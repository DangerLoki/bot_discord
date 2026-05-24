"""Status e presença do bot durante a reprodução."""
import asyncio
from datetime import datetime, timezone, timedelta

import discord

from src.logger import get_logger
from src.utils import formatar_duracao

logger = get_logger(__name__)


class PlayerStatus:
    """Loop de atualização de presença durante a reprodução."""

    async def _atualizar_status(self, titulo: str) -> None:
        """Define a presença com start timestamp para o Discord calcular o tempo."""
        bot = self.state.voice_bot
        if not bot:
            return
        decorrido = self.state.tempo_decorrido()
        start = datetime.now(timezone.utc) - timedelta(seconds=decorrido)
        duracao = self.state._playback_duracao
        name = f'{titulo} [{formatar_duracao(duracao)}]' if duracao else titulo
        activity = discord.Activity(
            type=discord.ActivityType.listening,
            name=name,
            start=start,
        )
        try:
            await bot.change_presence(activity=activity)
        except Exception:
            pass

    async def _limpar_status(self) -> None:
        bot = self.state.voice_bot
        if not bot:
            return
        try:
            await bot.change_presence(activity=None)
        except Exception:
            pass

    async def _status_loop(self) -> None:
        """Define a presença uma vez ao iniciar e refresca a cada 60s."""
        try:
            titulo = self.state._status_titulo
            if titulo:
                await self._atualizar_status(titulo)
            while self.state.is_playing_voice:
                await asyncio.sleep(60)
                titulo = self.state._status_titulo
                if self.state.is_playing_voice and titulo:
                    await self._atualizar_status(titulo)
        except asyncio.CancelledError:
            pass
        finally:
            await self._limpar_status()

    def _iniciar_status_loop(self) -> None:
        task = self.state._status_task
        if task and not task.done():
            task.cancel()
        loop = (
            self.state.voice_bot.loop
            if self.state.voice_bot
            else asyncio.get_event_loop()
        )
        self.state._status_task = loop.create_task(self._status_loop())

    def _parar_status_loop(self) -> None:
        task = self.state._status_task
        if task and not task.done():
            task.cancel()
