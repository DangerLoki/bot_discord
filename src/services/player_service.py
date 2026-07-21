"""Lógica de reprodução de áudio em canal de voz."""
import asyncio
import time

import discord

from src.logger import get_logger
from src.models.player_state import PlayerState, RepeatMode
from src.repositories.playlist_repository import PlaylistRepository
from src.services.player_status import PlayerStatus
from src.services.playlist_service import PlaylistService
from src.services.youtube_service import YouTubeService
from src.ui.player_controls import PlayerControlView, PlaylistQueueView
from src.utils import BotBlockedError, GeoBlockedError, embed_aviso, embed_carregando, embed_erro
from src.utils.formatters import formatar_duracao

logger = get_logger(__name__)
DOWNLOAD_TIMEOUT_SECONDS = 35
CHANNEL_CLEANUP_INTERVAL_SECONDS = 5
PROGRESS_UPDATE_INTERVAL_SECONDS = 10
PLAYLIST_MSG_LIMITE = 15


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
        self._status_msg: discord.Message | None = None
        self._playlist_msg: discord.Message | None = None
        self._current_video: dict | None = None
        self._current_total: int = 0
        self._playlist_scroll: int = 0
        self.view = PlayerControlView(state, self, playlist_svc)
        self.queue_view = PlaylistQueueView(state, self, playlist_svc)

    # ------------------------------------------------------------------
    # Mensagem de status única (evita spam: edita sempre a mesma mensagem
    # em vez de enviar uma nova a cada troca de faixa, como fazem
    # bots de música como Rythm/FredBoat/Jockie Music).
    # ------------------------------------------------------------------

    def reset_status_message(self) -> None:
        """Descarta a referência das mensagens do painel (ex: ao sair da call)."""
        self._parar_progress_loop()
        self._status_msg = None
        self._playlist_msg = None
        self._current_video = None

    def _painel_channel(self, ctx):
        """Retorna o canal dedicado do painel (se configurado) ou o canal do comando."""
        channel_id = self.state.player_channel_id
        if channel_id and ctx.guild:
            channel = ctx.guild.get_channel(channel_id)
            if channel:
                return channel
        return ctx.channel

    async def _get_status_message(self, ctx, embed: discord.Embed) -> discord.Message:
        """Retorna a mensagem de status reaproveitável, editando-a se possível.

        Se não houver mensagem anterior, se ela for de outro canal ou se a
        edição falhar (mensagem apagada, etc.), envia uma nova e a registra.
        """
        canal = self._painel_channel(ctx)
        msg = self._status_msg
        if msg and msg.channel.id == canal.id:
            try:
                await msg.edit(embed=embed, view=self.view)
                return msg
            except (discord.NotFound, discord.HTTPException) as e:
                logger.debug(f'[STATUS_MSG] falha ao reutilizar mensagem: {e}')

        msg = await canal.send(embed=embed, view=self.view)
        self._status_msg = msg
        return msg

    # ------------------------------------------------------------------
    # Mensagem da fila de reprodução (fica acima do card de status)
    # ------------------------------------------------------------------

    async def _get_playlist_message(self, ctx, embed: discord.Embed) -> discord.Message:
        canal = self._painel_channel(ctx)
        msg = self._playlist_msg
        if msg and msg.channel.id == canal.id:
            try:
                await msg.edit(embed=embed, view=self.queue_view)
                return msg
            except (discord.NotFound, discord.HTTPException) as e:
                logger.debug(f'[PLAYLIST_MSG] falha ao reutilizar mensagem: {e}')

        msg = await canal.send(embed=embed, view=self.queue_view)
        self._playlist_msg = msg
        return msg

    def _construir_embed_playlist(
        self, playlist: list, indice_atual: int, inicio: int | None = None
    ) -> discord.Embed:
        """Monta o embed da fila, marcando a música atual (▶️) e a próxima (⏭️).

        `inicio` permite rolar manualmente a janela exibida (paginação via botões).
        Quando omitido, a janela é centralizada automaticamente na faixa atual.
        """
        embed = discord.Embed(title='📋 Fila de Reprodução', color=0x5865F2)
        total = len(playlist)
        if not playlist:
            embed.description = 'Playlist vazia.'
            self._playlist_scroll = 0
            return embed

        if total <= PLAYLIST_MSG_LIMITE:
            inicio = 0
        elif inicio is None:
            inicio = max(0, min(indice_atual - 2, total - PLAYLIST_MSG_LIMITE))
        else:
            inicio = max(0, min(inicio, total - PLAYLIST_MSG_LIMITE))
        self._playlist_scroll = inicio
        fim = min(total, inicio + PLAYLIST_MSG_LIMITE)

        linhas = []
        if inicio > 0:
            linhas.append(f'*… e mais {inicio} música(s) acima*')
        for i in range(inicio, fim):
            video = playlist[i]
            titulo = video.get('titulo') or 'Desconhecido'
            url = video.get('embed_url') or '#'
            if i == indice_atual:
                marcador = '▶️'
            elif i == (indice_atual + 1) % total:
                marcador = '⏭️'
            else:
                marcador = '▫️'
            linhas.append(f'{marcador} **{i + 1}.** [{titulo}]({url})')
        if fim < total:
            linhas.append(f'*… e mais {total - fim} música(s) abaixo*')

        embed.description = '\n'.join(linhas)
        embed.set_footer(text=f'{total} música(s) na fila · 🔃 inverte · ◀️▶️ navega')
        return embed

    async def _atualizar_mensagem_playlist(self, ctx, playlist: list, indice_atual: int) -> None:
        embed = self._construir_embed_playlist(playlist, indice_atual)
        await self._get_playlist_message(ctx, embed)

    async def mudar_pagina_playlist(self, ctx, delta: int) -> None:
        """Rola a mensagem da fila para frente/trás em blocos de `PLAYLIST_MSG_LIMITE`."""
        playlist = self.repo.load()
        if not playlist:
            return
        novo_inicio = self._playlist_scroll + delta * PLAYLIST_MSG_LIMITE
        embed = self._construir_embed_playlist(
            playlist, self.state.playlist_index, inicio=novo_inicio
        )
        await self._get_playlist_message(ctx, embed)


    async def _preparar_canal_painel(self, ctx) -> None:
        """Limpa o canal dedicado do painel antes de criar as mensagens do player.

        Só executa na primeira criação do painel (quando ainda não há mensagens
        de status/fila registradas), para não apagar o próprio painel em
        chamadas seguintes (skip, pausar, recomeçar etc).
        """
        if self._status_msg is not None or self._playlist_msg is not None:
            return
        if not self.state.player_channel_id:
            return

        canal = self._painel_channel(ctx)
        try:
            await canal.purge(limit=100)
        except discord.Forbidden:
            logger.warning(f'[PAINEL] sem permissão para limpar #{canal.name} antes do painel.')
        except discord.HTTPException as e:
            logger.debug(f'[PAINEL] falha ao limpar canal antes do painel: {e}')

    # ------------------------------------------------------------------
    # Limpeza automática do canal do painel
    # ------------------------------------------------------------------

    def iniciar_limpeza_canal(self, channel: discord.TextChannel) -> None:
        """Inicia o loop que remove periodicamente mensagens de usuários no canal do painel."""
        self.parar_limpeza_canal()
        self.state._cleanup_task = asyncio.create_task(self._limpeza_canal_loop(channel))

    def parar_limpeza_canal(self) -> None:
        task = self.state._cleanup_task
        if task and not task.done():
            task.cancel()

    async def _limpeza_canal_loop(self, channel: discord.TextChannel) -> None:
        """A cada poucos segundos, apaga mensagens enviadas por usuários no canal do painel,
        mantendo apenas as mensagens do próprio bot (ex: o card de status).
        """
        try:
            while True:
                await asyncio.sleep(CHANNEL_CLEANUP_INTERVAL_SECONDS)
                try:
                    await channel.purge(limit=50, check=lambda m: not m.author.bot)
                except discord.Forbidden:
                    logger.warning(
                        f'[PAINEL] sem permissão para limpar mensagens em #{channel.name}'
                    )
                except discord.HTTPException as e:
                    logger.debug(f'[PAINEL] falha ao limpar mensagens: {e}')
        except asyncio.CancelledError:
            pass

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

        falhas_consecutivas = 0
        while True:
            playlist = self.repo.load()
            if not playlist:
                await ctx.send(embed=embed_erro('❌ Playlist vazia. Adicione vídeos com `&add`.'))
                return

            if st.playlist_index >= len(playlist):
                st.playlist_index = 0

            # Pula músicas já tocadas (modo sequencial), exceto em repeat ONE
            if not st.shuffle_mode and st.repeat_mode != RepeatMode.ONE:
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
            titulo = video.get('titulo') or 'Desconhecido'
            video_url = video.get('embed_url') or ''
            video_id = video.get('video_id', '')

            await self._preparar_canal_painel(ctx)
            await self._atualizar_mensagem_playlist(ctx, playlist, st.playlist_index)
            msg_carregando = await self._get_status_message(
                ctx, embed_carregando(f'🔄 Carregando **{titulo}**...')
            )

            if st.shuffle_mode and st.shuffle_id:
                posicao_shuffle = st.shuffle_index + 1
                playlist[st.playlist_index]['shuffle_id'] = st.shuffle_id
                playlist[st.playlist_index]['posicao_shuffle'] = posicao_shuffle
            self.repo.save(playlist)

            try:
                audio_path = await asyncio.wait_for(
                    self.yt.baixar_audio(video_url, video_id),
                    timeout=DOWNLOAD_TIMEOUT_SECONDS,
                )
            except BotBlockedError:
                await msg_carregando.edit(
                    embed=embed_erro(
                        '🤖 **YouTube está bloqueando os downloads** (detecção de bot).\n'
                        'Configure o arquivo `config/cookies.txt` com cookies do YouTube.'
                    )
                )
                st.is_playing_voice = False
                return
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
            except asyncio.TimeoutError:
                falhas_consecutivas += 1
                await msg_carregando.edit(
                    embed=embed_erro(
                        f'⏱️ Tempo limite ao carregar **{titulo}**. Pulando para a próxima...'
                    )
                )
                logger.warning(
                    f'[PERF][DOWNLOAD] timeout após {DOWNLOAD_TIMEOUT_SECONDS}s '
                    f'video_id={video_id}'
                )
                st.playlist_index = (st.playlist_index + 1) % len(playlist)
                if falhas_consecutivas >= 3:
                    st.is_playing_voice = False
                    await ctx.send(
                        embed=embed_erro(
                            '❌ Não consegui carregar áudio após várias tentativas. '
                            'Tente novamente em instantes.'
                        )
                    )
                    return
                continue

            if not audio_path:
                falhas_consecutivas += 1
                if falhas_consecutivas >= 3:
                    await msg_carregando.edit(
                        embed=embed_erro(
                            '🤖 **YouTube está bloqueando os downloads** (detecção de bot).\n'
                            'Configure o arquivo `config/cookies.txt` com cookies do YouTube.'
                        )
                    )
                    st.is_playing_voice = False
                    return
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
                if tentativas >= len(playlist):
                    await ctx.send(embed=embed_aviso('📋 Nenhuma música disponível para tocar.'))
                    st.is_playing_voice = False
                    return
                continue
            falhas_consecutivas = 0
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

        await self._enviar_embed_tocando(ctx, video, total, st)
        logger.info(f'[VOZ] Tocando: {titulo}')

    # ------------------------------------------------------------------
    # Card "tocando agora" — progresso, controles e atualização periódica
    # ------------------------------------------------------------------

    @staticmethod
    def _barra_progresso(elapsed: int, total: int, tamanho: int = 18) -> str:
        if not total:
            return '▬' * tamanho
        posicao = min(int((elapsed / total) * tamanho), tamanho - 1)
        return '▬' * posicao + '🔘' + '▬' * (tamanho - posicao - 1)

    def _construir_embed_tocando(self, video: dict, total: int, st) -> discord.Embed:
        """Monta o embed do player: progresso atual, faixa e informações de reprodução."""
        titulo = video.get('titulo') or 'Desconhecido'
        video_url = video.get('embed_url') or ''
        pausado = bool(self.state.voice_client and self.state.voice_client.is_paused())
        status_titulo = '⏸️ Pausado' if pausado else '▶️ Tocando na Call'
        _repeat_icon = {
            RepeatMode.OFF: '',
            RepeatMode.ONE: ' 🔂',
            RepeatMode.ALL: ' 🔁',
        }.get(st.repeat_mode, '')

        duracao_total = video.get('duracao', 0) or 0
        elapsed = st.tempo_decorrido()
        if duracao_total:
            elapsed = min(elapsed, duracao_total)
        barra = self._barra_progresso(elapsed, duracao_total)

        embed = discord.Embed(
            title=f'{status_titulo}{_repeat_icon}',
            description=(
                f'**[{titulo}]({video_url})**\n\n'
                f'{barra}\n'
                f'`{formatar_duracao(elapsed)} / {formatar_duracao(duracao_total)}`'
            ),
            color=0x1DB954,
        )
        embed.set_thumbnail(url=video.get('thumbnail_url', ''))
        embed.add_field(name='Posição', value=f'{st.playlist_index + 1}/{total}', inline=True)
        embed.add_field(name='Volume', value=f'{int(st.voice_volume * 100)}%', inline=True)
        embed.add_field(
            name='Shuffle', value='🔀 Ligado' if st.shuffle_mode else 'Desligado', inline=True
        )
        embed.set_footer(text='Use os botões abaixo para controlar a reprodução.')
        return embed

    async def _enviar_embed_tocando(self, ctx, video: dict, total: int, st) -> None:
        """Atualiza o card de status único com o player (progresso + controles)."""
        self._current_video = video
        self._current_total = total
        embed = self._construir_embed_tocando(video, total, st)
        await self._get_status_message(ctx, embed)
        self._iniciar_progress_loop(ctx)

    async def atualizar_status_agora(self, ctx) -> None:
        """Força a atualização imediata do card (ex: após pausar, mudar volume/repeat)."""
        if not self._current_video:
            return
        embed = self._construir_embed_tocando(self._current_video, self._current_total, self.state)
        await self._get_status_message(ctx, embed)

    async def marcar_parado(self, ctx) -> None:
        """Atualiza o card de status para refletir que a reprodução foi parada."""
        self._parar_progress_loop()
        self._current_video = None
        embed = embed_erro('⏹️ Reprodução parada.')
        try:
            await self._get_status_message(ctx, embed)
        except discord.HTTPException as e:
            logger.debug(f'[STATUS_MSG] falha ao marcar como parado: {e}')

    def _iniciar_progress_loop(self, ctx) -> None:
        self._parar_progress_loop()
        self.state._progress_task = asyncio.create_task(self._progress_loop(ctx))

    def _parar_progress_loop(self) -> None:
        task = self.state._progress_task
        if task and not task.done():
            task.cancel()

    async def _progress_loop(self, ctx) -> None:
        """A cada alguns segundos, atualiza o card com o progresso atual da faixa."""
        try:
            while self.state.is_playing_voice:
                await asyncio.sleep(PROGRESS_UPDATE_INTERVAL_SECONDS)
                if not self.state.is_playing_voice or not self._current_video:
                    break
                embed = self._construir_embed_tocando(
                    self._current_video, self._current_total, self.state
                )
                try:
                    await self._get_status_message(ctx, embed)
                except discord.HTTPException as e:
                    logger.debug(f'[PROGRESS] falha ao atualizar progresso: {e}')
        except asyncio.CancelledError:
            pass

    # ------------------------------------------------------------------
    # Auto-avanço
    # ------------------------------------------------------------------

    async def _auto_next(self, ctx) -> None:
        """Chamado automaticamente ao terminar uma música."""
        st = self.state
        self._parar_status_loop()
        self._parar_progress_loop()
        if not st.is_playing_voice:
            return

        # --- Repeat ONE: repete a música atual sem marcar como tocada ---
        if st.repeat_mode == RepeatMode.ONE:
            await self.tocar_atual(ctx)
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
                if st.repeat_mode == RepeatMode.ALL:
                    for v in playlist:
                        v['tocado'] = False
                    self.repo.save(playlist)
                    st.playlist_index = 0
                    await self.tocar_atual(ctx)
                    return
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
                if st.repeat_mode == RepeatMode.ALL:
                    for v in playlist:
                        v['tocado'] = False
                    self.repo.save(playlist)
                    st.playlist_index = 0
                    await self.tocar_atual(ctx)
                    return
                st.playlist_index = 0
                st.is_playing_voice = False
                await ctx.send(
                    embed=embed_aviso('📋 Playlist terminou! Use `&tocar` para recomeçar.')
                )
                return

        await self.tocar_atual(ctx)
