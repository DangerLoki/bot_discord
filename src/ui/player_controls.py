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


class PlayerControlView(discord.ui.View):
    """Botões persistentes equivalentes aos comandos de texto do player."""

    def __init__(self, state, player_svc, playlist_svc) -> None:
        super().__init__(timeout=None)
        self.state = state
        self.player_svc = player_svc
        self.playlist_svc = playlist_svc

    @staticmethod
    async def _ack(interaction: discord.Interaction) -> None:
        try:
            await interaction.response.defer()
        except discord.HTTPException:
            pass

    # ------------------------------------------------------------------
    # Linha 1 — transporte
    # ------------------------------------------------------------------

    @discord.ui.button(emoji='⏮️', style=discord.ButtonStyle.secondary, custom_id='player:previous', row=0)
    async def anterior(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await self._ack(interaction)
        ctx = _InteractionCtx(interaction)
        await self.playlist_svc.voltar_video(ctx, announce=False)
        if self.state.voice_client and self.state.voice_client.is_connected():
            await self.player_svc.tocar_atual(ctx)

    @discord.ui.button(emoji='⏯️', style=discord.ButtonStyle.primary, custom_id='player:playpause', row=0)
    async def pausar_retomar(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await self._ack(interaction)
        vc = self.state.voice_client
        if not vc:
            return
        if vc.is_playing():
            vc.pause()
            self.state.pausar_rastreio()
        elif vc.is_paused():
            vc.resume()
            self.state.retomar_rastreio()
        else:
            return
        await self.player_svc.atualizar_status_agora(_InteractionCtx(interaction))

    @discord.ui.button(emoji='⏭️', style=discord.ButtonStyle.secondary, custom_id='player:skip', row=0)
    async def pular(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await self._ack(interaction)
        ctx = _InteractionCtx(interaction)
        conectado = bool(self.state.voice_client and self.state.voice_client.is_connected())
        await self.playlist_svc.pular_video(ctx, announce=False)
        if conectado:
            await self.player_svc.tocar_atual(ctx)

    @discord.ui.button(emoji='⏹️', style=discord.ButtonStyle.danger, custom_id='player:stop', row=0)
    async def parar(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await self._ack(interaction)
        vc = self.state.voice_client
        if vc and (vc.is_playing() or vc.is_paused()):
            self.state.is_playing_voice = False
            self.player_svc._parar_status_loop()
            vc.stop()
        await self.player_svc.marcar_parado(_InteractionCtx(interaction))

    # ------------------------------------------------------------------
    # Linha 2 — modos e volume
    # ------------------------------------------------------------------

    @discord.ui.button(emoji='🔀', style=discord.ButtonStyle.secondary, custom_id='player:shuffle', row=1)
    async def alternar_shuffle(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await self._ack(interaction)
        ctx = _InteractionCtx(interaction)
        await self.playlist_svc.toggle_shuffle(ctx, silencioso=True)
        await self.player_svc.atualizar_status_agora(ctx)

    @discord.ui.button(emoji='🔁', style=discord.ButtonStyle.secondary, custom_id='player:repeat', row=1)
    async def alternar_repeat(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await self._ack(interaction)
        cycle = {
            RepeatMode.OFF: RepeatMode.ONE,
            RepeatMode.ONE: RepeatMode.ALL,
            RepeatMode.ALL: RepeatMode.OFF,
        }
        self.state.repeat_mode = cycle[self.state.repeat_mode]
        await self.player_svc.atualizar_status_agora(_InteractionCtx(interaction))

    @discord.ui.button(emoji='🔉', style=discord.ButtonStyle.secondary, custom_id='player:voldown', row=1)
    async def volume_menos(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await self._ack(interaction)
        self.state.voice_volume = max(0.0, round(self.state.voice_volume - 0.1, 2))
        if self.state.voice_client and self.state.voice_client.source:
            self.state.voice_client.source.volume = self.state.voice_volume
        await self.player_svc.atualizar_status_agora(_InteractionCtx(interaction))

    @discord.ui.button(emoji='🔊', style=discord.ButtonStyle.secondary, custom_id='player:volup', row=1)
    async def volume_mais(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await self._ack(interaction)
        self.state.voice_volume = min(2.0, round(self.state.voice_volume + 0.1, 2))
        if self.state.voice_client and self.state.voice_client.source:
            self.state.voice_client.source.volume = self.state.voice_volume
        await self.player_svc.atualizar_status_agora(_InteractionCtx(interaction))


class PlaylistQueueView(discord.ui.View):
    """Botões persistentes anexados à mensagem da fila de reprodução."""

    def __init__(self, state, player_svc, playlist_svc) -> None:
        super().__init__(timeout=None)
        self.state = state
        self.player_svc = player_svc
        self.playlist_svc = playlist_svc

    @staticmethod
    async def _ack(interaction: discord.Interaction) -> None:
        try:
            await interaction.response.defer()
        except discord.HTTPException:
            pass

    @discord.ui.button(emoji='◀️', style=discord.ButtonStyle.secondary, custom_id='playlist:prev_page', row=0)
    async def pagina_anterior(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await self._ack(interaction)
        await self.player_svc.mudar_pagina_playlist(_InteractionCtx(interaction), -1)

    @discord.ui.button(emoji='🔃', style=discord.ButtonStyle.secondary, custom_id='playlist:flip', row=0)
    async def inverter(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await self._ack(interaction)
        ctx = _InteractionCtx(interaction)
        await self.playlist_svc.inverter_playlist(ctx, silencioso=True)
        playlist = self.playlist_svc.repo.load()
        await self.player_svc._atualizar_mensagem_playlist(ctx, playlist, self.state.playlist_index)
        if self.player_svc._current_video:
            await self.player_svc.atualizar_status_agora(ctx)

    @discord.ui.button(emoji='▶️', style=discord.ButtonStyle.secondary, custom_id='playlist:next_page', row=0)
    async def proxima_pagina(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await self._ack(interaction)
        await self.player_svc.mudar_pagina_playlist(_InteractionCtx(interaction), 1)
