"""View persistente com botões (emotes) que controlam o player diretamente no painel,
sem precisar digitar comandos — similar ao que bots como Rythm/Jockie Music oferecem.
"""
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

    @discord.ui.button(emoji='🗑️', style=discord.ButtonStyle.danger, custom_id='playlist:clear', row=1)
    async def limpar_playlist(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        _, _, playlist_svc = self._services_for(interaction)
        await interaction.response.send_message(
            '⚠️ Tem certeza de que deseja remover todas as músicas da fila?',
            ephemeral=True,
            view=ConfirmarLimpezaView(playlist_svc, interaction.user.id),
        )
