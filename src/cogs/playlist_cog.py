"""Cog de gerenciamento da playlist — comandos de fila."""
import random
import urllib.parse

import discord
from discord.ext import commands

from src.logger import get_logger
from src.models.player_state import PlayerState
from src.services.playlist_service import PlaylistService
from src.repositories.playlist_repository import PlaylistRepository
from src.ui.pagination import PaginacaoPlaylist

logger = get_logger(__name__)


class PlaylistCog(commands.Cog, name='Playlist'):
    """Comandos de gerenciamento da fila de reprodução."""

    def __init__(
        self,
        bot: commands.Bot,
        state: PlayerState,
        playlist_svc: PlaylistService,
        repo: PlaylistRepository,
    ) -> None:
        self.bot = bot
        self.state = state
        self.playlist_svc = playlist_svc
        self.repo = repo

    # ------------------------------------------------------------------
    # Adição
    # ------------------------------------------------------------------

    @commands.command(name='add')
    async def add(self, ctx, *, entrada: str):
        """Adiciona um vídeo, playlist do YouTube ou URL do Spotify."""
        if 'open.spotify.com' in entrada:
            logger.info(f'[ADD SPOTIFY] {entrada} por {ctx.author}')
            await self.playlist_svc.adicionar_spotify(ctx, entrada, self.bot)
        elif entrada.startswith('http') and ('list=' in entrada or 'playlist' in entrada):
            params = urllib.parse.parse_qs(urllib.parse.urlparse(entrada).query)
            list_id = params.get('list', [''])[0]
            if list_id.startswith('RD'):
                # YouTube Mix — adiciona só o vídeo do link, ignora a fila gerada
                video_id = params.get('v', [''])[0]
                url_limpa = f'https://www.youtube.com/watch?v={video_id}' if video_id else entrada
                logger.info(f'[ADD MIX→VIDEO] {url_limpa} por {ctx.author}')
                await ctx.send(
                    embed=discord.Embed(
                        description='ℹ️ Links de Mix do YouTube adicionam apenas o vídeo selecionado, não a fila inteira.',
                        color=0x5865F2,
                    )
                )
                await self.playlist_svc.adicionar_por_url(ctx, url_limpa)
            else:
                logger.info(f'[ADD PLAYLIST] {entrada} por {ctx.author}')
                await self.playlist_svc.adicionar_playlist_youtube(ctx, entrada)
        elif entrada.startswith('http'):
            logger.info(f'[ADD URL] {entrada} por {ctx.author}')
            await self.playlist_svc.adicionar_por_url(ctx, entrada)
        else:
            logger.info(f'[ADD BUSCA] "{entrada}" por {ctx.author}')
            await self.playlist_svc.adicionar_por_busca(ctx, entrada, self.bot)

    @commands.command(name='playlist', aliases=['pl', 'addplaylist'])
    async def playlist_cmd(self, ctx, *, url: str):
        """Adiciona uma playlist inteira do YouTube."""
        if not url.startswith('http') or ('list=' not in url and 'playlist' not in url):
            await ctx.send(
                '❌ Forneça uma URL de playlist do YouTube. '
                'Exemplo: `&playlist https://www.youtube.com/playlist?list=XXXX`'
            )
            return
        params = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
        list_id = params.get('list', [''])[0]
        if list_id.startswith('RD'):
            await ctx.send(
                embed=discord.Embed(
                    description='❌ Links de **Mix** não são suportados no comando `&playlist`.\nUse `&add <url>` para adicionar apenas o vídeo do link.',
                    color=0xED4245,
                )
            )
            return
        logger.info(f'[ADD PLAYLIST] {url} por {ctx.author}')
        await self.playlist_svc.adicionar_playlist_youtube(ctx, url)

    @commands.command(name='spotify', aliases=['sp', 'addspotify'])
    async def spotify_cmd(self, ctx, *, url: str):
        """Adiciona uma faixa, álbum ou playlist do Spotify."""
        if 'open.spotify.com' not in url:
            await ctx.send(
                '❌ Forneça uma URL válida do Spotify.\nExemplos:\n'
                '• `&spotify https://open.spotify.com/track/...`\n'
                '• `&spotify https://open.spotify.com/album/...`\n'
                '• `&spotify https://open.spotify.com/playlist/...`'
            )
            return
        logger.info(f'[SPOTIFY CMD] {url} por {ctx.author}')
        await self.playlist_svc.adicionar_spotify(ctx, url, self.bot)

    # ------------------------------------------------------------------
    # Listagem
    # ------------------------------------------------------------------

    @commands.command(name='listar')
    async def listar(self, ctx):
        """Lista os vídeos da playlist (paginado)."""
        playlist = self.repo.load()
        st = self.state
        if st.shuffle_mode and st.shuffle_playlist:
            shuffle_items = []
            for pos, idx in enumerate(st.shuffle_playlist, 1):
                item = playlist[idx].copy()
                item['posicao_shuffle'] = pos
                item['shuffle_id'] = st.shuffle_id
                shuffle_items.append(item)
            titulo = f'🔀 Playlist Aleatória (ID: `{st.shuffle_id}`)'
            view = PaginacaoPlaylist(shuffle_items, titulo=titulo)
        else:
            view = PaginacaoPlaylist(playlist)
        await ctx.send(embed=view.criar_embed(), view=view)

    # ------------------------------------------------------------------
    # Remoção / reordenação
    # ------------------------------------------------------------------

    @commands.command(name='remove', aliases=['remover', 'rm', 'delete', 'rmid', 'deleteid', 'removeid'])
    async def remove(self, ctx, *, entrada: str = None):
        """Remove um vídeo da playlist pela posição ou pelo ID/URL."""
        logger.info(f'[REMOVE] entrada="{entrada}" por {ctx.author} em #{ctx.channel}')
        await self.playlist_svc.remover_video(ctx, entrada)

    @commands.command(name='promover', aliases=['promote', 'proxima', 'boost'])
    async def promover(self, ctx, *, entrada: str = None):
        """Move um vídeo para ser o próximo a tocar."""
        logger.info(f'[PROMOTE] entrada="{entrada}" por {ctx.author} em #{ctx.channel}')
        await self.playlist_svc.promover_video(ctx, entrada, self.bot)

    @commands.command(name='limpar', aliases=['clear', 'clearall', 'limpartudo'])
    async def limpar(self, ctx):
        """Limpa toda a playlist."""
        logger.info(f'[CLEAR] por {ctx.author} em #{ctx.channel}')
        await self.playlist_svc.limpar_playlist(ctx)

    # ------------------------------------------------------------------
    # Shuffle
    # ------------------------------------------------------------------

    @commands.command(name='aleatorio', aliases=['shuffle', 'random', 'embaralhar'])
    async def aleatorio(self, ctx):
        """Liga/desliga o modo de reprodução aleatória."""
        await self.playlist_svc.toggle_shuffle(ctx)

    # ------------------------------------------------------------------
    # Diversão
    # ------------------------------------------------------------------

    @commands.command(name='dado')
    async def dado(self, ctx, lados: str = '20'):
        """Lança um dado com N lados (padrão: d20)."""
        lados_num = int(float(lados.replace(',', '.')))
        if lados_num < 2:
            await ctx.send('O número de lados deve ser pelo menos 2.')
            return
        resultado = random.randint(1, lados_num)
        await ctx.send(
            f'🎲 {ctx.author.mention} lançou um dado de {lados_num} lados e o resultado foi {resultado}'
        )


async def setup(bot: commands.Bot, **kwargs) -> None:
    await bot.add_cog(PlaylistCog(bot, **kwargs))
