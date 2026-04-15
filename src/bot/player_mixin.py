import os
import asyncio
import random
import time

import discord
import yt_dlp

from src.logger import get_logger
from src.bot.utils import GeoBlockedError, _is_geo_blocked, formatar_duracao, embed_carregando, embed_erro, embed_aviso

logger = get_logger(__name__)


class PlayerMixin:
    """Métodos de reprodução de áudio em canal de voz."""

    # ------------------------------------------------------------------
    # Status do bot (presença / activity)
    # ------------------------------------------------------------------

    def _iniciar_rastreio_tempo(self, duracao_total: int):
        """Salva o instante de início e a duração total da música."""
        self._playback_start = time.monotonic()
        self._playback_paused_at = None
        self._playback_duracao = duracao_total  # segundos

    def _tempo_decorrido(self) -> int:
        """Retorna segundos decorridos (descontando pausas)."""
        if not hasattr(self, '_playback_start') or self._playback_start is None:
            return 0
        if self._playback_paused_at is not None:
            return int(self._playback_paused_at - self._playback_start)
        return int(time.monotonic() - self._playback_start)

    def _pausar_rastreio(self):
        if hasattr(self, '_playback_start') and self._playback_paused_at is None:
            self._playback_paused_at = time.monotonic()

    def _retomar_rastreio(self):
        if hasattr(self, '_playback_paused_at') and self._playback_paused_at is not None:
            pausa = time.monotonic() - self._playback_paused_at
            self._playback_start += pausa
            self._playback_paused_at = None

    async def _atualizar_status(self, titulo: str, duracao: int):
        """Atualiza a presença do bot com a música atual e tempo."""
        bot = getattr(self, 'voice_bot', None)
        if not bot:
            return
        decorrido = formatar_duracao(self._tempo_decorrido())
        total = formatar_duracao(duracao)
        activity = discord.Activity(
            type=discord.ActivityType.listening,
            name=f'{titulo} [{decorrido}/{total}]',
        )
        try:
            await bot.change_presence(activity=activity)
        except Exception:
            pass

    async def _limpar_status(self):
        """Remove a presença do bot."""
        bot = getattr(self, 'voice_bot', None)
        if not bot:
            return
        try:
            await bot.change_presence(activity=None)
        except Exception:
            pass

    async def _status_loop(self):
        """Loop que atualiza o status a cada 5 segundos enquanto toca.

        O Discord tem rate-limit em change_presence (~15s de propagação
        para outros usuários), então 5s é o melhor equilíbrio entre
        precisão e respeito ao limite.
        """
        try:
            while self.is_playing_voice:
                titulo = getattr(self, '_status_titulo', '')
                duracao = getattr(self, '_playback_duracao', 0)
                if titulo:
                    await self._atualizar_status(titulo, duracao)
                await asyncio.sleep(5)
        except asyncio.CancelledError:
            pass
        finally:
            await self._limpar_status()

    def _iniciar_status_loop(self):
        """Inicia a task de atualização do status."""
        if hasattr(self, '_status_task') and self._status_task and not self._status_task.done():
            self._status_task.cancel()
        loop = self.voice_bot.loop if self.voice_bot else asyncio.get_event_loop()
        self._status_task = loop.create_task(self._status_loop())

    def _parar_status_loop(self):
        """Para a task de atualização do status."""
        if hasattr(self, '_status_task') and self._status_task and not self._status_task.done():
            self._status_task.cancel()

    # ------------------------------------------------------------------
    # Download e cache
    # ------------------------------------------------------------------

    async def baixar_audio(self, video_url: str, video_id: str) -> str | None:
        """Baixa o áudio para o cache e retorna o caminho do arquivo.
        Lança GeoBlockedError se o vídeo estiver bloqueado na região.
        """
        existente = list(self.cache_dir.glob(f'{video_id}.*'))
        if existente:
            logger.debug(f'[CACHE] usando arquivo em cache: {existente[0]}')
            return str(existente[0])

        destino = self.cache_dir / video_id
        opts = {
            'format': 'bestaudio/best',
            'outtmpl': str(destino) + '.%(ext)s',
            'quiet': True,
            'no_warnings': True,
            'noplaylist': True,
            'js_runtimes': {'node': {}},
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'opus',
                'preferredquality': '0',
            }],
        }
        if os.path.exists(self.cookies_file):
            opts['cookiefile'] = self.cookies_file
        if self.proxy:
            opts['proxy'] = self.proxy

        def _download():
            try:
                with yt_dlp.YoutubeDL(opts) as ydl:
                    ydl.download([video_url])
                resultado = list(self.cache_dir.glob(f'{video_id}.*'))
                return str(resultado[0]) if resultado else None
            except Exception as e:
                if _is_geo_blocked(str(e)):
                    raise GeoBlockedError(str(e))
                logger.error(f'[yt-dlp] erro ao baixar {video_url}: {e}')
                return None

        return await asyncio.to_thread(_download)

    def _limpar_cache(self, video_id: str) -> None:
        for f in self.cache_dir.glob(f'{video_id}.*'):
            try:
                f.unlink()
                logger.debug(f'[CACHE] removido: {f}')
            except Exception as e:
                logger.warning(f'[CACHE] falha ao remover {f}: {e}')

    def _atualizar_shuffle_com_novo_video(self, novo_indice: int) -> None:
        """Atualiza a lista de shuffle inserindo o novo vídeo em posição aleatória."""
        if not self.shuffle_mode or not self.shuffle_playlist:
            return
        
        # Insere o novo vídeo em uma posição aleatória da lista shuffle
        # (como uma seed: mantém ordem relativa mas insere novos elementos aleatoriamente)
        posicao_aleatoria = random.randint(0, len(self.shuffle_playlist))
        self.shuffle_playlist.insert(posicao_aleatoria, novo_indice)
        
        logger.info(f'[SHUFFLE] Vídeo na posição {novo_indice} inserido na posição {posicao_aleatoria} da lista aleatória (ID: {self.shuffle_id})')

    # ------------------------------------------------------------------
    # Lógica de shuffle
    # ------------------------------------------------------------------

    def _proximo_aleatorio(self, playlist: list) -> int:
        """Retorna o próximo índice da lista aleatória gerada."""
        if not self.shuffle_playlist or self.shuffle_index >= len(self.shuffle_playlist):
            # Regenera lista se necessário
            nao_tocados = [i for i, v in enumerate(playlist) if not v.get('tocado', False)]
            if nao_tocados:
                random.shuffle(nao_tocados)
                self.shuffle_playlist = nao_tocados
                self.shuffle_index = 0
            else:
                # Se todos foram tocados, reinicia ciclo
                for v in playlist:
                    v['tocado'] = False
                self.salvar_playlist(playlist)
                indices = list(range(len(playlist)))
                random.shuffle(indices)
                self.shuffle_playlist = indices
                self.shuffle_index = 0

        if self.shuffle_playlist:
            index = self.shuffle_playlist[self.shuffle_index]
            self.shuffle_index += 1
            return index
        return self.playlist_index

    # ------------------------------------------------------------------
    # Reprodução
    # ------------------------------------------------------------------

    async def tocar_atual(self, ctx):
        """Ponto de entrada público — garante execução exclusiva via lock."""
        if self._carregando.locked():
            return
        async with self._carregando:
            await self._tocar_atual_impl(ctx)

    async def _tocar_atual_impl(self, ctx):
        if not self.voice_client or not self.voice_client.is_connected():
            await ctx.send(embed=embed_erro('❌ Não estou em nenhum canal de voz!'))
            return

        if self.voice_client.is_playing() or self.voice_client.is_paused():
            self.is_playing_voice = False
            self.voice_client.stop()

        while True:
            playlist = self.carregar_playlist()
            if not playlist:
                await ctx.send(embed=embed_erro('❌ Playlist vazia. Adicione vídeos com `&add`.'))
                return

            if self.playlist_index >= len(playlist):
                self.playlist_index = 0

            # Pula músicas já tocadas (a menos que todas já tenham sido)
            if not self.shuffle_mode:
                inicio = self.playlist_index
                while playlist[self.playlist_index].get('tocado', False):
                    self.playlist_index = (self.playlist_index + 1) % len(playlist)
                    if self.playlist_index == inicio:
                        # Todas já foram tocadas — avisa e para
                        await ctx.send(embed=embed_aviso('📋 Todas as músicas já foram tocadas! Use `&recomecar` ou adicione novas.'))
                        self.is_playing_voice = False
                        return

            video = playlist[self.playlist_index]
            total = len(playlist)
            titulo = video.get('titulo', 'Desconhecido')
            video_url = video.get('embed_url', '')
            video_id = video.get('video_id', '')

            msg_carregando = await ctx.send(embed=embed_carregando(f'🔄 Carregando **{titulo}**...'))

            playlist[self.playlist_index]['tocado'] = True
            # Se está em modo shuffle, salva o shuffle_id e posicao_shuffle
            if self.shuffle_mode and self.shuffle_id:
                posicao_shuffle = self.shuffle_index + 1  # Posição atual no shuffle
                playlist[self.playlist_index]['shuffle_id'] = self.shuffle_id
                playlist[self.playlist_index]['posicao_shuffle'] = posicao_shuffle
            self.salvar_playlist(playlist)

            try:
                audio_path = await self.baixar_audio(video_url, video_id)
            except GeoBlockedError:
                await msg_carregando.edit(embed=embed_erro(f'🌍 **{titulo}** está bloqueado na sua região e foi removido da playlist.'))
                playlist = self.carregar_playlist()
                playlist = [v for v in playlist if v.get('video_id') != video_id]
                for i, v in enumerate(playlist):
                    v['posicao'] = i + 1
                self.salvar_playlist(playlist)
                if not playlist:
                    await ctx.send(embed=embed_aviso('📋 Playlist vazia após remoção.'))
                    return
                self.playlist_index = self.playlist_index % len(playlist)
                continue

            if not audio_path:
                await msg_carregando.edit(embed=embed_erro(f'❌ Não consegui baixar o áudio de **{titulo}**. Pulando...'))
                self.playlist_index = (self.playlist_index + 1) % len(playlist)
                # Pula músicas que já foram tocadas
                tentativas = 0
                while tentativas < len(playlist) and playlist[self.playlist_index].get('tocado', False):
                    self.playlist_index = (self.playlist_index + 1) % len(playlist)
                    tentativas += 1
                continue
            break

        try:
            source = discord.FFmpegPCMAudio(audio_path)
            source = discord.PCMVolumeTransformer(source, volume=self.voice_volume)
        except Exception as e:
            await ctx.send(embed=embed_erro(f'❌ Erro ao criar stream de áudio: {e}'))
            return

        self.is_playing_voice = True
        video_id_atual = video.get('video_id', '')
        # Usa título original do Spotify (artista - música) quando disponível
        if video.get('fonte') == 'spotify' and video.get('spotify_titulo_original'):
            canal = video.get('canal', '')
            self._status_titulo = f"{canal} - {video['spotify_titulo_original']}" if canal else video['spotify_titulo_original']
        else:
            self._status_titulo = titulo
        self._iniciar_rastreio_tempo(video.get('duracao', 0) or 0)
        self._iniciar_status_loop()

        def after_playing(error):
            if error:
                logger.error(f'Erro no player: {error}')
            self._limpar_cache(video_id_atual)
            if self.is_playing_voice and self.voice_client and self.voice_client.is_connected():
                asyncio.run_coroutine_threadsafe(
                    self._auto_next(ctx), self.voice_bot.loop
                )

        self.voice_client.play(source, after=after_playing)

        embed = discord.Embed(
            title='🔊 Tocando na Call',
            description=f"**[{titulo}]({video_url})**",
            color=0x1DB954,
        )
        embed.set_thumbnail(url=video.get('thumbnail_url', ''))
        embed.add_field(name='Duração', value=video.get('duracao_formatada', '??:??'), inline=True)
        embed.add_field(name='Posição', value=f"{self.playlist_index + 1}/{total}", inline=True)
        embed.add_field(name='Volume', value=f'{int(self.voice_volume * 100)}%', inline=True)
        await msg_carregando.edit(embed=embed)
        logger.info(f'[VOZ] Tocando: {titulo}')

    async def _auto_next(self, ctx):
        """Chamado automaticamente ao terminar uma música."""
        self._parar_status_loop()
        if not self.is_playing_voice:
            return

        playlist = self.carregar_playlist()
        if not playlist:
            self.is_playing_voice = False
            await ctx.send(embed=embed_aviso('📋 Playlist terminou!'))
            return

        if self.shuffle_mode:
            self.playlist_index = self._proximo_aleatorio(playlist)
        else:
            self.playlist_index += 1
            if self.playlist_index >= len(playlist):
                self.playlist_index = 0
                self.is_playing_voice = False
                await ctx.send(embed=embed_aviso('📋 Playlist terminou! Use `&tocar` para recomeçar.'))
                return
            
            # Verifica se a próxima música já foi tocada e pula para a próxima não tocada
            while self.playlist_index < len(playlist) and playlist[self.playlist_index].get('tocado', False):
                self.playlist_index += 1
            
            # Se chegou ao final, playlist terminou
            if self.playlist_index >= len(playlist):
                self.playlist_index = 0
                self.is_playing_voice = False
                await ctx.send(embed=embed_aviso('📋 Playlist terminou! Use `&tocar` para recomeçar.'))
                return

        await self.tocar_atual(ctx)
