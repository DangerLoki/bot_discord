"""Utilitários para os Cogs acessarem serviços multi-guild."""
import discord
from discord.ext import commands


class MultiGuildCog(commands.Cog):
    """Base para Cogs que precisam de acesso a serviços multi-guild."""

    def __init__(self, bot, get_or_create_guild_services, guild_states):
        self.bot = bot
        self._get_or_create_guild_services = get_or_create_guild_services
        self._guild_states = guild_states

    def get_services_for_guild(self, guild_id: int):
        """Obtém ou cria serviços para um servidor."""
        return self._get_or_create_guild_services(guild_id)

    def get_state_for_guild(self, guild_id: int):
        """Obtém o estado do player para um servidor."""
        if guild_id not in self._guild_states:
            self.get_services_for_guild(guild_id)  # Cria se não existir
        return self._guild_states.get(guild_id)

    def get_services_from_ctx(self, ctx: commands.Context):
        """Helper: obtém serviços a partir do contexto do comando."""
        if not ctx.guild:
            return None, None
        return self.get_services_for_guild(ctx.guild.id)

    def get_state_from_ctx(self, ctx: commands.Context):
        """Helper: obtém estado a partir do contexto do comando."""
        if not ctx.guild:
            return None
        return self.get_state_for_guild(ctx.guild.id)
