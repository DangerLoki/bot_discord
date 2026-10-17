"""Servidor HTTP da Discord Activity sincronizada com o player do bot."""

import asyncio
import hashlib
import hmac
import json
import re
import secrets
import time
from collections.abc import Callable
from pathlib import Path

from aiohttp import web

from src.logger import get_logger
from src.models.player_state import RepeatMode

logger = get_logger(__name__)

_CONTROL_SECRET = secrets.token_bytes(32)
_CONTROL_HEADER = 'X-Loki-Control'
_VIDEO_ID_RE = re.compile(r'^[A-Za-z0-9_-]{11}$')


def create_activity_control_token(guild_id: int, user_id: int) -> str:
    """Cria uma credencial opaca, válida somente durante esta execução do bot."""
    payload = f'{guild_id}:{user_id}'.encode()
    signature = hmac.new(_CONTROL_SECRET, payload, hashlib.sha256).hexdigest()
    return f'{user_id}.{signature}'


def validate_activity_control_token(guild_id: int, token: str) -> int | None:
    """Valida a credencial e devolve o usuário Discord que abriu o painel."""
    try:
        raw_user_id, signature = token.split('.', 1)
        user_id = int(raw_user_id)
    except (AttributeError, TypeError, ValueError):
        return None
    expected = create_activity_control_token(guild_id, user_id).split('.', 1)[1]
    return user_id if hmac.compare_digest(signature, expected) else None


class _ActivityControlContext:
    """Contexto mínimo para reutilizar os serviços a partir do painel web."""

    def __init__(self, *, bot, guild, channel, author) -> None:
        self.bot = bot
        self.guild = guild
        self.channel = channel
        self.author = author

    async def send(self, *args, **kwargs):
        return await self.channel.send(*args, **kwargs)


