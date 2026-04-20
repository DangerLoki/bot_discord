import os
import asyncio
import random
import uuid
from pathlib import Path

import discord
from discord.ext import commands
from dotenv import load_dotenv

from src.logger import get_logger
from src.bot.ui import PaginacaoPlaylist
from src.bot.youtube_mixin import YouTubeMixin
from src.bot.spotify_mixin import SpotifyMixin
from src.bot.playlist_mixin import PlaylistMixin
from src.bot.player_mixin import PlayerMixin

logger = get_logger(__name__)


class MyBot(PlaylistMixin, YouTubeMixin, SpotifyMixin, PlayerMixin):
    def __init__(self):
        diretorio_atual = os.path.dirname(__file__)

        self.json_playlist = os.path.join(diretorio_atual, '..', '..', 'data', 'playlist.json')
        self.cookies_file = os.path.join(diretorio_atual, '..', '..', 'config', 'cookies.txt')
        self.cache_dir = Path(diretorio_atual) / '..' / '..' / 'cache'
        self.cache_dir.mkdir(parents=True, exist_ok=True)

        load_dotenv(os.path.join(diretorio_atual, '..', '..', 'config.env'))
        self.token = os.getenv('token_discord')
        self.proxy = os.getenv('ytdlp_proxy', '').strip() or None
        if self.proxy:
            logger.info(f'[PROXY] usando proxy para yt-dlp: {self.proxy}')

        self.spotify_client_id = os.getenv('spotify_client_id', '').strip() or None
        self.spotify_client_secret = os.getenv('spotify_client_secret', '').strip() or None
        if self.spotify_client_id:
            logger.info('[SPOTIFY] credenciais carregadas.')
        else:
            logger.info('[SPOTIFY] não configurado (spotify_client_id ausente).')

        # Voice playback state
        self.voice_client = None
        self.voice_volume = 0.25
        self.is_playing_voice = False
        self.voice_bot = None
        self.playlist_index = 0
        self.shuffle_mode = False
        self.shuffle_playlist = []  # Lista de índices aleatórios gerada
        self.shuffle_index = 0     # Posição atual na lista aleatória
        self.shuffle_id = None     # ID único para a lista aleatória gerada
        self._carregando = asyncio.Lock()
        
        # Busca a primeira música não tocada ao iniciar
        self._encontrar_proxima_nao_tocada()
    
    def _encontrar_proxima_nao_tocada(self):
        """Encontra a primeira música não tocada na playlist ao iniciar."""
        playlist = self.carregar_playlist()
        if not playlist:
            self.playlist_index = 0
            return
        
        # Procura a primeira música com tocado = False
        for i, video in enumerate(playlist):
            if not video.get('tocado', False):
                self.playlist_index = i
                logger.info(f'[INIT] Continuando de: {video.get("titulo", "?")} (posição {i + 1})')
                return
        
        # Se todas foram tocadas, para a reprodução
        self.playlist_index = 0
        logger.info('[INIT] Todas as músicas foram tocadas. Bot parado.')
    
    # ===================================================
    # Função para rodar o bot
    # ===================================================
    
    def run(self):
        intents = discord.Intents.default()  # Corrigido: era 'itents'
        intents.message_content = True
        
        bot = commands.Bot(command_prefix='&', intents=intents, help_command=None)
        
        # evento on_ready
        @bot.event
        async def on_ready():
            logger.info(f'Bot conectado como {bot.user} (ID: {bot.user.id})')
        
        
        @bot.command(name='skip', aliases=['pular', 'next'])
        async def skip(ctx):
            logger.info(f'[SKIP] solicitado por {ctx.author} em #{ctx.channel}')
            await self.pular_video(ctx)
            # Se está na call, toca o próximo
            if self.voice_client and self.voice_client.is_connected():
                await self.tocar_atual(ctx)
        
        @bot.command(name='previous', aliases=['voltar', 'anterior'])
        async def previous(ctx):
            logger.info(f'[PREVIOUS] solicitado por {ctx.author} em #{ctx.channel}')
            await self.voltar_video(ctx)
            # Se está na call, toca o anterior
            if self.voice_client and self.voice_client.is_connected():
                await self.tocar_atual(ctx)

        @bot.command(name='recomecar', aliases=['restart', 'replay', 'reiniciar'])
        async def recomecar(ctx):
            """Recomeça a música atual do início"""
            logger.info(f'[RECOMECAR] solicitado por {ctx.author} em #{ctx.channel}')
            if not self.voice_client or not self.voice_client.is_connected():
                await ctx.send('❌ Não estou em nenhum canal de voz.')
                return
            await ctx.send('🔁 Recomeçando música atual...')
            await self.tocar_atual(ctx)

        @bot.command(name='aleatorio', aliases=['shuffle', 'random', 'embaralhar'])
        async def aleatorio(ctx):
            """Liga/desliga o modo de reprodução aleatória"""
            self.shuffle_mode = not self.shuffle_mode
            if self.shuffle_mode:
                # Gera lista aleatória dos vídeos não tocados
                playlist = self.carregar_playlist()
                nao_tocados = [i for i, v in enumerate(playlist) if not v.get('tocado', False)]
                if nao_tocados:
                    random.shuffle(nao_tocados)
                    self.shuffle_playlist = nao_tocados
                    self.shuffle_index = 0
                    self.shuffle_id = str(uuid.uuid4())[:8]  # ID curto para exibição
                    await ctx.send(f'🔀 Modo aleatório **ativado**! (ID: `{self.shuffle_id}`) Lista criada com {len(nao_tocados)} músicas.')
                else:
                    # Se todos foram tocados, reinicia e embaralha tudo
                    indices = list(range(len(playlist)))
                    random.shuffle(indices)
                    self.shuffle_playlist = indices
                    self.shuffle_index = 0
                    self.shuffle_id = str(uuid.uuid4())[:8]
                    await ctx.send(f'🔀 Modo aleatório **ativado**! (ID: `{self.shuffle_id}`) Todas as músicas foram resetadas e embaralhadas.')
            else:
                await ctx.send('➡️ Modo aleatório **desativado**. Ordem normal retomada.')
            logger.info(f'[SHUFFLE] {"ON" if self.shuffle_mode else "OFF"} ({self.shuffle_id if self.shuffle_mode else "N/A"}) por {ctx.author}')
        
        @bot.command(name='remove', aliases=['remover', 'rm', 'delete', 'rmid', 'deleteid', 'removeid'])
        async def remove(ctx, *, entrada: str = None):
            """Remove um vídeo da playlist pela posição ou pelo ID/URL"""
            logger.info(f'[REMOVE] entrada="{entrada}" solicitado por {ctx.author} em #{ctx.channel}')
            await self.remover_video(ctx, entrada)

        @bot.command(name='promover', aliases=['promote', 'proxima', 'boost'])
        async def promover(ctx, *, entrada: str = None):
            """Move um vídeo para ser o próximo a tocar"""
            logger.info(f'[PROMOTE] entrada="{entrada}" solicitado por {ctx.author} em #{ctx.channel}')
            await self.promover_video(ctx, entrada, bot)

        @bot.command(name='limpar', aliases=['clear', 'clearall', 'limpartudo'])
        async def limpar(ctx):
            """Limpa toda a playlist"""
            logger.info(f'[CLEAR] solicitado por {ctx.author} em #{ctx.channel}')
            await self.limpar_playlist(ctx)

        
        # comando para lançar dado
        @bot.command()
        async def dado(ctx, lados: str = "20"):
            
            lados = lados.replace(',', '.')
            
            lados_num = float(lados)
            lados_int = int(lados_num)
            
            
            if lados_int < 2:
                await ctx.send('O número de lados deve ser pelo menos 2.')  # Corrigido: era "pelo menos 1"
                return
            
            resultado = random.randint(1, lados_int)
            
            await ctx.send(f'🎲 {ctx.author.mention} lançou um dado de {lados_int} lados e o resultado foi {resultado}')
        
        # comando para adicionar vídeo à playlist
        @bot.command()
        async def add(ctx, *, entrada: str):
            if 'open.spotify.com' in entrada:
                logger.info(f'[ADD SPOTIFY] {entrada} por {ctx.author}')
                await self.adicionar_spotify(ctx, entrada, bot)
            elif entrada.startswith('http') and ('list=' in entrada or 'playlist' in entrada):
                logger.info(f'[ADD PLAYLIST] {entrada} por {ctx.author}')
                await self.adicionar_playlist(ctx, entrada)
            elif entrada.startswith('http'):
                logger.info(f'[ADD URL] {entrada} por {ctx.author}')
                await self.adicionar_por_url(ctx, entrada)
            else:
                logger.info(f'[ADD BUSCA] "{entrada}" por {ctx.author}')
                await self.adicionar_por_busca(ctx, entrada, bot)

        @bot.command(name='playlist', aliases=['pl', 'addplaylist'])
        async def playlist_cmd(ctx, *, url: str):
            """Adiciona uma playlist inteira do YouTube"""
            if not url.startswith('http') or ('list=' not in url and 'playlist' not in url):
                await ctx.send('❌ Forneça uma URL de playlist do YouTube. Exemplo: `&playlist https://www.youtube.com/playlist?list=XXXX`')
                return
            logger.info(f'[ADD PLAYLIST] {url} por {ctx.author}')
            await self.adicionar_playlist(ctx, url)
        @bot.command(name='spotify', aliases=['sp', 'addspotify'])
        async def spotify_cmd(ctx, *, url: str):
            """Adiciona uma faixa, álbum ou playlist do Spotify"""
            if 'open.spotify.com' not in url:
                await ctx.send('\u274c Forneça uma URL válida do Spotify.\nExemplos:\n• `&spotify https://open.spotify.com/track/...`\n• `&spotify https://open.spotify.com/album/...`\n• `&spotify https://open.spotify.com/playlist/...`')
                return
            logger.info(f'[SPOTIFY CMD] {url} por {ctx.author}')
            await self.adicionar_spotify(ctx, url, bot)        
        @bot.command()
        async def listar(ctx):
            playlist = self.carregar_playlist()
            if self.shuffle_mode and self.shuffle_playlist:
                # Mostra a lista aleatória com shuffle_id
                shuffle_items = [playlist[i] for i in self.shuffle_playlist]
                # Adiciona posições da lista aleatória
                for pos, item in enumerate(shuffle_items, 1):
                    item_copy = item.copy()
                    item_copy['posicao_shuffle'] = pos
                    item_copy['shuffle_id'] = self.shuffle_id
                    shuffle_items[pos-1] = item_copy
                titulo = f"🔀 Playlist Aleatória (ID: `{self.shuffle_id}`)"
                view = PaginacaoPlaylist(shuffle_items, titulo=titulo)
            else:
                view = PaginacaoPlaylist(playlist)
            await ctx.send(embed=view.criar_embed(), view=view)
        
        # ==============================================
        # Comandos de voz
        # ==============================================

        @bot.command(name='entrar', aliases=['join', 'connect', 'entra'])
        async def entrar(ctx):
            """Bot entra no canal de voz do usuário"""
            if not ctx.author.voice:
                await ctx.send('❌ Você precisa estar em um canal de voz!')
                return
            
            canal = ctx.author.voice.channel
            
            if self.voice_client and self.voice_client.is_connected():
                if self.voice_client.channel == canal:
                    await ctx.send('⚠️ Já estou nesse canal!')
                    return
                await self.voice_client.move_to(canal)
                await ctx.send(f'🔄 Me movi para **{canal.name}**.')
                return
            
            self.voice_client = await canal.connect()
            self.voice_bot = bot
            await ctx.send(f'✅ Entrei em **{canal.name}**! Use `&tocar` para iniciar o áudio.')
            logger.info(f'[VOZ] Bot entrou em: {canal.name}')

        @bot.command(name='tocar', aliases=['play', 'start'])
        async def tocar(ctx):
            """Começa a tocar o áudio da playlist na call"""
            if not self.voice_client or not self.voice_client.is_connected():
                # Auto-join se o user está em um canal
                if ctx.author.voice:
                    self.voice_client = await ctx.author.voice.channel.connect()
                    self.voice_bot = bot
                else:
                    await ctx.send('❌ Não estou em nenhum canal! Use `&entrar` primeiro.')
                    return
            
            await self.tocar_atual(ctx)

        @bot.command(name='pausar', aliases=['pause'])
        async def pausar(ctx):
            """Pausa o áudio"""
            if self.voice_client and self.voice_client.is_playing():
                self.voice_client.pause()
                self._pausar_rastreio()
                await ctx.send('⏸️ Áudio pausado.')
            else:
                await ctx.send('❌ Nenhum áudio tocando.')

        @bot.command(name='retomar', aliases=['resume', 'continuar'])
        async def retomar(ctx):
            """Retoma o áudio pausado"""
            if self.voice_client and self.voice_client.is_paused():
                self.voice_client.resume()
                self._retomar_rastreio()
                await ctx.send('▶️ Áudio retomado.')
            else:
                await ctx.send('❌ Nenhum áudio pausado.')

        @bot.command(name='parar', aliases=['stop'])
        async def parar(ctx):
            """Para o áudio sem sair da call"""
            if self.voice_client and (self.voice_client.is_playing() or self.voice_client.is_paused()):
                self.is_playing_voice = False
                self._parar_status_loop()
                self.voice_client.stop()
                await ctx.send('⏹️ Áudio parado.')
            else:
                await ctx.send('❌ Nenhum áudio tocando.')

        @bot.command(name='sair', aliases=['leave', 'disconnect', 'dc'])
        async def sair(ctx):
            """Para o áudio e sai da call"""
            if self.voice_client:
                self.is_playing_voice = False
                self._parar_status_loop()
                self.voice_client.stop()
                await self.voice_client.disconnect()
                self.voice_client = None
                await ctx.send('📴 Saí da call.')
                logger.info('[VOZ] Bot saiu da call.')
            else:
                await ctx.send('❌ Não estou em nenhum canal.')

        @bot.command(name='volume', aliases=['vol', 'v'])
        async def volume(ctx, valor: str = None):
            """Ajusta o volume (0 a 200)"""
            if valor is None:
                porcentagem = int(self.voice_volume * 100)
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
            
            self.voice_volume = valor_num / 100.0
            
            # Atualiza volume ao vivo se estiver tocando
            if self.voice_client and self.voice_client.source:
                self.voice_client.source.volume = self.voice_volume
            
            await ctx.send(f'🔉 Volume ajustado para **{valor_num}%**.')

        @bot.command(name='tocando', aliases=['np', 'nowplaying', 'atual'])
        async def tocando(ctx):
            """Mostra o que está tocando na call"""
            if not self.voice_client or not self.voice_client.is_connected():
                await ctx.send('❌ Não estou em nenhum canal.')
                return
            
            if not self.voice_client.is_playing() and not self.voice_client.is_paused():
                await ctx.send('❌ Nenhum áudio tocando no momento.')
                return
            
            playlist = self.carregar_playlist()
            if not playlist:
                await ctx.send('❌ Playlist vazia.')
                return
            
            index = self.playlist_index if self.playlist_index < len(playlist) else 0
            video = playlist[index]
            status = '⏸️ Pausado' if self.voice_client.is_paused() else '▶️ Tocando'
            embed = discord.Embed(
                title=f'{status} na Call',
                description=f"**[{video.get('titulo', 'Desconhecido')}]({video.get('embed_url', '#')})**",
                color=0x1DB954
            )
            embed.set_thumbnail(url=video.get('thumbnail_url', ''))
            embed.add_field(name='Duração', value=video.get('duracao_formatada', '??:??'), inline=True)
            embed.add_field(name='Posição', value=f"{index + 1}/{len(playlist)}", inline=True)
            embed.add_field(name='Volume', value=f'{int(self.voice_volume * 100)}%', inline=True)
            embed.add_field(name='Canal', value=video.get('canal', 'Desconhecido'), inline=True)
            await ctx.send(embed=embed)

        @bot.command(name='help', aliases=['ajuda', 'comandos', 'cmds'])
        async def help_cmd(ctx):
            """Lista todos os comandos disponíveis"""
            embed = discord.Embed(
                title='📖 Comandos do Bot',
                description='Prefixo: `&`',
                color=0x5865F2
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
                inline=False
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
                inline=False
            )

            embed.add_field(
                name='🎲 Diversão',
                value='`&dado [lados]` — Lança um dado (padrão: d20)',
                inline=False
            )

            embed.set_footer(text=f'Solicitado por {ctx.author}', icon_url=ctx.author.display_avatar.url)
            await ctx.send(embed=embed)

        bot.run(self.token)
if __name__ == "__main__":
    bot = MyBot()
    bot.run()