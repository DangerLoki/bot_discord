import discord
from discord.ext import commands
from discord.ui import View, Button
from dotenv import load_dotenv
import os
import json
import re
from datetime import datetime
import random
import asyncio
import yt_dlp
from pathlib import Path
from src.logger import get_logger

logger = get_logger(__name__)


class GeoBlockedError(Exception):
    """Levantado quando um vídeo está bloqueado por geo-restrição."""
    pass


_GEO_KEYWORDS = [
    'not made this video available in your country',
    'this video is not available in your country',
    'blocked it in your country',
    'geo restricted',
]


def _is_geo_blocked(msg: str) -> bool:
    m = msg.lower()
    return any(kw in m for kw in _GEO_KEYWORDS)


class PaginacaoPlaylist(View):
    def __init__(self, playlist, itens_por_pagina=10, timeout=60):
        super().__init__(timeout=timeout)
        self.playlist = playlist
        self.itens_por_pagina = itens_por_pagina
        self.pagina_atual = 0
        self.total_paginas = max(1, (len(playlist) + itens_por_pagina - 1) // itens_por_pagina)
        self.atualizar_botoes()
    
    def atualizar_botoes(self):
        self.primeira.disabled = self.pagina_atual == 0
        self.anterior.disabled = self.pagina_atual == 0
        self.proxima.disabled = self.pagina_atual >= self.total_paginas - 1
        self.ultima.disabled = self.pagina_atual >= self.total_paginas - 1
    
    def criar_embed(self):
        embed = discord.Embed(
            title="🎵 Playlist de Vídeos",
            color=0x00ff00
        )
        
        if not self.playlist:
            embed.description = "A playlist está vazia."
        else:
            inicio = self.pagina_atual * self.itens_por_pagina
            fim = inicio + self.itens_por_pagina
            itens_pagina = self.playlist[inicio:fim]
            
            descricao = ""
            for item in itens_pagina:
                descricao += f"**{item['posicao']}.** [{item['titulo']}]({item['embed_url']})\n"
                descricao += f"└ Por: {item['adicionado_por']} | ⏱️ {item['duracao_formatada']}\n\n"
            embed.description = descricao
            embed.set_footer(text=f"Página {self.pagina_atual + 1}/{self.total_paginas} | Total: {len(self.playlist)} vídeos")
        
        return embed
    
    @discord.ui.button(label="⏮️", style=discord.ButtonStyle.secondary)
    async def primeira(self, interaction: discord.Interaction, button: Button):
        self.pagina_atual = 0
        self.atualizar_botoes()
        await interaction.response.edit_message(embed=self.criar_embed(), view=self)
    
    @discord.ui.button(label="◀️", style=discord.ButtonStyle.primary)
    async def anterior(self, interaction: discord.Interaction, button: Button):
        self.pagina_atual = max(0, self.pagina_atual - 1)
        self.atualizar_botoes()
        await interaction.response.edit_message(embed=self.criar_embed(), view=self)
    
    @discord.ui.button(label="▶️", style=discord.ButtonStyle.primary)
    async def proxima(self, interaction: discord.Interaction, button: Button):
        self.pagina_atual = min(self.total_paginas - 1, self.pagina_atual + 1)
        self.atualizar_botoes()
        await interaction.response.edit_message(embed=self.criar_embed(), view=self)
    
    @discord.ui.button(label="⏭️", style=discord.ButtonStyle.secondary)
    async def ultima(self, interaction: discord.Interaction, button: Button):
        self.pagina_atual = self.total_paginas - 1
        self.atualizar_botoes()
        await interaction.response.edit_message(embed=self.criar_embed(), view=self)

class MyBot():
    def __init__(self):
        
        diretorio_atual = os.path.dirname(__file__)
        diretorio_config = os.path.join(diretorio_atual, '..', '..', 'config.env')
        
        self.json_playlist = os.path.join(diretorio_atual, '..', '..', 'data', 'playlist.json')
        self.cookies_file = os.path.join(diretorio_atual, '..', '..', 'config', 'cookies.txt')
        self.cache_dir = Path(diretorio_atual) / '..' / '..' / 'cache'
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        
        load_dotenv(diretorio_config)
        self.token = os.getenv('token_discord')
        self.proxy = os.getenv('ytdlp_proxy', '').strip() or None
        if self.proxy:
            logger.info(f'[PROXY] usando proxy para yt-dlp: {self.proxy}')
        
        # Voice playback state
        self.voice_client = None
        self.voice_volume = 0.25
        self.is_playing_voice = False
        self.voice_bot = None  # referência ao bot para usar no after callback
        self.playlist_index = 0  # índice do vídeo atual na playlist
        self.shuffle_mode = False   # modo aleatório ON/OFF
        self._carregando = asyncio.Lock()  # lock contra chamadas concorrentes de tocar_atual
    
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
                await ctx.send('🔀 Modo aleatório **ativado**! Músicas sem repetição até completar a playlist.')
            else:
                await ctx.send('➡️ Modo aleatório **desativado**. Ordem normal retomada.')
            logger.info(f'[SHUFFLE] {"ON" if self.shuffle_mode else "OFF"} por {ctx.author}')
        
        @bot.command(name='remove', aliases=['remover', 'rm', 'delete', 'rmid', 'deleteid', 'removeid'])
        async def remove(ctx, *, entrada: str = None):
            """Remove um vídeo da playlist pela posição ou pelo ID/URL"""
            logger.info(f'[REMOVE] entrada="{entrada}" solicitado por {ctx.author} em #{ctx.channel}')
            await self.remover_video(ctx, entrada)

        @bot.command(name='promover', aliases=['promote', 'proxima', 'boost'])
        async def promover(ctx, *, entrada: str = None):
            """Move um vídeo para ser o próximo a tocar"""
            logger.info(f'[PROMOTE] entrada="{entrada}" solicitado por {ctx.author} em #{ctx.channel}')
            await self.promover_video(ctx, entrada)

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
            if entrada.startswith('http') and ('list=' in entrada or 'playlist' in entrada):
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
        
        @bot.command()
        async def listar(ctx):
            playlist = self.carregar_playlist()
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
                await ctx.send('⏸️ Áudio pausado.')
            else:
                await ctx.send('❌ Nenhum áudio tocando.')

        @bot.command(name='retomar', aliases=['resume', 'continuar'])
        async def retomar(ctx):
            """Retoma o áudio pausado"""
            if self.voice_client and self.voice_client.is_paused():
                self.voice_client.resume()
                await ctx.send('▶️ Áudio retomado.')
            else:
                await ctx.send('❌ Nenhum áudio pausado.')

        @bot.command(name='parar', aliases=['stop'])
        async def parar(ctx):
            """Para o áudio sem sair da call"""
            if self.voice_client and (self.voice_client.is_playing() or self.voice_client.is_paused()):
                self.is_playing_voice = False
                self.voice_client.stop()
                await ctx.send('⏹️ Áudio parado.')
            else:
                await ctx.send('❌ Nenhum áudio tocando.')

        @bot.command(name='sair', aliases=['leave', 'disconnect', 'dc'])
        async def sair(ctx):
            """Para o áudio e sai da call"""
            if self.voice_client:
                self.is_playing_voice = False
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
                    '`&add <url|busca>` — Adiciona vídeo ou playlist\n'
                    '`&playlist <url>` — Adiciona playlist inteira\n'
                    '`&listar` — Lista os vídeos (paginado)\n'
                    '`&remove <pos|id>` — Remove um vídeo\n'
                    '`&promover <pos|id>` — Move para próxima posição\n'
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
    
    # ===================================================
    # Métodos de reprodução de áudio na call
    # ===================================================

    async def baixar_audio(self, video_url, video_id):
        """Baixa o áudio do vídeo para o cache e retorna o caminho do arquivo.
        Lança GeoBlockedError se o vídeo estiver bloqueado na região.
        """
        destino = self.cache_dir / video_id
        existente = list(self.cache_dir.glob(f'{video_id}.*'))
        if existente:
            logger.debug(f'[CACHE] usando arquivo em cache: {existente[0]}')
            return str(existente[0])

        opts = {
            'format': 'bestaudio/best',
            'outtmpl': str(destino) + '.%(ext)s',
            'quiet': True,
            'no_warnings': True,
            'noplaylist': True,
            'js_runtimes': {'node': {}},
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'opus',
                'preferredquality': '0',
            }],
        }

        if os.path.exists(self.cookies_file):
            opts['cookiefile'] = self.cookies_file
        if self.proxy:
            opts['proxy'] = self.proxy

        def _download():
            try:
                with yt_dlp.YoutubeDL(opts) as ydl:
                    ydl.download([video_url])
                resultado = list(self.cache_dir.glob(f'{video_id}.*'))
                return str(resultado[0]) if resultado else None
            except Exception as e:
                if _is_geo_blocked(str(e)):
                    raise GeoBlockedError(str(e))
                logger.error(f'[yt-dlp] erro ao baixar {video_url}: {e}')
                return None

        return await asyncio.to_thread(_download)

    def _limpar_cache(self, video_id):
        """Remove o arquivo de áudio do cache após tocar."""
        for f in self.cache_dir.glob(f'{video_id}.*'):
            try:
                f.unlink()
                logger.debug(f'[CACHE] removido: {f}')
            except Exception as e:
                logger.warning(f'[CACHE] falha ao remover {f}: {e}')

    def _proximo_aleatorio(self, playlist: list) -> int:
        """Retorna índice aleatório de um vídeo não tocado.
        Quando todos já foram tocados, reseta as flags e começa novo ciclo.
        """
        nao_tocados = [
            i for i, v in enumerate(playlist)
            if not v.get('tocado', False) and i != self.playlist_index
        ]
        if not nao_tocados:
            # Todos tocados — reset e começa novo ciclo
            for v in playlist:
                v['tocado'] = False
            self.salvar_playlist(playlist)
            nao_tocados = [i for i in range(len(playlist)) if i != self.playlist_index]
        if not nao_tocados:
            return self.playlist_index  # playlist com 1 único vídeo
        return random.choice(nao_tocados)
    
    async def tocar_atual(self, ctx):
        """Toca o vídeo atual da playlist na call"""
        if self._carregando.locked():
            return
        async with self._carregando:
            await self._tocar_atual_impl(ctx)

    async def _tocar_atual_impl(self, ctx):
        if not self.voice_client or not self.voice_client.is_connected():
            await ctx.send('❌ Não estou em nenhum canal de voz!')
            return
        
        # Para qualquer áudio atual sem disparar _auto_next
        if self.voice_client.is_playing() or self.voice_client.is_paused():
            self.is_playing_voice = False
            self.voice_client.stop()

        # Loop para pular automaticamente vídeos que falham na extração
        while True:
            playlist = self.carregar_playlist()
            if not playlist:
                await ctx.send('❌ Playlist vazia. Adicione vídeos com `&add`.')
                return
            
            if self.playlist_index >= len(playlist):
                self.playlist_index = 0
            
            video = playlist[self.playlist_index]
            total = len(playlist)
            titulo = video.get('titulo', 'Desconhecido')
            video_url = video.get('embed_url', '')

            await ctx.send(f'🔄 Baixando áudio de **{titulo}**...')

            video_id = video.get('video_id', '')

            # Marca o vídeo como tocado na playlist
            playlist[self.playlist_index]['tocado'] = True
            self.salvar_playlist(playlist)

            try:
                audio_path = await self.baixar_audio(video_url, video_id)
            except GeoBlockedError:
                await ctx.send(
                    f'🌍 **{titulo}** está bloqueado na sua região e foi removido da playlist.'
                )
                playlist = self.carregar_playlist()
                playlist = [v for v in playlist if v.get('video_id') != video_id]
                for i, v in enumerate(playlist):
                    v['posicao'] = i + 1
                self.salvar_playlist(playlist)
                if not playlist:
                    await ctx.send('📋 Playlist vazia após remoção.')
                    return
                self.playlist_index = self.playlist_index % len(playlist)
                continue

            if not audio_path:
                await ctx.send(f'❌ Não consegui baixar o áudio de **{titulo}**. Pulando...')
                self.playlist_index = (self.playlist_index + 1) % len(playlist)
                continue
            break
        
        try:
            source = discord.FFmpegPCMAudio(audio_path)
            source = discord.PCMVolumeTransformer(source, volume=self.voice_volume)
        except Exception as e:
            await ctx.send(f'❌ Erro ao criar stream de áudio: {e}')
            return
        
        self.is_playing_voice = True
        video_id_atual = video.get('video_id', '')
        
        def after_playing(error):
            if error:
                logger.error(f'Erro no player: {error}')
            self._limpar_cache(video_id_atual)
            if self.is_playing_voice and self.voice_client and self.voice_client.is_connected():
                asyncio.run_coroutine_threadsafe(
                    self._auto_next(ctx), self.voice_bot.loop
                )
        
        self.voice_client.play(source, after=after_playing)
        
        embed = discord.Embed(
            title='🔊 Tocando na Call',
            description=f"**[{titulo}]({video_url})**",
            color=0x1DB954
        )
        embed.set_thumbnail(url=video.get('thumbnail_url', ''))
        embed.add_field(name='Duração', value=video.get('duracao_formatada', '??:??'), inline=True)
        embed.add_field(name='Posição', value=f"{self.playlist_index + 1}/{total}", inline=True)
        embed.add_field(name='Volume', value=f'{int(self.voice_volume * 100)}%', inline=True)
        await ctx.send(embed=embed)
        logger.info(f'[VOZ] Tocando: {titulo}')
    
    async def _auto_next(self, ctx):
        """Avança automaticamente para o próximo vídeo"""
        if not self.is_playing_voice:
            return

        playlist = self.carregar_playlist()
        if not playlist:
            self.is_playing_voice = False
            await ctx.send('📋 Playlist terminou!')
            return

        if self.shuffle_mode:
            self.playlist_index = self._proximo_aleatorio(playlist)
        else:
            self.playlist_index += 1
            if self.playlist_index >= len(playlist):
                self.playlist_index = 0
                self.is_playing_voice = False
                await ctx.send('📋 Playlist terminou! Use `&tocar` para recomeçar.')
                return

        await self.tocar_atual(ctx)

    async def voltar_video(self, ctx):
        playlist = self.carregar_playlist()
        if not playlist:
            await ctx.send('❌ Playlist vazia.')
            return
        
        self.playlist_index = (self.playlist_index - 1) % len(playlist)
        video = playlist[self.playlist_index]
        embed = discord.Embed(
            title="⏮️ Vídeo Anterior",
            description=f"Anterior: [{video.get('titulo', 'Desconhecido')}]({video.get('embed_url', '#')})",
            color=0x00ff00
        )
        embed.set_thumbnail(url=video.get('thumbnail_url', ''))
        embed.set_footer(text="Voltado ao vídeo anterior.")
        await ctx.send(embed=embed)
    
    async def remover_video(self, ctx, entrada: str = None):
        """Remove um vídeo da playlist por posição, ID ou URL"""

        if not entrada:
            await ctx.send("❌ Use: `&remove <posição>` ou `&remove <video_id>`\nExemplos: `&remove 5` | `&remove dQw4w9WgXcQ`")
            return

        playlist = self.carregar_playlist()
        if not playlist:
            await ctx.send("⚠️ A playlist está vazia.")
            return

        video = None
        posicao_label = None

        # Tenta interpretar como número de posição
        if entrada.isdigit():
            posicao = int(entrada)
            index = posicao - 1
            if index < 0 or index >= len(playlist):
                await ctx.send(f"❌ Posição inválida. A playlist tem {len(playlist)} vídeos.")
                return
            video = playlist[index]
            posicao_label = str(posicao)
        else:
            # Tenta extrair ID de URL ou usar diretamente como ID
            video_id = self.extrair_video_id(entrada) or entrada.strip()
            video = next((v for v in playlist if v.get('video_id') == video_id), None)
            if not video:
                await ctx.send(f"❌ Não encontrei nenhum vídeo com ID `{video_id}` na playlist.")
                return
            posicao_label = str(video.get('posicao', '?'))

        video_id = video.get('video_id')
        titulo = video.get('titulo', 'Desconhecido')

        # Encontra o índice real no array
        index_removido = next((i for i, v in enumerate(playlist) if v.get('video_id') == video_id), None)
        if index_removido is None:
            await ctx.send(f"❌ Erro interno: vídeo não encontrado.")
            return

        removendo_atual = (index_removido == self.playlist_index)
        playlist.pop(index_removido)

        for i, v in enumerate(playlist):
            v['posicao'] = i + 1

        self.salvar_playlist(playlist)

        # Ajusta o índice atual
        if len(playlist) == 0:
            self.playlist_index = 0
        elif index_removido < self.playlist_index:
            self.playlist_index -= 1
        elif removendo_atual and self.playlist_index >= len(playlist):
            self.playlist_index = 0

        embed = discord.Embed(
            title="🗑️ Vídeo Removido!",
            description=f"**{titulo}**",
            color=0xff0000
        )
        embed.set_thumbnail(url=video.get('thumbnail_url', ''))
        embed.add_field(name="Posição", value=posicao_label, inline=True)
        embed.add_field(name="ID", value=f"`{video_id}`", inline=True)
        embed.add_field(name="Canal", value=video.get('canal', 'Desconhecido'), inline=True)
        if removendo_atual and playlist:
            proximo = playlist[self.playlist_index]
            embed.add_field(
                name="▶️ Tocando agora",
                value=proximo.get('titulo', 'Desconhecido'),
                inline=False
            )
        embed.set_footer(text=f"Removido por {ctx.author}")
        await ctx.send(embed=embed)
    async def promover_video(self, ctx, entrada: str = None):
        """Move um vídeo para ser o próximo a tocar"""

        if not entrada:
            await ctx.send("\u274c Use: `&promover <posição>` ou `&promover <video_id>`\nExemplos: `&promover 6` | `&promover dQw4w9WgXcQ`")
            return

        playlist = self.carregar_playlist()
        if not playlist:
            await ctx.send("\u26a0\ufe0f A playlist está vazia.")
            return

        video = None
        if entrada.isdigit():
            posicao = int(entrada)
            index = posicao - 1
            if index < 0 or index >= len(playlist):
                await ctx.send(f"\u274c Posição inválida. A playlist tem {len(playlist)} vídeos.")
                return
            video = playlist[index]
        else:
            video_id = self.extrair_video_id(entrada) or entrada.strip()
            video = next((v for v in playlist if v.get('video_id') == video_id), None)
            if not video:
                await ctx.send(f"\u274c Não encontrei nenhum vídeo com ID `{video_id}` na playlist.")
                return

        video_id = video.get('video_id')

        index_video = next((i for i, v in enumerate(playlist) if v.get('video_id') == video_id), None)
        if index_video is None:
            await ctx.send("❌ Erro interno: vídeo não encontrado.")
            return

        if index_video == self.playlist_index:
            await ctx.send("⚠️ Este vídeo já está tocando.")
            return

        next_index = (self.playlist_index + 1) % len(playlist)
        if index_video == next_index:
            nova_posicao = next_index + 1
            embed = discord.Embed(
                title="⏭️ Vídeo Promovido!",
                description=f"**{video.get('titulo', video_id)}** será o próximo a tocar.",
                color=0xfeca57
            )
            embed.set_thumbnail(url=video.get('thumbnail_url', ''))
            embed.add_field(name="Nova Posição", value=str(nova_posicao), inline=True)
            embed.add_field(name="Canal", value=video.get('canal', 'Desconhecido'), inline=True)
            embed.set_footer(text=f"Promovido por {ctx.author}")
            await ctx.send(embed=embed)
            return

        # Remove da posição atual
        playlist.pop(index_video)
        if index_video < self.playlist_index:
            self.playlist_index -= 1

        # Insere logo após o atual
        next_pos = self.playlist_index + 1
        playlist.insert(next_pos, video)

        for i, v in enumerate(playlist):
            v['posicao'] = i + 1

        self.salvar_playlist(playlist)
        logger.info(f'[PROMOTE] {video_id} ("{video.get("titulo", "?")}") movido para posição {next_pos + 1}')

        embed = discord.Embed(
            title="⏭️ Vídeo Promovido!",
            description=f"**{video.get('titulo', video_id)}** será o próximo a tocar.",
            color=0xfeca57
        )
        embed.set_thumbnail(url=video.get('thumbnail_url', ''))
        embed.add_field(name="Nova Posição", value=str(next_pos + 1), inline=True)
        embed.add_field(name="Canal", value=video.get('canal', 'Desconhecido'), inline=True)
        embed.set_footer(text=f"Promovido por {ctx.author}")
        await ctx.send(embed=embed)
    async def limpar_playlist(self, ctx):
        """Limpa toda a playlist"""

        playlist = self.carregar_playlist()
        if not playlist:
            await ctx.send("⚠️ A playlist já está vazia.")
            return

        total = len(playlist)
        self.salvar_playlist([])
        self.playlist_index = 0
        logger.info(f'[CLEAR] Playlist limpa por {ctx.author}')
        embed = discord.Embed(
            title="🗑️ Playlist Limpa!",
            description=f"**{total}** vídeo(s) removido(s).",
            color=0xff0000
        )
        embed.set_footer(text=f"Limpa por {ctx.author}")
        await ctx.send(embed=embed)
    async def pular_video(self, ctx):
        playlist = self.carregar_playlist()
        if not playlist:
            await ctx.send('❌ Playlist vazia.')
            return

        if self.shuffle_mode:
            self.playlist_index = self._proximo_aleatorio(playlist)
            label = '🔀 Pulado (aleatório)'
        else:
            self.playlist_index = (self.playlist_index + 1) % len(playlist)
            label = '⏭️ Vídeo Pulado'

        video = playlist[self.playlist_index]
        embed = discord.Embed(
            title=label,
            description=f"Próximo: [{video.get('titulo', 'Desconhecido')}]({video.get('embed_url', '#')})",
            color=0x00ff00
        )
        embed.set_thumbnail(url=video.get('thumbnail_url', ''))
        embed.set_footer(text='O vídeo foi pulado com sucesso.')
        await ctx.send(embed=embed)
                            
    # ===================================================
    # Funções de busca e adição por busca
    # ===================================================
        
    async def adicionar_por_busca(self, ctx, termo, bot):
        await ctx.send(f'🔍 {ctx.author.mention} Buscando vídeos para "{termo}"...')
        resultados = await self.buscar_videos_youtube(termo)
        
        if not resultados:
            await ctx.send('❌ Nenhum vídeo encontrado para o termo de busca fornecido.')
            return
        
        emojis = ['1️⃣', '2️⃣', '3️⃣', '4️⃣', '5️⃣']
        descricao = ''
        
        for i, video in enumerate(resultados):
            descricao += f"{emojis[i]} **{video['titulo']}**\nCanal: {video['canal']}\nDuração: {video['duracao_formatada']}\n\n"
        
        embed = discord.Embed(
            title="Selecione um vídeo para adicionar à playlist",
            description=descricao,
            color=0x00ff00
        )
        msg = await ctx.send(embed=embed)
        
        for emoji in emojis[:len(resultados)]:
            await msg.add_reaction(emoji)
            
        def check(reaction, user):
            return( 
                   user == ctx.author
                   and reaction.message.id == msg.id
                   and reaction.emoji in emojis
                )
        try:
            reaction, user = await bot.wait_for('reaction_add', timeout=30.0, check=check)
        except asyncio.TimeoutError:
            await msg.edit(content='⏰ Tempo esgotado. Por favor, tente novamente.', embed=None)
            return
        
        indice = emojis.index(reaction.emoji)
        video = resultados[indice]
        url = f"https://www.youtube.com/watch?v={video['video_id']}"
        
        await self.adicionar_por_url(ctx, url)
    
    # ===================================================
    # Funções de manipulação da playlist
    # ===================================================    
        
    async def adicionar_por_url(self, ctx, url):
            
            video_id = self.extrair_video_id(url)
            if not video_id:
                await ctx.send('URL inválida. Por favor, forneça uma URL válida do YouTube.')
                return
            
            embed_url = f'https://www.youtube.com/watch?v={video_id}'
            thumbnail_url = f'https://img.youtube.com/vi/{video_id}/hqdefault.jpg'
            
            playlist = self.carregar_playlist()
            
            if any(item['video_id'] == video_id for item in playlist):
                await ctx.send('⚠️ Este vídeo já está na playlist.')
                return
            
            # Obtém informações do vídeo
            await ctx.send(f'🔍 {ctx.author.mention} Obtendo informações do vídeo...')
            info_video = await self.obter_info_video(url)

            if info_video and info_video.get('geo_blocked'):
                await ctx.send(
                    f'🌍 Este vídeo está bloqueado na sua região e não pode ser adicionado à playlist.'
                )
                return

            registro = {
                'video_id': video_id,
                'titulo': info_video['titulo'] if info_video else None,
                'duracao': info_video['duracao'] if info_video else None,
                'duracao_formatada': info_video['duracao_formatada'] if info_video else None,
                'canal': info_video['canal'] if info_video else None,
                'embed_url': embed_url,
                'thumbnail_url': thumbnail_url,
                'adicionado_por': str(ctx.author),
                'data_adicionado': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'url': url,
                'status': 'pendente',
                'posicao': len(playlist) + 1,
                'tocado': False,
            }
            
            playlist.append(registro)
            self.salvar_playlist(playlist)
            logger.info(f'[ADD] "{registro["titulo"]}" ({video_id}) por {ctx.author} — pos {registro["posicao"]}')
            
            embed = discord.Embed(
                title=info_video['titulo'] if info_video else 'Vídeo Adicionado à Playlist',
                color=0x00ff00,
                url=embed_url
            )
            embed.set_thumbnail(url=thumbnail_url)
            embed.add_field(name="Adicionado por", value=str(ctx.author), inline=True)
            if info_video:
                embed.add_field(name="Canal", value=info_video['canal'], inline=True)
                embed.add_field(name="Duração", value=info_video['duracao_formatada'], inline=True)
                embed.add_field(name="Visualizações", value=f"{info_video['views']:,}", inline=True)
                embed.add_field(name="Posição na Playlist", value=str(registro['posicao']), inline=True)
            embed.set_footer(text="Vídeo adicionado com sucesso! ✅")
            
            await ctx.send(embed=embed)

    # ===================================================
    # Função carregar e salvar playlist
    # ===================================================
    
    def carregar_playlist(self):
        # Se o arquivo não existir, retorna lista vazia
        if not os.path.exists(self.json_playlist):
            return []
    
        try:
            with open(self.json_playlist, 'r', encoding='utf-8') as f:
                conteudo = f.read().strip()
                # Se o arquivo está vazio, retorna lista vazia
                if not conteudo:
                    return []
                return json.loads(conteudo)
        except (json.JSONDecodeError, FileNotFoundError):
            # Se houver erro no JSON, retorna lista vazia
            return []
        
    def salvar_playlist(self, playlist):
        # Cria o diretório se não existir
        os.makedirs(os.path.dirname(self.json_playlist), exist_ok=True)
        
        with open(self.json_playlist, 'w', encoding='utf-8') as f:
            json.dump(playlist, f, ensure_ascii=False, indent=2)
    
    # ===================================================
    # Função obter ID do vídeo
    # ===================================================
    
    def extrair_video_id(self, url):
        # Expressão regular para extrair o ID do vídeo do YouTube
        regex = (
            r"(?:youtube\.com\/(?:watch\?v=|embed\/|shorts\/)|youtu\.be\/)"
            r"([a-zA-Z0-9_-]{11})"
        )
        
        # Procurar o ID do vídeo na URL fornecida
        match = re.search(regex, url)
        return match.group(1) if match else None
    
    # ===================================================
    # Funções de playlist inteira
    # ===================================================

    async def obter_videos_playlist(self, url, mix_limit=50):
        """Extrai todos os vídeos de uma playlist do YouTube usando yt-dlp (modo flat, sem baixar).
        YouTube Mix (list=RD...) são playlists dinâmicas/infinitas: usa URL original com v= e limita entradas.
        """
        import urllib.parse
        parsed = urllib.parse.urlparse(url)
        params = urllib.parse.parse_qs(parsed.query)
        playlist_id = params['list'][0] if 'list' in params else None

        # Mix do YouTube têm ID de playlist com prefixo "RD" (Radio/Mix automático)
        is_mix = bool(playlist_id and playlist_id.startswith('RD'))

        if is_mix:
            # Precisa da URL com v= para semear o mix;
            # playlistend evita paginação infinita
            extract_url = url
            ydl_opts = {
                'quiet': True,
                'no_warnings': True,
                'extract_flat': True,
                'ignoreerrors': True,
                'playlistend': mix_limit,
            }
            logger.debug(f'Extraindo YouTube Mix (limite {mix_limit}): {extract_url}')
        else:
            # Playlist normal: converte para URL canônica sem v=
            extract_url = f'https://www.youtube.com/playlist?list={playlist_id}' if playlist_id else url
            ydl_opts = {
                'quiet': True,
                'no_warnings': True,
                'extract_flat': 'in_playlist',
                'ignoreerrors': True,
            }
            logger.debug(f'Extraindo playlist: {extract_url}')

        if os.path.exists(self.cookies_file):
            ydl_opts['cookiefile'] = self.cookies_file

        def _extract():
            try:
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    info = ydl.extract_info(extract_url, download=False)
                    if not info:
                        return None, [], is_mix
                    # Se retornou um vídeo único no lugar de playlist
                    if info.get('_type') == 'video' or 'entries' not in info:
                        logger.warning('yt-dlp retornou vídeo único, esperava playlist')
                        return None, [], is_mix
                    titulo_pl = info.get('title') or ('YouTube Mix' if is_mix else 'Playlist')
                    entries = list(info.get('entries', []))
                    videos = []
                    for entry in entries:
                        if not entry or not entry.get('id'):
                            continue
                        vid_id = entry.get('id')
                        videos.append({
                            'video_id': vid_id,
                            'titulo': entry.get('title') or f'Vídeo {vid_id[:8]}',
                            'duracao': entry.get('duration') or 0,
                            'duracao_formatada': self.formatar_duracao(entry.get('duration') or 0),
                            'canal': entry.get('uploader') or entry.get('channel') or 'Desconhecido',
                            'embed_url': f'https://www.youtube.com/watch?v={vid_id}',
                            'thumbnail_url': f'https://img.youtube.com/vi/{vid_id}/hqdefault.jpg',
                        })
                    logger.info(f'["{titulo_pl}"] {len(videos)} vídeos extraídos (mix={is_mix})')
                    return titulo_pl, videos, is_mix
            except Exception as e:
                logger.error(f'Erro ao extrair playlist: {e}', exc_info=True)
                return None, [], is_mix

        return await asyncio.to_thread(_extract)

    async def adicionar_playlist(self, ctx, url):
        """Adiciona todos os vídeos de uma playlist à fila"""
        msg = await ctx.send(f'🔍 {ctx.author.mention} Carregando playlist, aguarde...')

        titulo_pl, videos, is_mix = await self.obter_videos_playlist(url)

        if not videos:
            await msg.edit(content='❌ Nenhum vídeo encontrado na playlist. Verifique se a URL é válida e se a playlist é pública.')
            return

        playlist = self.carregar_playlist()
        ids_existentes = {v['video_id'] for v in playlist}

        adicionados = 0
        duplicados = 0

        tipo_icone = '🎲' if is_mix else '📋'
        await msg.edit(content=f'{tipo_icone} **{titulo_pl}** — {len(videos)} vídeos encontrados. Adicionando...')

        for video in videos:
            if video['video_id'] in ids_existentes:
                duplicados += 1
                continue

            registro = {
                'video_id': video['video_id'],
                'titulo': video['titulo'],
                'duracao': video['duracao'],
                'duracao_formatada': video['duracao_formatada'],
                'canal': video['canal'],
                'embed_url': video['embed_url'],
                'thumbnail_url': video['thumbnail_url'],
                'adicionado_por': str(ctx.author),
                'data_adicionado': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'url': video['embed_url'],
                'status': 'pendente',
                'posicao': len(playlist) + 1,
                'tocado': False,
            }
            playlist.append(registro)
            ids_existentes.add(video['video_id'])
            adicionados += 1

        self.salvar_playlist(playlist)

        embed = discord.Embed(
            title=f'{tipo_icone} {titulo_pl}',
            color=0x00ff00,
            url=url
        )
        embed.add_field(name='✅ Adicionados', value=str(adicionados), inline=True)
        embed.add_field(name='⚠️ Já na fila', value=str(duplicados), inline=True)
        embed.add_field(name='📊 Total na fila', value=str(len(playlist)), inline=True)
        embed.set_footer(text=f'Adicionado por {ctx.author}')
        await msg.edit(content=None, embed=embed)

    # ===================================================
    # Funções de busca no YouTube usando yt-dlp
    # ===================================================
    
    async def obter_info_video(self, url):
        """Obtém informações do vídeo do YouTube usando yt-dlp"""
        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'extract_flat': False,
            'noplaylist': True,
            'js_runtimes': {'node': {}},
        }

        if os.path.exists(self.cookies_file):
            ydl_opts['cookiefile'] = self.cookies_file
        if self.proxy:
            ydl_opts['proxy'] = self.proxy

        def _extract():
            try:
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    info = ydl.extract_info(url, download=False)
                    return {
                        'titulo': info.get('title', 'Título não disponível'),
                        'duracao': info.get('duration', 0),
                        'duracao_formatada': self.formatar_duracao(info.get('duration', 0)),
                        'canal': info.get('uploader', 'Desconhecido'),
                        'views': info.get('view_count', 0),
                    }
            except Exception as e:
                if _is_geo_blocked(str(e)):
                    return {'geo_blocked': True}
                logger.error(f'Erro ao obter info do vídeo: {e}', exc_info=True)
                return None

        return await asyncio.to_thread(_extract)
    
    # ===================================================
    # Função para formatar duração
    # ===================================================
    
    def formatar_duracao(self, segundos):
        """Converte segundos para formato HH:MM:SS ou MM:SS"""
        if not segundos:
            return "00:00"
        
        segundos = int(segundos)  # Converte para inteiro
        
        horas = segundos // 3600
        minutos = (segundos % 3600) // 60
        segs = segundos % 60
        
        if horas > 0:
            return f"{horas:02d}:{minutos:02d}:{segs:02d}"
        return f"{minutos:02d}:{segs:02d}"
    
    # ===================================================
    # Função para buscar vídeos pelo termo de busca no YouTube
    # ===================================================
    
    async def buscar_videos_youtube(self, termo_busca, max_resultados=5):
        """Busca vídeos no YouTube usando yt-dlp"""
        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'extract_flat': True,
            'default_search': 'ytsearch',
            'noplaylist': True,
            'http_headers': {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Accept-Language': 'pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7',
            },
        }
        
        def _search():
            try:
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    search_query = f"ytsearch{max_resultados}:{termo_busca}"
                    info = ydl.extract_info(search_query, download=False)
                    videos = []
                    for entry in info.get('entries', []):
                        videos.append({
                            'video_id': entry.get('id'),
                            'titulo': entry.get('title'),
                            'url': entry.get('webpage_url'),
                            'canal': entry.get('uploader'),
                            'duracao_formatada': self.formatar_duracao(entry.get('duration'))
                        })
                    return videos
            except Exception as e:
                logger.error(f'Erro ao buscar vídeos: {e}', exc_info=True)
                return []
        
        # Executa em thread separada para não bloquear o event loop
        return await asyncio.to_thread(_search)

if __name__ == "__main__":
    bot = MyBot()
    bot.run()