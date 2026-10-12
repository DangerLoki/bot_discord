"""Servidor HTTP da Discord Activity sincronizada com o player do bot."""

import time
from collections.abc import Callable
from pathlib import Path

from aiohttp import web

from src.logger import get_logger

logger = get_logger(__name__)


class ActivityServer:
    """Serve a SPA da Activity e expõe snapshots somente-leitura do player."""

    def __init__(
        self,
        guild_states: dict,
        guild_services: dict,
        static_dir: str | Path,
        *,
        client_id_provider: Callable[[], str | None],
        host: str = '0.0.0.0',
        port: int = 8080,
    ) -> None:
        self.guild_states = guild_states
        self.guild_services = guild_services
        self.static_dir = Path(static_dir)
        self.client_id_provider = client_id_provider
        self.host = host
        self.port = port
        self._runner: web.AppRunner | None = None
        self._site: web.TCPSite | None = None

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
    def _proximas_faixas(state, playlist: list, limite: int = 5) -> list[dict]:
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
        }

    @web.middleware
    async def _headers_middleware(self, request, handler):
        response = await handler(request)
        if request.path.startswith('/api/'):
            response.headers['Cache-Control'] = 'no-store'
            response.headers['Access-Control-Allow-Origin'] = '*'
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
        raw_guild_id = request.query.get('guild_id', '')
        try:
            guild_id = int(raw_guild_id)
        except (TypeError, ValueError):
            raise web.HTTPBadRequest(
                text='guild_id inválido', content_type='text/plain'
            )
        snapshot = self.snapshot(guild_id)
        if snapshot is None:
            raise web.HTTPNotFound(
                text='servidor não encontrado', content_type='text/plain'
            )
        return web.json_response(snapshot)

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
