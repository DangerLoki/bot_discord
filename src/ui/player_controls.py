"""View persistente com botões (emotes) que controlam o player diretamente no painel,
sem precisar digitar comandos — similar ao que bots como Rythm/Jockie Music oferecem.
"""
import unicodedata

import discord

from src.logger import get_logger
from src.models.player_state import RepeatMode

logger = get_logger(__name__)


class _InteractionCtx:
    """Adapta uma Interaction para a interface mínima (send/channel/guild/author)
    que os serviços de playlist/player já esperam de um `ctx` de comando.
    """

    def __init__(self, interaction: discord.Interaction) -> None:
        self.interaction = interaction
        self.channel = interaction.channel
        self.guild = interaction.guild
        self.author = interaction.user
        self.bot = interaction.client

    async def send(self, *args, **kwargs):
        return await self.channel.send(*args, **kwargs)


class AdicionarMusicaModal(discord.ui.Modal, title='Adicionar música'):
    """Modal para adicionar música sem precisar digitar no chat (que é limpo
    periodicamente). Aceita URL do YouTube/Spotify ou um termo de busca.
    """

    entrada = discord.ui.TextInput(
        label='Link ou nome da música',
        placeholder='Cole uma URL do YouTube/Spotify ou digite o nome da música...',
        required=True,
        max_length=500,
    )

    def __init__(self, playlist_svc) -> None:
        super().__init__()
        self.playlist_svc = playlist_svc

    async def on_submit(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer()
        ctx = _InteractionCtx(interaction)
        await self.playlist_svc.adicionar_entrada(ctx, self.entrada.value, interaction.client)

    async def on_error(self, interaction: discord.Interaction, error: Exception) -> None:
        logger.error(f'[ADD MODAL] erro ao processar entrada: {error}', exc_info=error)
        if not interaction.response.is_done():
            await interaction.response.defer()
        await interaction.channel.send('❌ Ocorreu um erro ao adicionar a música. Tente novamente.')


class PlayerControlView(discord.ui.View):
    """Botões persistentes equivalentes aos comandos de texto do player."""

    def __init__(
        self, state, player_svc, playlist_svc, *, service_resolver=None
    ) -> None:
        super().__init__(timeout=None)
        self.state = state
        self.player_svc = player_svc
        self.playlist_svc = playlist_svc
        self._service_resolver = service_resolver

    def _services_for(self, interaction: discord.Interaction):
        """Resolve os serviços pela guild para callbacks persistentes."""
        if self._service_resolver and interaction.guild:
            playlist_svc, player_svc = self._service_resolver(interaction.guild.id)
            return player_svc.state, player_svc, playlist_svc
        return self.state, self.player_svc, self.playlist_svc

    @staticmethod
    async def _ack(interaction: discord.Interaction) -> None:
        try:
            await interaction.response.defer()
        except discord.HTTPException:
            pass

    def sincronizar_estado(self, state) -> None:
        """Reflete visualmente reprodução, shuffle, repeat e stop."""
        vc = state.voice_client
        pausado = bool(vc and vc.is_paused())
        tocando = bool(vc and vc.is_playing())
        self.pausar_retomar.emoji = '⏸️' if tocando else '▶️'
        self.pausar_retomar.style = (
            discord.ButtonStyle.success if pausado else discord.ButtonStyle.primary
        )

        self.alternar_shuffle.style = (
            discord.ButtonStyle.success
            if state.shuffle_mode
            else discord.ButtonStyle.secondary
        )

        if state.repeat_mode == RepeatMode.ONE:
            self.alternar_repeat.emoji = '🔂'
            self.alternar_repeat.style = discord.ButtonStyle.success
        elif state.repeat_mode == RepeatMode.ALL:
            self.alternar_repeat.emoji = '🔁'
            self.alternar_repeat.style = discord.ButtonStyle.primary
        else:
            self.alternar_repeat.emoji = '🔁'
            self.alternar_repeat.style = discord.ButtonStyle.secondary

        if state.saiu_pausado:
            self.parar.emoji = '📞'
            self.parar.style = discord.ButtonStyle.success
        else:
            self.parar.emoji = '⏹️'
            self.parar.style = discord.ButtonStyle.danger

    # ------------------------------------------------------------------
    # Linha 1 — transporte
    # ------------------------------------------------------------------

    @discord.ui.button(emoji='⏮️', style=discord.ButtonStyle.secondary, custom_id='player:previous', row=0)
    async def anterior(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await self._ack(interaction)
        ctx = _InteractionCtx(interaction)
        state, player_svc, playlist_svc = self._services_for(interaction)
        await playlist_svc.voltar_video(ctx, announce=False)
        if state.voice_client and state.voice_client.is_connected():
            await player_svc.tocar_atual(ctx)

    @discord.ui.button(emoji='⏯️', style=discord.ButtonStyle.primary, custom_id='player:playpause', row=0)
    async def pausar_retomar(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await self._ack(interaction)
        ctx = _InteractionCtx(interaction)
        state, player_svc, _ = self._services_for(interaction)
        vc = state.voice_client
        if vc and vc.is_playing():
            vc.pause()
            state.pausar_rastreio()
            await player_svc.atualizar_status_agora(ctx)
            return
        if vc and vc.is_paused():
            vc.resume()
            state.retomar_rastreio()
            await player_svc.atualizar_status_agora(ctx)
            return

        canal_voz = interaction.user.voice.channel if interaction.user.voice else None
        if not canal_voz:
            await ctx.send('❌ Você precisa estar em um canal de voz para iniciar a reprodução.')
            return

        if state.saiu_pausado:
            await player_svc.voltar_e_retomar(ctx, canal_voz)
            return

        if not vc or not vc.is_connected():
            state.voice_client = await canal_voz.connect()
            state.voice_bot = interaction.client
        await player_svc.tocar_atual(ctx)

    @discord.ui.button(emoji='⏭️', style=discord.ButtonStyle.secondary, custom_id='player:skip', row=0)
    async def pular(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await self._ack(interaction)
        ctx = _InteractionCtx(interaction)
        state, player_svc, playlist_svc = self._services_for(interaction)
        conectado = bool(state.voice_client and state.voice_client.is_connected())
        await playlist_svc.pular_video(ctx, announce=False)
        if conectado:
            await player_svc.tocar_atual(ctx)

    @discord.ui.button(emoji='⏹️', style=discord.ButtonStyle.danger, custom_id='player:stop', row=0)
    async def parar(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await self._ack(interaction)
        ctx = _InteractionCtx(interaction)
        state, player_svc, _ = self._services_for(interaction)
        if state.saiu_pausado:
            canal_voz = interaction.user.voice.channel if interaction.user.voice else None
            if not canal_voz:
                await ctx.send('❌ Você precisa estar em um canal de voz para me trazer de volta.')
                return
            await player_svc.voltar_e_retomar(ctx, canal_voz)
        else:
            await player_svc.pausar_e_sair_da_call(ctx)

    # ------------------------------------------------------------------
    # Linha 2 — modos e volume
    # ------------------------------------------------------------------

    @discord.ui.button(emoji='🔀', style=discord.ButtonStyle.secondary, custom_id='player:shuffle', row=1)
    async def alternar_shuffle(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await self._ack(interaction)
        ctx = _InteractionCtx(interaction)
        _, _, playlist_svc = self._services_for(interaction)
        await playlist_svc.toggle_shuffle(ctx, silencioso=True)

    @discord.ui.button(emoji='🔁', style=discord.ButtonStyle.secondary, custom_id='player:repeat', row=1)
    async def alternar_repeat(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await self._ack(interaction)
        state, player_svc, _ = self._services_for(interaction)
        cycle = {
            RepeatMode.OFF: RepeatMode.ONE,
            RepeatMode.ONE: RepeatMode.ALL,
            RepeatMode.ALL: RepeatMode.OFF,
        }
        state.repeat_mode = cycle[state.repeat_mode]
        await player_svc.atualizar_status_agora(_InteractionCtx(interaction))

    @discord.ui.button(emoji='🔉', style=discord.ButtonStyle.secondary, custom_id='player:voldown', row=1)
    async def volume_menos(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await self._ack(interaction)
        state, player_svc, _ = self._services_for(interaction)
        state.voice_volume = max(0.0, round(state.voice_volume - 0.1, 2))
        if state.voice_client and state.voice_client.source:
            state.voice_client.source.volume = state.voice_volume
        await player_svc.persistir_estado()
        await player_svc.atualizar_status_agora(_InteractionCtx(interaction))

    @discord.ui.button(emoji='🔊', style=discord.ButtonStyle.secondary, custom_id='player:volup', row=1)
    async def volume_mais(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await self._ack(interaction)
        state, player_svc, _ = self._services_for(interaction)
        state.voice_volume = min(2.0, round(state.voice_volume + 0.1, 2))
        if state.voice_client and state.voice_client.source:
            state.voice_client.source.volume = state.voice_volume
        await player_svc.persistir_estado()
        await player_svc.atualizar_status_agora(_InteractionCtx(interaction))


class ConfirmarLimpezaView(discord.ui.View):
    """Confirma uma operação destrutiva antes de esvaziar a fila."""

    def __init__(self, playlist_svc, autor_id: int | None) -> None:
        super().__init__(timeout=30)
        self.playlist_svc = playlist_svc
        self.autor_id = autor_id

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if self.autor_id is None or interaction.user.id == self.autor_id:
            return True
        await interaction.response.send_message(
            '❌ Somente quem solicitou a limpeza pode confirmar.', ephemeral=True
        )
        return False

    @discord.ui.button(label='Limpar fila', emoji='🗑️', style=discord.ButtonStyle.danger)
    async def confirmar(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        await interaction.response.defer()
        await self.playlist_svc.limpar_playlist(_InteractionCtx(interaction))
        try:
            await interaction.message.delete()
        except (discord.NotFound, discord.HTTPException):
            pass
        self.stop()

    @discord.ui.button(label='Cancelar', style=discord.ButtonStyle.secondary)
    async def cancelar(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        await interaction.response.defer()
        try:
            await interaction.message.delete()
        except (discord.NotFound, discord.HTTPException):
            pass
        self.stop()


class PromoverMusicaSelect(discord.ui.Select):
    """Seletor da faixa que deve se tornar a próxima da fila."""

    def __init__(self, parent: 'PromoverMusicaView') -> None:
        self.parent_view = parent
        super().__init__(
            placeholder='Escolha a música que será a próxima...',
            min_values=1,
            max_values=1,
            options=[],
            row=0,
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        await self.parent_view.promover_selecionada(interaction, self.values[0])


class PromoverMusicaView(discord.ui.View):
    """Menu paginado para promover músicas sem digitar comandos.

    O Discord limita selects a 25 opções. A view pagina a fila inteira e usa o
    ID do vídeo como valor sempre que possível, evitando selecionar outra faixa
    caso a fila mude enquanto o menu está aberto.
    """

    PAGE_SIZE = 25

    def __init__(
        self,
        playlist_svc,
        autor_id: int | None,
        *,
        termo_busca: str | None = None,
    ) -> None:
        super().__init__(timeout=90)
        self.playlist_svc = playlist_svc
        self.autor_id = autor_id
        self.termo_busca = termo_busca.strip() if termo_busca else None
        self.pagina = 0
        candidatos = self._carregar_candidatos()
        if self.termo_busca:
            termo_normalizado = self._normalizar_busca(self.termo_busca)
            candidatos = [
                candidato
                for candidato in candidatos
                if termo_normalizado
                in self._normalizar_busca(candidato[1].get('titulo') or '')
            ]
        self.candidatos = candidatos
        self.seletor = PromoverMusicaSelect(self)
        self.add_item(self.seletor)
        if not self.termo_busca:
            self.remove_item(self.mostrar_todas)
        self._sincronizar_componentes()

    def _carregar_candidatos(self) -> list[tuple[int, dict]]:
        playlist = self.playlist_svc.repo.load(self.playlist_svc.state.guild_id)
        st = self.playlist_svc.state
        if st.shuffle_mode and st.shuffle_playlist:
            ordem = [
                indice
                for indice in st.shuffle_playlist
                if 0 <= indice < len(playlist)
            ]
        else:
            ordem = list(range(len(playlist)))

        return [
            (posicao, playlist[indice])
            for posicao, indice in enumerate(ordem, 1)
            if indice != st.playlist_index
        ]

    @property
    def total_paginas(self) -> int:
        return max(1, (len(self.candidatos) + self.PAGE_SIZE - 1) // self.PAGE_SIZE)

    @staticmethod
    def _texto_curto(texto: str, limite: int) -> str:
        if len(texto) <= limite:
            return texto
        return texto[: limite - 1].rstrip() + '…'

    @staticmethod
    def _normalizar_busca(texto: str) -> str:
        sem_acentos = ''.join(
            caractere
            for caractere in unicodedata.normalize('NFKD', texto)
            if not unicodedata.combining(caractere)
        )
        return sem_acentos.casefold().strip()

    def _opcoes_da_pagina(self) -> list[discord.SelectOption]:
        inicio = self.pagina * self.PAGE_SIZE
        fim = inicio + self.PAGE_SIZE
        opcoes = []
        for posicao, video in self.candidatos[inicio:fim]:
            titulo = video.get('titulo') or 'Desconhecido'
            video_id = video.get('video_id')
            valor = str(video_id) if video_id else str(posicao)
            canal = video.get('canal') or 'Canal desconhecido'
            opcoes.append(
                discord.SelectOption(
                    label=self._texto_curto(f'{posicao}. {titulo}', 100),
                    value=self._texto_curto(valor, 100),
                    description=self._texto_curto(canal, 100),
                    emoji='⏫',
                )
            )
        return opcoes

    def _sincronizar_componentes(self) -> None:
        self.seletor.options = self._opcoes_da_pagina()
        self.seletor.placeholder = (
            f'Escolha a próxima música · página {self.pagina + 1}/{self.total_paginas}'
        )
        self.pagina_anterior.disabled = self.pagina == 0
        self.proxima_pagina.disabled = self.pagina >= self.total_paginas - 1

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if self.autor_id is None or interaction.user.id == self.autor_id:
            return True
        await interaction.response.send_message(
            '❌ Abra o seu próprio menu de promoção para escolher uma música.',
            ephemeral=True,
        )
        return False

    async def promover_selecionada(
        self, interaction: discord.Interaction, entrada: str
    ) -> None:
        await interaction.response.defer()
        video_id_exato = next(
            (
                str(video.get('video_id'))
                for _, video in self.candidatos
                if video.get('video_id') is not None
                and str(video.get('video_id')) == entrada
            ),
            None,
        )
        await self.playlist_svc.promover_video(
            _InteractionCtx(interaction),
            entrada if video_id_exato is None else None,
            interaction.client,
            video_id_exato=video_id_exato,
        )
        await interaction.edit_original_response(
            content='✅ Seleção processada. A fila foi atualizada.', view=None
        )
        self.stop()

    @discord.ui.button(
        label='Anterior', emoji='◀️', style=discord.ButtonStyle.secondary, row=1
    )
    async def pagina_anterior(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        self.pagina = max(0, self.pagina - 1)
        self._sincronizar_componentes()
        await interaction.response.edit_message(view=self)

    @discord.ui.button(
        label='Próxima', emoji='▶️', style=discord.ButtonStyle.secondary, row=1
    )
    async def proxima_pagina(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        self.pagina = min(self.total_paginas - 1, self.pagina + 1)
        self._sincronizar_componentes()
        await interaction.response.edit_message(view=self)

    @discord.ui.button(
        label='Buscar por nome',
        emoji='🔍',
        style=discord.ButtonStyle.primary,
        row=1,
    )
    async def buscar_por_nome(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        await interaction.response.send_modal(
            BuscarPromocaoModal(self.playlist_svc, self.autor_id, self)
        )

    @discord.ui.button(
        label='Ver todas',
        emoji='📋',
        style=discord.ButtonStyle.secondary,
        row=1,
    )
    async def mostrar_todas(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        view = PromoverMusicaView(self.playlist_svc, self.autor_id)
        await interaction.response.edit_message(
            content='Escolha a música que deve tocar em seguida:', view=view
        )
        self.stop()


class BuscarPromocaoModal(discord.ui.Modal, title='Buscar música na fila'):
    """Pesquisa músicas e devolve os resultados no seletor de promoção."""

    consulta = discord.ui.TextInput(
        label='Nome da música',
        placeholder='Digite parte do nome da música...',
        required=True,
        min_length=2,
        max_length=100,
    )

    def __init__(self, playlist_svc, autor_id: int | None, view_origem) -> None:
        super().__init__()
        self.playlist_svc = playlist_svc
        self.autor_id = autor_id
        self.view_origem = view_origem

    async def on_submit(self, interaction: discord.Interaction) -> None:
        termo = self.consulta.value.strip()
        if len(termo) < 2:
            await interaction.response.edit_message(
                content='⚠️ Digite pelo menos 2 caracteres para pesquisar.',
                view=self.view_origem,
            )
            return
        view = PromoverMusicaView(
            self.playlist_svc,
            self.autor_id,
            termo_busca=termo,
        )
        if not view.candidatos:
            await interaction.response.edit_message(
                content=(
                    f'⚠️ Nenhuma música encontrada para **{termo}**. '
                    'Tente buscar outro nome.'
                ),
                view=self.view_origem,
            )
            return
        await interaction.response.edit_message(
            content=(
                f'🔍 **{len(view.candidatos)}** resultado(s) para '
                f'**{termo}**. Escolha a próxima música:'
            ),
            view=view,
        )
        self.view_origem.stop()

    async def on_error(
        self, interaction: discord.Interaction, error: Exception
    ) -> None:
        logger.error(f'[PROMOTE SEARCH] erro ao pesquisar: {error}', exc_info=error)
        if interaction.response.is_done():
            await interaction.followup.send(
                '❌ Não foi possível pesquisar a fila. Tente novamente.', ephemeral=True
            )
        else:
            await interaction.response.send_message(
                '❌ Não foi possível pesquisar a fila. Tente novamente.', ephemeral=True
            )


class PlaylistQueueView(discord.ui.View):
    """Botões persistentes anexados à mensagem da fila de reprodução."""

    def __init__(
        self, state, player_svc, playlist_svc, *, service_resolver=None
    ) -> None:
        super().__init__(timeout=None)
        self.state = state
        self.player_svc = player_svc
        self.playlist_svc = playlist_svc
        self._service_resolver = service_resolver

    def _services_for(self, interaction: discord.Interaction):
        """Resolve os serviços pela guild para callbacks persistentes."""
        if self._service_resolver and interaction.guild:
            playlist_svc, player_svc = self._service_resolver(interaction.guild.id)
            return player_svc.state, player_svc, playlist_svc
        return self.state, self.player_svc, self.playlist_svc

    @staticmethod
    async def _ack(interaction: discord.Interaction) -> None:
        try:
            await interaction.response.defer()
        except discord.HTTPException:
            pass

    def sincronizar_paginacao(self, tem_anterior: bool, tem_proxima: bool) -> None:
        self.pagina_anterior.disabled = not tem_anterior
        self.proxima_pagina.disabled = not tem_proxima

    @discord.ui.button(emoji='◀️', style=discord.ButtonStyle.secondary, custom_id='playlist:prev_page', row=0)
    async def pagina_anterior(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await self._ack(interaction)
        _, player_svc, _ = self._services_for(interaction)
        await player_svc.mudar_pagina_playlist(_InteractionCtx(interaction), -1)

    @discord.ui.button(emoji='🔃', style=discord.ButtonStyle.secondary, custom_id='playlist:flip', row=0)
    async def inverter(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await self._ack(interaction)
        ctx = _InteractionCtx(interaction)
        _, _, playlist_svc = self._services_for(interaction)
        await playlist_svc.inverter_playlist(ctx, silencioso=True)

    @discord.ui.button(emoji='▶️', style=discord.ButtonStyle.secondary, custom_id='playlist:next_page', row=0)
    async def proxima_pagina(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await self._ack(interaction)
        _, player_svc, _ = self._services_for(interaction)
        await player_svc.mudar_pagina_playlist(_InteractionCtx(interaction), 1)

    @discord.ui.button(emoji='➕', style=discord.ButtonStyle.success, custom_id='playlist:add', row=1)
    async def adicionar(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        # Não usa _ack aqui: abrir um modal precisa ser a resposta inicial da interação.
        _, _, playlist_svc = self._services_for(interaction)
        await interaction.response.send_modal(AdicionarMusicaModal(playlist_svc))

    @discord.ui.button(
        label='Promover',
        emoji='⏫',
        style=discord.ButtonStyle.primary,
        custom_id='playlist:promote',
        row=1,
    )
    async def promover(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        _, _, playlist_svc = self._services_for(interaction)
        view = PromoverMusicaView(playlist_svc, interaction.user.id)
        if not view.candidatos:
            await interaction.response.send_message(
                '⚠️ Não há outra música na fila para promover.', ephemeral=True
            )
            return
        await interaction.response.send_message(
            'Escolha a música que deve tocar em seguida:',
            ephemeral=True,
            view=view,
        )

    @discord.ui.button(emoji='🗑️', style=discord.ButtonStyle.danger, custom_id='playlist:clear', row=1)
    async def limpar_playlist(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        _, _, playlist_svc = self._services_for(interaction)
        await interaction.response.send_message(
            '⚠️ Tem certeza de que deseja remover todas as músicas da fila?',
            ephemeral=True,
            view=ConfirmarLimpezaView(playlist_svc, interaction.user.id),
        )