class ActivityServer:
    """Serve a SPA da Activity e expõe snapshots somente-leitura do player."""

    def __init__(
        self,
        guild_states: dict,
        guild_services: dict,
        static_dir: str | Path,
        *,
        client_id_provider: Callable[[], str | None],
        bot_provider: Callable[[], object | None] | None = None,
        host: str = '0.0.0.0',
        port: int = 8080,
    ) -> None:
        self.guild_states = guild_states
        self.guild_services = guild_services
        self.static_dir = Path(static_dir)
        self.client_id_provider = client_id_provider
        self.bot_provider = bot_provider or (lambda: None)
        self.host = host
        self.port = port
        self._runner: web.AppRunner | None = None
        self._site: web.TCPSite | None = None
        self._control_locks: dict[int, asyncio.Lock] = {}

    @staticmethod
    def _status_reproducao(state, video: dict | None) -> str:
        if not video:
            return 'idle'
        voice_client = state.voice_client
        if state.saiu_pausado or (
            voice_client is not None and voice_client.is_paused()
        ):
            return 'paused'
        if state.is_playing_voice and voice_client is not None:
            if voice_client.is_playing():
                return 'playing'
        return 'loading' if state.is_playing_voice else 'idle'

    @staticmethod
    def _proximas_faixas(state, playlist: list, limite: int = 10) -> list[dict]:
        if state.shuffle_mode and state.shuffle_playlist:
            indices = state.shuffle_playlist[state.shuffle_index :]
        else:
            indices = range(state.playlist_index + 1, len(playlist))

        proximas = []
        for indice in indices:
            if not 0 <= indice < len(playlist):
                continue
            video = playlist[indice]
            if not state.shuffle_mode and video.get('tocado', False):
                continue
            proximas.append(
                {
                    'video_id': str(video.get('video_id') or ''),
                    'title': video.get('titulo') or 'Desconhecido',
                    'channel': video.get('canal') or 'Canal desconhecido',
                    'duration_seconds': int(video.get('duracao') or 0),
                    'thumbnail_url': video.get('thumbnail_url') or '',
                }
            )
            if len(proximas) >= limite:
                break
        return proximas

    def snapshot(self, guild_id: int) -> dict | None:
        """Cria um retrato consistente o bastante para corrigir o player visual."""
        state = self.guild_states.get(guild_id)
        services = self.guild_services.get(guild_id)
        if state is None or services is None:
            return None

        _, player_service = services
        video = player_service._current_video
        playlist = player_service.repo.load(guild_id)
        status = self._status_reproducao(state, video)
        elapsed = state.tempo_decorrido() if video else 0
        duration = int((video or {}).get('duracao') or 0)
        if duration:
            elapsed = min(elapsed, duration)

        return {
            'version': 1,
            'guild_id': str(guild_id),
            'server_time_ms': int(time.time() * 1000),
            'playback': {
                'status': status,
                'position_seconds': max(0, elapsed),
                'duration_seconds': duration,
                'muted_clip_recommended': True,
            },
            'video': (
                {
                    'video_id': str(video.get('video_id') or ''),
                    'title': video.get('titulo') or 'Desconhecido',
                    'channel': video.get('canal') or 'Canal desconhecido',
                    'url': video.get('embed_url') or video.get('url') or '',
                    'thumbnail_url': video.get('thumbnail_url') or '',
                }
                if video
                else None
            ),
            'queue': self._proximas_faixas(state, playlist),
            'modes': {
                'shuffle': state.shuffle_mode,
                'repeat': state.repeat_mode.value,
            },
            'controls': {
                'authorized': False,
                'connected': bool(
                    state.voice_client and state.voice_client.is_connected()
                ),
                'volume_percent': round(state.voice_volume * 100),
            },
        }

    @web.middleware
    async def _headers_middleware(self, request, handler):
        response = await handler(request)
        if request.path.startswith('/api/'):
            response.headers['Cache-Control'] = 'no-store'
            response.headers['Access-Control-Allow-Origin'] = '*'
            response.headers['Access-Control-Allow-Headers'] = (
                f'Content-Type, {_CONTROL_HEADER}'
            )
            response.headers['Access-Control-Allow-Methods'] = 'GET, POST, OPTIONS'
        return response

    async def _health(self, request: web.Request) -> web.Response:
        return web.json_response({'status': 'ok', 'service': 'loki-clipes'})

    async def _config(self, request: web.Request) -> web.Response:
        return web.json_response(
            {
                'client_id': self.client_id_provider() or '',
                'poll_interval_ms': 2000,
                'youtube_proxy_prefix': '/.proxy/youtube',
                'youtube_thumbnail_proxy_prefix': '/.proxy/ytimg',
            }
        )

    async def _state(self, request: web.Request) -> web.Response:
        guild_id = self._guild_id(request)
        snapshot = self.snapshot(guild_id)
        if snapshot is None:
            raise web.HTTPNotFound(
                text='servidor não encontrado', content_type='text/plain'
            )
        snapshot['controls']['authorized'] = self._control_user_id(request, guild_id) is not None
        return web.json_response(snapshot)

    @staticmethod
    def _guild_id(request: web.Request) -> int:
        raw_guild_id = request.query.get('guild_id', '')
        try:
            return int(raw_guild_id)
        except (TypeError, ValueError):
            raise web.HTTPBadRequest(
                text='guild_id inválido', content_type='text/plain'
            )

    @staticmethod
    def _json_error(error_type, message: str):
        raise error_type(
            text=json.dumps({'error': message}, ensure_ascii=False),
            content_type='application/json',
        )

    @staticmethod
    def _control_user_id(request: web.Request, guild_id: int) -> int | None:
        return validate_activity_control_token(
            guild_id, request.headers.get(_CONTROL_HEADER, '')
        )

    def _require_control_user(self, request: web.Request, guild_id: int) -> int:
        user_id = self._control_user_id(request, guild_id)
        if user_id is None:
            self._json_error(web.HTTPForbidden, 'Painel aberto sem permissão de controle.')
        return user_id

    def _control_context(self, guild_id: int, user_id: int, player_service):
        bot = self.bot_provider()
        guild = bot.get_guild(guild_id) if bot else None
        if guild is None:
            self._json_error(web.HTTPServiceUnavailable, 'Servidor Discord indisponível.')
        channel = (
            guild.get_channel(player_service.state.player_channel_id)
            if player_service.state.player_channel_id
            else None
        )
        if channel is None and player_service._status_msg is not None:
            channel = player_service._status_msg.channel
        if channel is None and player_service._playlist_msg is not None:
            channel = player_service._playlist_msg.channel
        if channel is None:
            self._json_error(
                web.HTTPConflict,
                'Defina o canal do painel no Discord antes de usar os controles web.',
            )
        author = guild.get_member(user_id) or f'Painel web ({user_id})'
        return _ActivityControlContext(
            bot=bot, guild=guild, channel=channel, author=author
        )

    async def _execute_control(
        self, guild_id: int, user_id: int, action: str, payload: dict
    ) -> str:
        services = self.guild_services.get(guild_id)
        state = self.guild_states.get(guild_id)
        if services is None or state is None:
            self._json_error(web.HTTPNotFound, 'Servidor não encontrado.')
        playlist_service, player_service = services
        ctx = self._control_context(guild_id, user_id, player_service)
        voice = state.voice_client
        connected = bool(voice and voice.is_connected())

        if action == 'previous':
            await playlist_service.voltar_video(ctx, announce=False)
            if connected:
                await player_service.tocar_atual(ctx)
            return 'Voltando para a faixa anterior.'

        if action == 'play_pause':
            if voice and voice.is_playing():
                voice.pause()
                state.pausar_rastreio()
                await player_service.atualizar_status_agora(ctx)
                return 'Reprodução pausada.'
            if voice and voice.is_paused():
                voice.resume()
                state.retomar_rastreio()
                await player_service.atualizar_status_agora(ctx)
                return 'Reprodução retomada.'
            if connected:
                await player_service.tocar_atual(ctx)
                return 'Iniciando a reprodução.'
            member_voice = getattr(ctx.author, 'voice', None)
            voice_channel = getattr(member_voice, 'channel', None)
            if voice_channel is None:
                self._json_error(
                    web.HTTPConflict,
                    'Entre em um canal de voz no Discord antes de iniciar a reprodução.',
                )
            if state.saiu_pausado:
                await player_service.voltar_e_retomar(ctx, voice_channel)
                return 'Bot reconectado à call e reprodução retomada.'
            state.voice_client = await voice_channel.connect()
            state.voice_bot = ctx.bot
            await player_service.tocar_atual(ctx)
            return 'Bot conectado à sua call e reprodução iniciada.'

        if action == 'next':
            await playlist_service.pular_video(ctx, announce=False)
            if connected:
                await player_service.tocar_atual(ctx)
            return 'Pulando para a próxima faixa.'

        if action == 'stop':
            if not connected:
                self._json_error(web.HTTPConflict, 'O bot já está fora da call.')
            await player_service.pausar_e_sair_da_call(ctx)
            return 'Reprodução pausada e bot removido da call.'

        if action == 'shuffle':
            await playlist_service.toggle_shuffle(ctx, silencioso=True)
            return 'Shuffle atualizado.'

        if action == 'repeat':
            state.repeat_mode = {
                RepeatMode.OFF: RepeatMode.ONE,
                RepeatMode.ONE: RepeatMode.ALL,
                RepeatMode.ALL: RepeatMode.OFF,
            }[state.repeat_mode]
            await player_service.persistir_estado()
            await player_service.atualizar_status_agora(ctx)
            return 'Modo de repetição atualizado.'

        if action == 'volume':
            try:
                percent = int(payload.get('value'))
            except (TypeError, ValueError):
                self._json_error(web.HTTPBadRequest, 'Volume inválido.')
            percent = max(0, min(200, percent))
            state.voice_volume = percent / 100
            if voice and voice.source:
                voice.source.volume = state.voice_volume
            await player_service.persistir_estado()
            await player_service.atualizar_status_agora(ctx)
            return f'Volume ajustado para {percent}%.'

        if action == 'reverse':
            await playlist_service.inverter_playlist(ctx, silencioso=True)
            return 'Ordem das próximas faixas invertida.'

        if action == 'promote':
            video_id = str(payload.get('video_id', ''))
            await playlist_service.promover_video(
                ctx, video_id_exato=video_id, bot=ctx.bot
            )
            return 'Faixa promovida para tocar em seguida.'

        if action == 'remove':
            video_id = str(payload.get('video_id', ''))
            await playlist_service.remover_video(
                ctx, f'https://www.youtube.com/watch?v={video_id}'
            )
            return 'Faixa removida da fila.'

        if action == 'clear':
            await playlist_service.limpar_playlist(ctx)
            return 'Fila limpa.'

        if action == 'add':
            video_id = str(payload.get('video_id', ''))
            if not _VIDEO_ID_RE.fullmatch(video_id):
                self._json_error(web.HTTPBadRequest, 'Vídeo inválido.')
            before = playlist_service.repo.load(guild_id)
            if any(str(item.get('video_id')) == video_id for item in before):
                self._json_error(web.HTTPConflict, 'Essa música já está na fila.')
            await playlist_service.adicionar_por_url(
                ctx, f'https://www.youtube.com/watch?v={video_id}'
            )
            after = playlist_service.repo.load(guild_id)
            if not any(str(item.get('video_id')) == video_id for item in after):
                self._json_error(web.HTTPBadGateway, 'Não foi possível adicionar o vídeo.')
            return 'Música adicionada à fila.'

        self._json_error(web.HTTPBadRequest, 'Comando desconhecido.')

    async def _control(self, request: web.Request) -> web.Response:
        guild_id = self._guild_id(request)
        user_id = self._require_control_user(request, guild_id)
        try:
            payload = await request.json()
        except (ValueError, TypeError):
            self._json_error(web.HTTPBadRequest, 'Corpo da requisição inválido.')
        if not isinstance(payload, dict):
            self._json_error(web.HTTPBadRequest, 'Corpo da requisição inválido.')
        action = str(payload.get('action', ''))
        lock = self._control_locks.setdefault(guild_id, asyncio.Lock())
        async with lock:
            message = await self._execute_control(guild_id, user_id, action, payload)
            snapshot = self.snapshot(guild_id)
        snapshot['controls']['authorized'] = True
        return web.json_response({'message': message, 'state': snapshot})

    async def _search(self, request: web.Request) -> web.Response:
        guild_id = self._guild_id(request)
        self._require_control_user(request, guild_id)
        query = request.query.get('q', '').strip()
        if not 2 <= len(query) <= 100:
            self._json_error(
                web.HTTPBadRequest, 'Digite entre 2 e 100 caracteres para pesquisar.'
            )
        services = self.guild_services.get(guild_id)
        if services is None:
            self._json_error(web.HTTPNotFound, 'Servidor não encontrado.')
        playlist_service, _ = services
        results = await playlist_service.yt.buscar_videos(query)
        return web.json_response(
            {
                'results': [
                    {
                        'video_id': str(item.get('video_id') or ''),
                        'title': item.get('titulo') or 'Desconhecido',
                        'channel': item.get('canal') or 'Canal desconhecido',
                        'duration': item.get('duracao_formatada') or '',
                        'thumbnail_url': item.get('thumbnail_url')
                        or f'https://img.youtube.com/vi/{item.get("video_id", "")}/hqdefault.jpg',
                    }
                    for item in (results or [])[:5]
                    if item.get('video_id')
                ]
            }
        )

    async def _index(self, request: web.Request) -> web.StreamResponse:
        index = self.static_dir / 'index.html'
        if not index.is_file():
            raise web.HTTPServiceUnavailable(
                text='Frontend da Activity não foi compilado.',
                content_type='text/plain',
            )
        return web.FileResponse(index, headers={'Cache-Control': 'no-store'})

    def _build_app(self) -> web.Application:
        app = web.Application(middlewares=[self._headers_middleware])
        app.router.add_get('/health', self._health)
        app.router.add_get('/api/config', self._config)
        app.router.add_get('/api/state', self._state)
        app.router.add_get('/api/search', self._search)
        app.router.add_post('/api/control', self._control)
        assets_dir = self.static_dir / 'assets'
        if assets_dir.is_dir():
            app.router.add_static('/assets', assets_dir, name='activity-assets')
        app.router.add_get('/{tail:.*}', self._index)
        return app

    async def start(self) -> None:
        if self._runner is not None:
            return
        if not (self.static_dir / 'index.html').is_file():
            raise RuntimeError(
                f'Frontend da Activity ausente em {self.static_dir}. '
                'Execute `npm ci && npm run build` dentro de activity/.'
            )
        self._runner = web.AppRunner(self._build_app())
        await self._runner.setup()
        self._site = web.TCPSite(self._runner, self.host, self.port)
        await self._site.start()
        logger.info(f'[ACTIVITY] servidor em http://{self.host}:{self.port}')

    async def stop(self) -> None:
        if self._runner is None:
            return
        await self._runner.cleanup()
        self._runner = None
        self._site = None
        logger.info('[ACTIVITY] servidor encerrado')
