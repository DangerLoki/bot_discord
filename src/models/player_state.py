"""Estado mutável do player de áudio.

Centraliza toda variável de runtime do player num único objeto,
eliminando atributos espalhados por mixins.
"""
import asyncio
import time
from typing import Optional


class PlayerState:
    """Único ponto de verdade sobre o estado atual da reprodução."""

    def __init__(self) -> None:
        # Voice
        self.voice_client = None
        self.voice_bot = None
        self.voice_volume: float = 0.25

        # Flags
        self.is_playing_voice: bool = False

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
