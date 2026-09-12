"""Estado mutável do player de áudio.

Centraliza toda variável de runtime do player num único objeto,
eliminando atributos espalhados por classes herdadas.
"""
import asyncio
import time
from enum import Enum
from typing import Optional


class RepeatMode(Enum):
    OFF = "off"          # sem repetição
    ONE = "one"          # repete a música atual
    ALL = "all"          # repete a playlist inteira


class PlayerState:
    """Único ponto de verdade sobre o estado atual da reprodução - por servidor (guild)."""

    def __init__(self, guild_id: int) -> None:
        self.guild_id = guild_id

        # Voice
        self.voice_client = None
        self.voice_bot = None
        self.voice_volume: float = 0.25

        # Flags
        self.is_playing_voice: bool = False
        self.repeat_mode: RepeatMode = RepeatMode.OFF

        # Pausado e fora da call (botão ⏹️/📞 do painel): a reprodução foi
        # pausada e o bot desconectou, aguardando alguém trazê-lo de volta.
        self.saiu_pausado: bool = False

        # Navegação na playlist
        self.playlist_index: int = 0

        # Shuffle
        self.shuffle_mode: bool = False
        self.shuffle_playlist: list[int] = []
        self.shuffle_index: int = 0
        self.shuffle_id: Optional[str] = None

        # Lock de carregamento (evita duas músicas carregando ao mesmo tempo)
        self.carregando: asyncio.Lock = asyncio.Lock()

        # Rastreio de tempo (para presença)
        self._playback_start: Optional[float] = None
        self._playback_paused_at: Optional[float] = None
        self._playback_duracao: int = 0
        self._status_titulo: str = ''
        self._status_task: Optional[asyncio.Task] = None
        self._progress_task: Optional[asyncio.Task] = None

        # Canal dedicado ao painel do player (comandos + status)
        self.player_channel_id: Optional[int] = None
        self._cleanup_task: Optional[asyncio.Task] = None

    def to_dict(self) -> dict:
        """Serializa estado persistível para dict."""
        return {
            'voice_volume': self.voice_volume,
            'repeat_mode': self.repeat_mode.value,
            'playlist_index': self.playlist_index,
            'shuffle_mode': self.shuffle_mode,
            'shuffle_index': self.shuffle_index,
            'shuffle_id': self.shuffle_id,
            'player_channel_id': self.player_channel_id,
        }

    def from_dict(self, data: dict) -> None:
        """Restaura estado a partir de dict."""
        if data is None:
            return
        self.voice_volume = data.get('voice_volume', 0.25)
        repeat_str = data.get('repeat_mode', 'off')
        self.repeat_mode = RepeatMode(repeat_str)
        self.playlist_index = data.get('playlist_index', 0)
        self.shuffle_mode = data.get('shuffle_mode', False)
        self.shuffle_index = data.get('shuffle_index', 0)
        self.shuffle_id = data.get('shuffle_id')
        self.player_channel_id = data.get('player_channel_id')

    # ------------------------------------------------------------------
    # Rastreio de tempo
    # ------------------------------------------------------------------

    def iniciar_rastreio_tempo(self, duracao_total: int) -> None:
        self._playback_start = time.monotonic()
        self._playback_paused_at = None
        self._playback_duracao = duracao_total

    def tempo_decorrido(self) -> int:
        if self._playback_start is None:
            return 0
        if self._playback_paused_at is not None:
            return int(self._playback_paused_at - self._playback_start)
        return int(time.monotonic() - self._playback_start)

    def pausar_rastreio(self) -> None:
        if self._playback_start is not None and self._playback_paused_at is None:
            self._playback_paused_at = time.monotonic()

    def retomar_rastreio(self) -> None:
        if self._playback_paused_at is not None:
            pausa = time.monotonic() - self._playback_paused_at
            self._playback_start = (self._playback_start or 0) + pausa
            self._playback_paused_at = None
