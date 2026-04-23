"""Lógica de reprodução de áudio em canal de voz."""
import asyncio
import time

import discord

from src.logger import get_logger
from src.models.player_state import PlayerState
from src.repositories.playlist_repository import PlaylistRepository
from src.services.youtube_service import YouTubeService
from src.services.playlist_service import PlaylistService
from src.services.player_status import PlayerStatus
from src.utils import GeoBlockedError, embed_carregando, embed_erro, embed_aviso

logger = get_logger(__name__)


class PlayerService(PlayerStatus):
    """Gerencia a reprodução de áudio: download, playback e presença do bot.

    Lógica de status herdada de PlayerStatus.
    """

    def __init__(
        self,
        state: PlayerState,
        repo: PlaylistRepository,
        yt: YouTubeService,
        playlist_svc: PlaylistService,
    ) -> None:
        self.state = state
        self.repo = repo
        self.yt = yt
        self.playlist_svc = playlist_svc

    # ------------------------------------------------------------------
    # Reprodução
    # ------------------------------------------------------------------

    async def tocar_atual(self, ctx) -> None:
        """Ponto de entrada público — usa lock para execução exclusiva."""
        st = self.state
        if st.carregando.locked():
            logger.debug('[PERF][TOCAR] lock ocupado — chamada ignorada')
            return
        t0 = time.perf_counter()
        async with st.carregando:
            await self._tocar_atual_impl(ctx)
        elapsed = time.perf_counter() - t0
        logger.info(f'[PERF][TOCAR] tempo total até início da reprodução: {elapsed:.2f}s')

    async def _tocar_atual_impl(self, ctx) -> None:
        st = self.state
        vc = st.voice_client

        if not vc or not vc.is_connected():
            await ctx.send(embed=embed_erro('❌ Não estou em nenhum canal de voz!'))
            return

        if vc.is_playing() or vc.is_paused():
            st.is_playing_voice = False
            vc.stop()

        while True:
            playlist = self.repo.load()
            if not playlist:
                await ctx.send(embed=embed_erro('❌ Playlist vazia. Adicione vídeos com `&add`.'))
                return

            if st.playlist_index >= len(playlist):
                st.playlist_index = 0

            # Pula músicas já tocadas (modo sequencial)
            if not st.shuffle_mode:
                inicio = st.playlist_index
                while playlist[st.playlist_index].get('tocado', False):
                    st.playlist_index = (st.playlist_index + 1) % len(playlist)
                    if st.playlist_index == inicio:
                        await ctx.send(
                            embed=embed_aviso(
                                '📋 Todas as músicas já foram tocadas! '
                                'Use `&recomecar` ou adicione novas.'
                            )
                        )
                        st.is_playing_voice = False
                        return

            video = playlist[st.playlist_index]
            total = len(playlist)
            titulo = video.get('titulo', 'Desconhecido')
            video_url = video.get('embed_url', '')
            video_id = video.get('video_id', '')

            msg_carregando = await ctx.send(embed=embed_carregando(f'🔄 Carregando **{titulo}**...'))

            if st.shuffle_mode and st.shuffle_id:
                posicao_shuffle = st.shuffle_index + 1
                playlist[st.playlist_index]['shuffle_id'] = st.shuffle_id
                playlist[st.playlist_index]['posicao_shuffle'] = posicao_shuffle
            self.repo.save(playlist)

            try:
                audio_path = await self.yt.baixar_audio(video_url, video_id)
            except GeoBlockedError:
                await msg_carregando.edit(
                    embed=embed_erro(
                        f'🌍 **{titulo}** está bloqueado na sua região e foi removido da playlist.'
                    )
                )
                playlist = self.repo.load()
                playlist = [v for v in playlist if v.get('video_id') != video_id]
                for i, v in enumerate(playlist):
                    v['posicao'] = i + 1
                self.repo.save(playlist)
                if not playlist:
                    await ctx.send(embed=embed_aviso('📋 Playlist vazia após remoção.'))
                    return
                st.playlist_index = st.playlist_index % len(playlist)
                continue

            if not audio_path:
                await msg_carregando.edit(
                    embed=embed_erro(f'❌ Não consegui baixar o áudio de **{titulo}**. Pulando...')
                )
                st.playlist_index = (st.playlist_index + 1) % len(playlist)
                tentativas = 0
                while (
                    tentativas < len(playlist)
                    and playlist[st.playlist_index].get('tocado', False)
                ):
                    st.playlist_index = (st.playlist_index + 1) % len(playlist)
                    tentativas += 1
                continue
            break

        try:
            source = discord.FFmpegPCMAudio(audio_path)
            source = discord.PCMVolumeTransformer(source, volume=st.voice_volume)
        except Exception as e:
            await ctx.send(embed=embed_erro(f'❌ Erro ao criar stream de áudio: {e}'))
            return

        st.is_playing_voice = True
        video_id_atual = video.get('video_id', '')
        if video.get('fonte') == 'spotify' and video.get('spotify_titulo_original'):
            canal = video.get('canal', '')
            st._status_titulo = (
                f"{canal} - {video['spotify_titulo_original']}" if canal
                else video['spotify_titulo_original']
            )
        else:
            st._status_titulo = titulo
        st.iniciar_rastreio_tempo(video.get('duracao', 0) or 0)
        self._iniciar_status_loop()

        def after_playing(error):
            if error:
                logger.error(f'Erro no player: {error}')
            self.yt.limpar_cache(video_id_atual)
            if st.is_playing_voice and vc and vc.is_connected():
                asyncio.run_coroutine_threadsafe(
                    self._auto_next(ctx), st.voice_bot.loop
                )

        vc.play(source, after=after_playing)

        await self._enviar_embed_tocando(msg_carregando, video, total, st)
        logger.info(f'[VOZ] Tocando: {titulo}')

    async def _enviar_embed_tocando(self, msg, video: dict, total: int, st) -> None:
        """Edita a mensagem de carregando para o embed de 'tocando agora'."""
        titulo = video.get('titulo', 'Desconhecido')
        video_url = video.get('embed_url', '')
        embed = discord.Embed(
            title='🔊 Tocando na Call',
            description=f'**[{titulo}]({video_url})**',
            color=0x1DB954,
        )
        embed.set_thumbnail(url=video.get('thumbnail_url', ''))
        embed.add_field(name='Duração', value=video.get('duracao_formatada', '??:??'), inline=True)
        embed.add_field(name='Posição', value=f'{st.playlist_index + 1}/{total}', inline=True)
        embed.add_field(name='Volume', value=f'{int(st.voice_volume * 100)}%', inline=True)
        await msg.edit(embed=embed)


    async def _auto_next(self, ctx) -> None:
        """Chamado automaticamente ao terminar uma música."""
        st = self.state
        self._parar_status_loop()
        if not st.is_playing_voice:
            return

        playlist = self.repo.load()
        if playlist and st.playlist_index < len(playlist):
            playlist[st.playlist_index]['tocado'] = True
            self.repo.save(playlist)

        if not playlist:
            st.is_playing_voice = False
            await ctx.send(embed=embed_aviso('📋 Playlist terminou!'))
            return

        if st.shuffle_mode:
            st.playlist_index = self.playlist_svc.proximo_aleatorio(playlist)
        else:
            st.playlist_index += 1
            if st.playlist_index >= len(playlist):
                st.playlist_index = 0
                st.is_playing_voice = False
                await ctx.send(
                    embed=embed_aviso('📋 Playlist terminou! Use `&tocar` para recomeçar.')
                )
                return
            while (
                st.playlist_index < len(playlist)
                and playlist[st.playlist_index].get('tocado', False)
            ):
                st.playlist_index += 1
            if st.playlist_index >= len(playlist):
                st.playlist_index = 0
                st.is_playing_voice = False
                await ctx.send(
                    embed=embed_aviso('📋 Playlist terminou! Use `&tocar` para recomeçar.')
                )
                return

        await self.tocar_atual(ctx)
