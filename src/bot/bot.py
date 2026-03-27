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
from src.logger import get_logger

logger = get_logger(__name__)

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
            logger.info(f'Bot conectado como {bot.user} (ID: {bot.user.id})')
        
        
        @bot.command(name='skip', aliases=['pular', 'next'])
        async def skip(ctx):
            logger.info(f'[SKIP] solicitado por {ctx.author} em #{ctx.channel}')
            await self.pular_video(ctx)
        
        @bot.command(name='previous', aliases=['voltar', 'anterior'])
        async def previous(ctx):
            logger.info(f'[PREVIOUS] solicitado por {ctx.author} em #{ctx.channel}')
            await self.voltar_video(ctx)
        
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
    
    async def remover_video(self, ctx, entrada: str = None):
        """Remove um vídeo da playlist por posição, ID ou URL"""
        import aiohttp

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
                            embed.add_field(name="Posição", value=posicao_label, inline=True)
                            embed.add_field(name="ID", value=f"`{video_id}`", inline=True)
                            embed.add_field(name="Canal", value=video.get('canal', 'Desconhecido'), inline=True)
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
            logger.error(f'Erro ao remover vídeo: {e}', exc_info=True)
            await ctx.send(f"❌ Erro ao remover vídeo: {e}")
    async def promover_video(self, ctx, entrada: str = None):
        """Move um vídeo para ser o próximo a tocar"""
        import aiohttp

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

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(f'http://localhost:5000/api/playlist/promote/{video_id}') as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        if data.get('success'):
                            embed = discord.Embed(
                                title="\u23ed\ufe0f Vídeo Promovido!",
                                description=f"**{video.get('titulo', video_id)}** será o próximo a tocar.",
                                color=0xfeca57
                            )
                            embed.set_thumbnail(url=video.get('thumbnail_url', ''))
                            embed.add_field(name="Nova Posição", value=str(data.get('nova_posicao', '?')), inline=True)
                            embed.add_field(name="Canal", value=video.get('canal', 'Desconhecido'), inline=True)
                            embed.set_footer(text=f"Promovido por {ctx.author}")
                            await ctx.send(embed=embed)
                        else:
                            await ctx.send(f"\u26a0\ufe0f {data.get('message', 'Erro ao promover.')}")
                    else:
                        await ctx.send("\u274c Falha ao conectar com o servidor.")
        except Exception as e:
            logger.error(f'Erro ao promover vídeo: {e}', exc_info=True)
            await ctx.send(f"\u274c Erro ao promover vídeo: {e}")
    async def limpar_playlist(self, ctx):
        """Limpa toda a playlist via API"""
        import aiohttp

        playlist = self.carregar_playlist()
        if not playlist:
            await ctx.send("⚠️ A playlist já está vazia.")
            return

        try:
            async with aiohttp.ClientSession() as session:
                async with session.delete('http://localhost:5000/api/playlist/clear') as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        if data.get('success'):
                            embed = discord.Embed(
                                title="🗑️ Playlist Limpa!",
                                description=f"**{len(playlist)}** vídeo(s) removido(s).",
                                color=0xff0000
                            )
                            embed.set_footer(text=f"Limpa por {ctx.author}")
                            await ctx.send(embed=embed)
                        else:
                            await ctx.send(f"⚠️ {data.get('message', 'Erro ao limpar.')}")
                    else:
                        await ctx.send("❌ Falha ao conectar com o servidor.")
        except Exception as e:
            logger.error(f'Erro ao limpar playlist: {e}', exc_info=True)
            await ctx.send(f"❌ Erro ao limpar playlist: {e}")
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