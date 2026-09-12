"""Cog de diagnóstico do bot."""
from pathlib import Path

import discord
from discord.ext import commands

from src.logger import get_logger
from src.services.spotify_service import SpotifyService
from src.utils import HealthCheck

logger = get_logger(__name__)


class DiagnosticCog(commands.Cog, name='Diagnóstico'):
    """Comandos de diagnóstico e healthcheck."""

    def __init__(
        self,
        bot: commands.Bot,
        cache_dir: Path,
        cookies_file: str,
        spotify_svc: SpotifyService,
    ) -> None:
        self.bot = bot
        self.cache_dir = cache_dir
        self.cookies_file = cookies_file
        self.spotify_svc = spotify_svc

    @commands.hybrid_command(name='healthcheck', aliases=['health', 'diag', 'status'])
    async def healthcheck(self, ctx: commands.Context) -> None:
        """Executa diagnóstico de dependências críticas."""
        async with ctx.typing():
            checks = {
                'FFmpeg': HealthCheck.check_ffmpeg(),
                'Cache': HealthCheck.check_cache_dir(self.cache_dir),
                'Cookies': HealthCheck.check_cookies(self.cookies_file),
            }
            spotify_ok, spotify_msg = await HealthCheck.check_spotify(self.spotify_svc)
            checks['Spotify'] = (spotify_ok, spotify_msg)

            embed = discord.Embed(title='🔍 Healthcheck do Bot', color=0x5865F2)
            status_emoji = {'ffmpeg': HealthCheck.check_ffmpeg()[0]}

            lines = []
            all_ok = True
            for name, (ok, msg) in checks.items():
                emoji = '✅' if ok else '❌'
                lines.append(f'{emoji} **{name}**: {msg}')
                if not ok:
                    all_ok = False

            embed.description = '\n'.join(lines)
            color = 0x57F287 if all_ok else 0xED4245
            embed.color = color

            await ctx.send(embed=embed)
