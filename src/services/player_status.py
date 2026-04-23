"""Status e presença do bot durante a reprodução."""
import asyncio

import discord

from src.logger import get_logger
from src.utils import formatar_duracao

logger = get_logger(__name__)


class PlayerStatus:
    """Loop de atualização de presença durante a reprodução."""

    async def _atualizar_status(self, titulo: str, duracao: int) -> None:
        bot = self.state.voice_bot
        if not bot:
            return
        decorrido = formatar_duracao(self.state.tempo_decorrido())
        total = formatar_duracao(duracao)
        activity = discord.Activity(
            type=discord.ActivityType.listening,
            name=f'{titulo} [{decorrido}/{total}]',
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
        try:
            while self.state.is_playing_voice:
                titulo = self.state._status_titulo
                duracao = self.state._playback_duracao
                if titulo:
                    await self._atualizar_status(titulo, duracao)
                await asyncio.sleep(5)
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
