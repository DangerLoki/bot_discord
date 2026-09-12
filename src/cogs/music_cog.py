"""Cog de reprodução de áudio — comandos de voz (multi-guild)."""
import asyncio

import discord
from discord.ext import commands

from src.cogs.cog_utils import MultiGuildCog
from src.logger import get_logger
from src.models.player_state import RepeatMode, PlayerState
from src.repositories.config_repository import ConfigRepository
from src.repositories.playlist_repository import PlaylistRepository

logger = get_logger(__name__)


class MusicCog(MultiGuildCog, name='Música'):
    """Comandos de reprodução de áudio em canal de voz (multi-guild)."""

    def __init__(
        self,
        bot: commands.Bot,
        repo: PlaylistRepository,
        config_repo: ConfigRepository,
        get_or_create_guild_services,
        guild_states,
    ) -> None:
        super().__init__(bot, get_or_create_guild_services, guild_states)
        self.repo = repo
        self.config_repo = config_repo

    def _get_state(self, ctx):
        """Shortcut para pegar state do servidor."""
        return self.get_state_from_ctx(ctx)

    def _get_services(self, ctx):
        """Shortcut para pegar serviços do servidor."""
        playlist_svc, player_svc = self.get_services_from_ctx(ctx)
        return playlist_svc, player_svc

    # ------------------------------------------------------------------
    # Conexão
    # ------------------------------------------------------------------

    @commands.hybrid_command(name='entrar', aliases=['join', 'connect', 'entra'])
    async def entrar(self, ctx):
        """Bot entra no canal de voz do usuário."""
        if not ctx.author.voice:
            await ctx.send('❌ Você precisa estar em um canal de voz!')
            return
        canal = ctx.author.voice.channel

        if self._get_guild_state(ctx).voice_client and self._get_guild_state(ctx).voice_client.is_connected():
            if self._get_guild_state(ctx).voice_client.channel == canal:
                await ctx.send('⚠️ Já estou nesse canal!')
                return
            await self._get_guild_state(ctx).voice_client.move_to(canal)
            await ctx.send(f'🔄 Me movi para **{canal.name}**.')
            return

        self._get_guild_state(ctx).voice_client = await canal.connect()
        self._get_guild_state(ctx).voice_bot = self.bot
        await ctx.send(f'✅ Entrei em **{canal.name}**! Use `&tocar` para iniciar o áudio.')
        logger.info(f'[VOZ] Bot entrou em: {canal.name}')

    @commands.hybrid_command(name='sair', aliases=['leave', 'disconnect', 'dc'])
    async def sair(self, ctx):
        """Para o áudio e sai da call."""
        if self._get_guild_state(ctx).voice_client:
            self._get_guild_state(ctx).is_playing_voice = False
            self._get_guild_services(ctx)[1]._parar_status_loop()
            self._get_guild_state(ctx).voice_client.stop()
            await self._get_guild_state(ctx).voice_client.disconnect()
            self._get_guild_state(ctx).voice_client = None
            await self._get_guild_services(ctx)[1].marcar_parado(ctx)
            self._get_guild_services(ctx)[1].reset_status_message()
            await ctx.send('📴 Saí da call.')
            logger.info('[VOZ] Bot saiu da call.')
        else:
            await ctx.send('❌ Não estou em nenhum canal.')

    # ------------------------------------------------------------------
    # Canal de comandos
    # ------------------------------------------------------------------

    @commands.hybrid_command(name='definircanal', aliases=['setcanal', 'canalbot'])
    async def definircanal(self, ctx, canal: discord.TextChannel = None):
        """Define em qual canal o bot aceita comandos (usa o canal atual se nenhum for informado)."""
        if not ctx.guild:
            await ctx.send('❌ Esse comando só funciona em um servidor.')
            return

        canal_alvo = canal or ctx.channel
        self._get_guild_state(ctx).player_channel_id = canal_alvo.id
        self.config_repo.set_valor(ctx.guild.id, 'player_channel_id', canal_alvo.id)
        self._get_guild_services(ctx)[1].reset_status_message()
        self._get_guild_services(ctx)[1].iniciar_limpeza_canal(canal_alvo)

        await ctx.send(f'✅ Agora os comandos só são aceitos em {canal_alvo.mention}.')
        logger.info(f'[CANAL] canal de comandos definido: #{canal_alvo.name} ({canal_alvo.id})')

    @commands.hybrid_command(name='limparchat', aliases=['clearchat', 'purge'])
    async def limparchat(self, ctx, quantidade: int = 50):
        """Apaga as últimas mensagens do canal atual (padrão: 50, máx: 100)."""
        if not ctx.guild:
            await ctx.send('❌ Esse comando só funciona em um servidor.')
            return

        quantidade = max(1, min(quantidade, 100))
        try:
            apagadas = await ctx.channel.purge(limit=quantidade)
        except discord.Forbidden:
            await ctx.send('❌ Não tenho permissão para apagar mensagens neste canal.')
            return
        except discord.HTTPException as e:
            await ctx.send(f'❌ Erro ao apagar mensagens: {e}')
            return

        aviso = await ctx.send(f'🧹 {len(apagadas)} mensagem(ns) apagada(s).')
        logger.info(f'[LIMPARCHAT] {len(apagadas)} mensagens apagadas em #{ctx.channel} por {ctx.author}')
        await asyncio.sleep(3)
        try:
            await aviso.delete()
        except (discord.NotFound, discord.HTTPException):
            pass

    # ------------------------------------------------------------------
    # Reprodução
    # ------------------------------------------------------------------

    @commands.hybrid_command(name='tocar', aliases=['play', 'start'])
    async def tocar(self, ctx):
        """Começa a tocar o áudio da playlist na call."""
        if not self._get_guild_state(ctx).voice_client or not self._get_guild_state(ctx).voice_client.is_connected():
            if ctx.author.voice:
                self._get_guild_state(ctx).voice_client = await ctx.author.voice.channel.connect()
                self._get_guild_state(ctx).voice_bot = self.bot
            else:
                await ctx.send('❌ Não estou em nenhum canal! Use `&entrar` primeiro.')
                return
        await self._get_guild_services(ctx)[1].tocar_atual(ctx)

    @commands.hybrid_command(name='pausar', aliases=['pause'])
    async def pausar(self, ctx):
        """Pausa o áudio."""
        if self._get_guild_state(ctx).voice_client and self._get_guild_state(ctx).voice_client.is_playing():
            self._get_guild_state(ctx).voice_client.pause()
            self._get_guild_state(ctx).pausar_rastreio()
            await self._get_guild_services(ctx)[1].atualizar_status_agora(ctx)
        else:
            await ctx.send('❌ Nenhum áudio tocando.')

    @commands.hybrid_command(name='retomar', aliases=['resume', 'continuar'])
    async def retomar(self, ctx):
        """Retoma o áudio pausado."""
        if self._get_guild_state(ctx).voice_client and self._get_guild_state(ctx).voice_client.is_paused():
            self._get_guild_state(ctx).voice_client.resume()
            self._get_guild_state(ctx).retomar_rastreio()
            await self._get_guild_services(ctx)[1].atualizar_status_agora(ctx)
        else:
            await ctx.send('❌ Nenhum áudio pausado.')

    @commands.hybrid_command(name='parar', aliases=['stop'])
    async def parar(self, ctx):
        """Para o áudio sem sair da call."""
        if self._get_guild_state(ctx).voice_client and (
            self._get_guild_state(ctx).voice_client.is_playing() or self._get_guild_state(ctx).voice_client.is_paused()
        ):
            self._get_guild_state(ctx).is_playing_voice = False
            self._get_guild_services(ctx)[1]._parar_status_loop()
            self._get_guild_state(ctx).voice_client.stop()
            await self._get_guild_services(ctx)[1].marcar_parado(ctx)
        else:
            await ctx.send('❌ Nenhum áudio tocando.')

    @commands.hybrid_command(name='skip', aliases=['pular', 'next'])
    async def skip(self, ctx):
        """Pula para o próximo vídeo."""
        logger.info(f'[SKIP] solicitado por {ctx.author} em #{ctx.channel}')
        connected = bool(self._get_guild_state(ctx).voice_client and self._get_guild_state(ctx).voice_client.is_connected())
        await self._get_guild_services(ctx)[0].pular_video(ctx, announce=not connected)
        if connected:
            await self._get_guild_services(ctx)[1].tocar_atual(ctx)

    @commands.hybrid_command(name='previous', aliases=['voltar', 'anterior'])
    async def previous(self, ctx):
        """Volta ao vídeo anterior."""
        logger.info(f'[PREVIOUS] solicitado por {ctx.author} em #{ctx.channel}')
        await self._get_guild_services(ctx)[0].voltar_video(ctx)
        if self._get_guild_state(ctx).voice_client and self._get_guild_state(ctx).voice_client.is_connected():
            await self._get_guild_services(ctx)[1].tocar_atual(ctx)

    @commands.hybrid_command(name='recomecar', aliases=['restart', 'replay', 'reiniciar'])
    async def recomecar(self, ctx):
        """Recomeça a música atual do início."""
        logger.info(f'[RECOMECAR] solicitado por {ctx.author} em #{ctx.channel}')
        if not self._get_guild_state(ctx).voice_client or not self._get_guild_state(ctx).voice_client.is_connected():
            await ctx.send('❌ Não estou em nenhum canal de voz.')
            return
        await ctx.send('🔁 Recomeçando música atual...')
        await self._get_guild_services(ctx)[1].tocar_atual(ctx)

    @commands.command(name='repetir', aliases=['repeat', 'loop'])
    async def repetir(self, ctx, modo: str = None):
        """Define o modo de repetição: `musica`, `playlist` ou `off`."""
        modos_one = ('musica', 'music', '1', 'one', 'música')
        modos_all = ('playlist', 'all', 'todos', 'tudo', 'p')
        modos_off = ('off', 'não', 'nao', '0', 'desligar', 'none')

        if modo is None:
            # Cicla entre os modos: OFF -> ONE -> ALL -> OFF
            cycle = {
                RepeatMode.OFF: RepeatMode.ONE,
                RepeatMode.ONE: RepeatMode.ALL,
                RepeatMode.ALL: RepeatMode.OFF,
            }
            self._get_guild_state(ctx).repeat_mode = cycle[self._get_guild_state(ctx).repeat_mode]
        elif modo.lower() in modos_one:
            self._get_guild_state(ctx).repeat_mode = RepeatMode.ONE
        elif modo.lower() in modos_all:
            self._get_guild_state(ctx).repeat_mode = RepeatMode.ALL
        elif modo.lower() in modos_off:
            self._get_guild_state(ctx).repeat_mode = RepeatMode.OFF
        else:
            await ctx.send(
                '❌ Modo inválido. Use: `&repetir musica`, `&repetir playlist` ou `&repetir off`'
            )
            return

        mensagens = {
            RepeatMode.OFF: '⏹️ Repetição **desativada**.',
            RepeatMode.ONE: '🔂 Repetindo a **música atual**.',
            RepeatMode.ALL: '🔁 Repetindo a **playlist inteira**.',
        }
        await ctx.send(mensagens[self._get_guild_state(ctx).repeat_mode])
        await self._get_guild_services(ctx)[1].atualizar_status_agora(ctx)

    # ------------------------------------------------------------------
    # Volume
    # ------------------------------------------------------------------

    @commands.hybrid_command(name='volume', aliases=['vol', 'v'])
    async def volume(self, ctx, valor: int = None):
        """Ajusta o volume (0 a 200)."""
        if valor is None:
            porcentagem = int(self._get_guild_state(ctx).voice_volume * 100)
            await ctx.send(f'🔉 Volume atual: **{porcentagem}%**')
            return
        if not 0 <= valor <= 200:
            await ctx.send('❌ Volume deve ser entre **0** e **200**.')
            return
        self._get_guild_state(ctx).voice_volume = valor / 100.0
        if self._get_guild_state(ctx).voice_client and self._get_guild_state(ctx).voice_client.source:
            self._get_guild_state(ctx).voice_client.source.volume = self._get_guild_state(ctx).voice_volume
        await ctx.send(f'🔉 Volume ajustado para **{valor}%**.')
        await self._get_guild_services(ctx)[1].atualizar_status_agora(ctx)

    # ------------------------------------------------------------------
    # Now Playing
    # ------------------------------------------------------------------

    @commands.hybrid_command(name='tocando', aliases=['np', 'nowplaying', 'atual'])
    async def tocando(self, ctx):
        """Mostra o que está tocando na call."""
        vc = self._get_guild_state(ctx).voice_client
        if not vc or not vc.is_connected():
            await ctx.send('❌ Não estou em nenhum canal.')
            return
        if not vc.is_playing() and not vc.is_paused():
            await ctx.send('❌ Nenhum áudio tocando no momento.')
            return
        playlist = self.repo.load()
        if not playlist:
            await ctx.send('❌ Playlist vazia.')
            return
        index = (
            self._get_guild_state(ctx).playlist_index if self._get_guild_state(ctx).playlist_index < len(playlist) else 0
        )
        video = playlist[index]
        status = '⏸️ Pausado' if vc.is_paused() else '▶️ Tocando'
        embed = discord.Embed(
            title=f'{status} na Call',
            description=f"**[{video.get('titulo') or 'Desconhecido'}]({video.get('embed_url') or '#'})**",
            color=0x1DB954,
        )
        embed.set_thumbnail(url=video.get('thumbnail_url', ''))
        embed.add_field(name='Duração', value=video.get('duracao_formatada', '??:??'), inline=True)
        embed.add_field(name='Posição', value=f'{index + 1}/{len(playlist)}', inline=True)
        embed.add_field(name='Volume', value=f'{int(self._get_guild_state(ctx).voice_volume * 100)}%', inline=True)
        embed.add_field(name='Canal', value=video.get('canal', 'Desconhecido'), inline=True)
        await ctx.send(embed=embed)

    # ------------------------------------------------------------------
    # Help
    # ------------------------------------------------------------------

    @commands.hybrid_command(name='help', aliases=['ajuda', 'comandos', 'cmds'])
    async def help_cmd(self, ctx):
        """Lista todos os comandos disponíveis."""
        embed = discord.Embed(
            title='📖 Comandos do Bot',
            description='Prefixo: `&`',
            color=0x5865F2,
        )
        embed.add_field(
            name='🎵 Playlist',
            value=(
                '`&add <url|busca>` — Adiciona vídeo, playlist YouTube ou URL Spotify\n'
                '`&playlist <url>` — Adiciona playlist inteira do YouTube\n'
                '`&spotify <url>` — Adiciona faixa/álbum/playlist do Spotify 🐟\n'
                '`&listar` — Lista os vídeos (paginado)\n'
                '`&remove <pos|id>` — Remove um vídeo\n'
                '`&promover <pos|id|nome>` — Move para próxima posição\n'
                '`&limpar` — Limpa toda a playlist'
            ),
            inline=False,
        )
        embed.add_field(
            name='🔊 Reprodução de Voz',
            value=(
                '`&entrar` — Entra no seu canal de voz\n'
                '`&tocar` — Inicia a reprodução\n'
                '`&pausar` — Pausa o áudio\n'
                '`&retomar` — Retoma o áudio pausado\n'
                '`&parar` — Para sem sair da call\n'
                '`&sair` — Para e sai da call\n'
                '`&skip` — Pula para o próximo\n'
                '`&previous` — Volta ao anterior\n'
                '`&recomecar` — Recomeça a música atual\n'
                '`&aleatorio` — Liga/desliga modo aleatório 🔀\n'                '`&repetir` — Cicla: sem repetição / música 🔂 / playlist 🔁\n'                '`&volume <0‑200>` — Ajusta o volume\n'
                '`&tocando` — Mostra o que está tocando'
            ),
            inline=False,
        )
        embed.add_field(
            name='🎲 Diversão',
            value='`&dado [lados]` — Lança um dado (padrão: d20)',
            inline=False,
        )
        embed.add_field(
            name='⚙️ Configuração',
            value=(
                '`&definircanal [#canal]` — Define onde os comandos são aceitos\n'
                '`&limparchat [qtd]` — Apaga as últimas mensagens do canal'
            ),
            inline=False,
        )
        embed.set_footer(
            text=f'Solicitado por {ctx.author}',
            icon_url=ctx.author.display_avatar.url,
        )
        await ctx.send(embed=embed)


async def setup(bot: commands.Bot, **kwargs) -> None:
    await bot.add_cog(MusicCog(bot, **kwargs))
