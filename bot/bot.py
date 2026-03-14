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
        diretorio_config = os.path.join(diretorio_atual, '..', 'config.env')
        self.arquivo_fox = discord.File("image/fox.jpg")
        
        self.json_playlist = os.path.join(diretorio_atual, '..', 'data', 'playlist.json')
        self.cookies_file = os.path.join(diretorio_atual, '..', 'config', 'cookies.txt')  # Adicione isso
        
        load_dotenv(diretorio_config)
        self.token = os.getenv('token_discord')
    
    # ===================================================
    # Função para rodar o bot
    # ===================================================
    
    def run(self):
        intents = discord.Intents.default()  # Corrigido: era 'itents'
        intents.message_content = True
        
        bot = commands.Bot(command_prefix='&', intents=intents)
        
        # evento on_ready
        @bot.event
        async def on_ready():
            print(f'Bot conectado como {bot.user}')
        
        
        @bot.command(name='skip', aliases=['pular', 'next'])
        async def skip(ctx):
            await self.pular_video(ctx)
        
        @bot.command(name='previous', aliases=['voltar', 'anterior'])
        async def previous(ctx):
            await self.voltar_video(ctx)
        
        @bot.command(name='remove', aliases=['remover', 'rm', 'delete'])
        async def remove(ctx, posicao: int = None):
            """Remove um vídeo da playlist pela posição"""
            await self.remover_video(ctx, posicao)
        
        
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
            video_id = self.extrair_video_id(entrada)
            
            if entrada.startswith('http'):
                await self.adicionar_por_url(ctx, entrada)
            else:
                await self.adicionar_por_busca(ctx, entrada, bot)
        
        @bot.command()
        async def listar(ctx):
            playlist = self.carregar_playlist()
            view = PaginacaoPlaylist(playlist)
            await ctx.send(embed=view.criar_embed(), view=view)
        

        
        bot.run(self.token)
        
    async def voltar_video(self, ctx):
        
        import aiohttp
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post('http://localhost:5000/api/playlist/previous') as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        if data.get('success'):
                            video = data.get('video', {})
                            embed = discord.Embed(
                                title="⏭️ Vídeo Pulado",
                                description=f"O vídeo [{video.get('titulo', 'Desconhecido')}]({video.get('embed_url', '#')})",
                                color=0x00ff00
                            )
                            embed.set_thumbnail(url=video.get('thumbnail_url', ''))
                            embed.set_footer(text="O vídeo atual foi pulado com sucesso.")
                            await ctx.send(embed=embed)
                        else:
                            await ctx.send("❌ Não há vídeo para pular na playlist.")
                    else:
                        await ctx.send("❌ Falha ao conectar com o servidor de mídia.")
        except Exception as e:
            await ctx.send(f"❌ Ocorreu um erro ao tentar pular o vídeo: {e}")
    
    async def remover_video(self, ctx, posicao: int = None):
        """Remove um vídeo da playlist"""
        import aiohttp
        
        if posicao is None:
            await ctx.send("❌ Use: `&remove <posição>`\nExemplo: `&remove 5`")
            return
        
        playlist = self.carregar_playlist()
        
        if not playlist:
            await ctx.send("⚠️ A playlist está vazia.")
            return
        
        index = posicao - 1
        
        if index < 0 or index >= len(playlist):
            await ctx.send(f"❌ Posição inválida. A playlist tem {len(playlist)} vídeos.")
            return
        
        video = playlist[index]
        video_id = video.get('video_id')
        titulo = video.get('titulo', 'Desconhecido')
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.delete(f'http://localhost:5000/api/playlist/remove/{video_id}') as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        if data.get('success'):
                            embed = discord.Embed(
                                title="🗑️ Vídeo Removido!",
                                description=f"**{titulo}**",
                                color=0xff0000
                            )
                            embed.set_thumbnail(url=video.get('thumbnail_url', ''))
                            embed.add_field(name="Canal", value=video.get('canal', 'Desconhecido'), inline=True)
                            embed.add_field(name="Posição removida", value=str(posicao), inline=True)
                            
                            # Mostra o próximo vídeo se removeu o atual
                            if data.get('removeu_atual') and data.get('proximo_video'):
                                proximo = data.get('proximo_video')
                                embed.add_field(
                                    name="▶️ Tocando agora", 
                                    value=proximo.get('titulo', 'Desconhecido'), 
                                    inline=False
                                )
                            
                            embed.set_footer(text=f"Removido por {ctx.author}")
                            await ctx.send(embed=embed)
                        else:
                            await ctx.send(f"⚠️ {data.get('message', 'Erro ao remover.')}")
                    else:
                        await ctx.send("❌ Falha ao conectar com o servidor.")
        except Exception as e:
            await ctx.send(f"❌ Erro ao remover vídeo: {e}")
        
    async def pular_video(self, ctx):
        
        import aiohttp
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post('http://localhost:5000/api/playlist/skip') as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        if data.get('success'):
                            video = data.get('video', {})
                            embed = discord.Embed(
                                title="⏭️ Vídeo Pulado",
                                description=f"O vídeo [{video.get('titulo', 'Desconhecido')}]({video.get('embed_url', '#')})",
                                color=0x00ff00
                            )
                            embed.set_thumbnail(url=video.get('thumbnail_url', ''))
                            embed.set_footer(text="O vídeo atual foi pulado com sucesso.")
                            await ctx.send(embed=embed)
                        else:
                            await ctx.send("❌ Não há vídeo para pular na playlist.")
                    else:
                        await ctx.send("❌ Falha ao conectar com o servidor de mídia.")
        except Exception as e:
            await ctx.send(f"❌ Ocorreu um erro ao tentar pular o vídeo: {e}")
                            
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
            
            # Obtém informações do vídeo (agora assíncrono)
            await ctx.send(f'🔍 {ctx.author.mention} Obtendo informações do vídeo...')
            info_video = await self.obter_info_video(url)
            
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
                'posicao': len(playlist) + 1
            }
            
            playlist.append(registro)
            self.salvar_playlist(playlist)
            
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
    # Funções de busca no YouTube usando yt-dlp
    # ===================================================
    
    async def obter_info_video(self, url):
        """Obtém informações do vídeo do YouTube usando yt-dlp"""
        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'extract_flat': False,
            'noplaylist': True,
            'ignoreerrors': False,
            'geo_bypass': True,
            'geo_bypass_country': 'BR',
            # Usar cliente Android 
            'extractor_args': {
                'youtube': {
                    'player_client': ['android_music', 'android', 'ios'],
                    'skip': ['dash', 'hls'],
                }
            },
            'http_headers': {
                'User-Agent': 'com.google.android.youtube/17.36.4 (Linux; U; Android 12; BR) gzip',
            },
        }
        
        # Usa cookies se existir
        if os.path.exists(self.cookies_file):
            ydl_opts['cookiefile'] = self.cookies_file
        
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
                print(f"Erro ao obter info do vídeo: {e}")
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
                print(f"Erro ao buscar vídeos: {e}")
                return []
        
        # Executa em thread separada para não bloquear o event loop
        return await asyncio.to_thread(_search)

if __name__ == "__main__":
    bot = MyBot()
    bot.run()