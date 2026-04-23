"""Cog de reprodução de áudio — comandos de voz."""
import discord
from discord.ext import commands

from src.logger import get_logger
from src.models.player_state import PlayerState
from src.services.player_service import PlayerService
from src.services.playlist_service import PlaylistService
from src.repositories.playlist_repository import PlaylistRepository
from src.utils import embed_erro

logger = get_logger(__name__)


class MusicCog(commands.Cog, name='Música'):
    """Comandos de reprodução de áudio em canal de voz."""

    def __init__(
        self,
        bot: commands.Bot,
        state: PlayerState,
        player_svc: PlayerService,
        playlist_svc: PlaylistService,
        repo: PlaylistRepository,
    ) -> None:
        self.bot = bot
        self.state = state
        self.player_svc = player_svc
        self.playlist_svc = playlist_svc
        self.repo = repo

    # ------------------------------------------------------------------
    # Conexão
    # ------------------------------------------------------------------

    @commands.command(name='entrar', aliases=['join', 'connect', 'entra'])
    async def entrar(self, ctx):
        """Bot entra no canal de voz do usuário."""
        if not ctx.author.voice:
            await ctx.send('❌ Você precisa estar em um canal de voz!')
            return
        canal = ctx.author.voice.channel

        if self.state.voice_client and self.state.voice_client.is_connected():
            if self.state.voice_client.channel == canal:
                await ctx.send('⚠️ Já estou nesse canal!')
                return
            await self.state.voice_client.move_to(canal)
            await ctx.send(f'🔄 Me movi para **{canal.name}**.')
            return

        self.state.voice_client = await canal.connect()
        self.state.voice_bot = self.bot
        await ctx.send(f'✅ Entrei em **{canal.name}**! Use `&tocar` para iniciar o áudio.')
        logger.info(f'[VOZ] Bot entrou em: {canal.name}')

    @commands.command(name='sair', aliases=['leave', 'disconnect', 'dc'])
    async def sair(self, ctx):
        """Para o áudio e sai da call."""
        if self.state.voice_client:
            self.state.is_playing_voice = False
            self.player_svc._parar_status_loop()
            self.state.voice_client.stop()
            await self.state.voice_client.disconnect()
            self.state.voice_client = None
            await ctx.send('📴 Saí da call.')
            logger.info('[VOZ] Bot saiu da call.')
        else:
            await ctx.send('❌ Não estou em nenhum canal.')

    # ------------------------------------------------------------------
    # Reprodução
    # ------------------------------------------------------------------

    @commands.command(name='tocar', aliases=['play', 'start'])
    async def tocar(self, ctx):
        """Começa a tocar o áudio da playlist na call."""
        if not self.state.voice_client or not self.state.voice_client.is_connected():
            if ctx.author.voice:
                self.state.voice_client = await ctx.author.voice.channel.connect()
                self.state.voice_bot = self.bot
            else:
                await ctx.send('❌ Não estou em nenhum canal! Use `&entrar` primeiro.')
                return
        await self.player_svc.tocar_atual(ctx)

    @commands.command(name='pausar', aliases=['pause'])
    async def pausar(self, ctx):
        """Pausa o áudio."""
        if self.state.voice_client and self.state.voice_client.is_playing():
            self.state.voice_client.pause()
            self.state.pausar_rastreio()
            await ctx.send('⏸️ Áudio pausado.')
        else:
            await ctx.send('❌ Nenhum áudio tocando.')

    @commands.command(name='retomar', aliases=['resume', 'continuar'])
    async def retomar(self, ctx):
        """Retoma o áudio pausado."""
        if self.state.voice_client and self.state.voice_client.is_paused():
            self.state.voice_client.resume()
            self.state.retomar_rastreio()
            await ctx.send('▶️ Áudio retomado.')
        else:
            await ctx.send('❌ Nenhum áudio pausado.')

    @commands.command(name='parar', aliases=['stop'])
    async def parar(self, ctx):
        """Para o áudio sem sair da call."""
        if self.state.voice_client and (
            self.state.voice_client.is_playing() or self.state.voice_client.is_paused()
        ):
            self.state.is_playing_voice = False
            self.player_svc._parar_status_loop()
            self.state.voice_client.stop()
            await ctx.send('⏹️ Áudio parado.')
        else:
            await ctx.send('❌ Nenhum áudio tocando.')

    @commands.command(name='skip', aliases=['pular', 'next'])
    async def skip(self, ctx):
        """Pula para o próximo vídeo."""
        logger.info(f'[SKIP] solicitado por {ctx.author} em #{ctx.channel}')
        await self.playlist_svc.pular_video(ctx)
        if self.state.voice_client and self.state.voice_client.is_connected():
            await self.player_svc.tocar_atual(ctx)

    @commands.command(name='previous', aliases=['voltar', 'anterior'])
    async def previous(self, ctx):
        """Volta ao vídeo anterior."""
        logger.info(f'[PREVIOUS] solicitado por {ctx.author} em #{ctx.channel}')
        await self.playlist_svc.voltar_video(ctx)
        if self.state.voice_client and self.state.voice_client.is_connected():
            await self.player_svc.tocar_atual(ctx)

    @commands.command(name='recomecar', aliases=['restart', 'replay', 'reiniciar'])
    async def recomecar(self, ctx):
        """Recomeça a música atual do início."""
        logger.info(f'[RECOMECAR] solicitado por {ctx.author} em #{ctx.channel}')
        if not self.state.voice_client or not self.state.voice_client.is_connected():
            await ctx.send('❌ Não estou em nenhum canal de voz.')
            return
        await ctx.send('🔁 Recomeçando música atual...')
        await self.player_svc.tocar_atual(ctx)

    # ------------------------------------------------------------------
    # Volume
    # ------------------------------------------------------------------

    @commands.command(name='volume', aliases=['vol', 'v'])
    async def volume(self, ctx, valor: str = None):
        """Ajusta o volume (0 a 200)."""
        if valor is None:
            porcentagem = int(self.state.voice_volume * 100)
            await ctx.send(f'🔉 Volume atual: **{porcentagem}%**')
            return
        try:
            valor_num = int(valor)
        except ValueError:
            await ctx.send('❌ Use um número entre 0 e 200. Ex: `&volume 80`')
            return
        if not 0 <= valor_num <= 200:
            await ctx.send('❌ Volume deve ser entre **0** e **200**.')
            return
        self.state.voice_volume = valor_num / 100.0
        if self.state.voice_client and self.state.voice_client.source:
            self.state.voice_client.source.volume = self.state.voice_volume
        await ctx.send(f'🔉 Volume ajustado para **{valor_num}%**.')

    # ------------------------------------------------------------------
    # Now Playing
    # ------------------------------------------------------------------

    @commands.command(name='tocando', aliases=['np', 'nowplaying', 'atual'])
    async def tocando(self, ctx):
        """Mostra o que está tocando na call."""
        vc = self.state.voice_client
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
            self.state.playlist_index if self.state.playlist_index < len(playlist) else 0
        )
        video = playlist[index]
        status = '⏸️ Pausado' if vc.is_paused() else '▶️ Tocando'
        embed = discord.Embed(
            title=f'{status} na Call',
            description=f"**[{video.get('titulo', 'Desconhecido')}]({video.get('embed_url', '#')})**",
            color=0x1DB954,
        )
        embed.set_thumbnail(url=video.get('thumbnail_url', ''))
        embed.add_field(name='Duração', value=video.get('duracao_formatada', '??:??'), inline=True)
        embed.add_field(name='Posição', value=f'{index + 1}/{len(playlist)}', inline=True)
        embed.add_field(name='Volume', value=f'{int(self.state.voice_volume * 100)}%', inline=True)
        embed.add_field(name='Canal', value=video.get('canal', 'Desconhecido'), inline=True)
        await ctx.send(embed=embed)

    # ------------------------------------------------------------------
    # Help
    # ------------------------------------------------------------------

    @commands.command(name='help', aliases=['ajuda', 'comandos', 'cmds'])
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
                '`&aleatorio` — Liga/desliga modo aleatório 🔀\n'
                '`&volume <0‑200>` — Ajusta o volume\n'
                '`&tocando` — Mostra o que está tocando'
            ),
            inline=False,
        )
        embed.add_field(
            name='🎲 Diversão',
            value='`&dado [lados]` — Lança um dado (padrão: d20)',
            inline=False,
        )
        embed.set_footer(
            text=f'Solicitado por {ctx.author}',
            icon_url=ctx.author.display_avatar.url,
        )
        await ctx.send(embed=embed)


async def setup(bot: commands.Bot, **kwargs) -> None:
    await bot.add_cog(MusicCog(bot, **kwargs))
