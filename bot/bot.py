import discord
from discord.ext import commands
from dotenv import load_dotenv
import os
import json
import re
from datetime import datetime
import random

class MyBot():
    def __init__(self):
        
        diretorio_atual = os.path.dirname(__file__)
        diretorio_config = os.path.join(diretorio_atual, '..', 'config', 'config.env')
        self.arquivo_fox = discord.File("image/fox.jpg")
        
        self.json_playlist = os.path.join(diretorio_atual, '..', 'data', 'playlist.json')
        
        load_dotenv(diretorio_config)
        self.token = os.getenv('token_discord')
    
    def run(self):
        intents = discord.Intents.default()  # Corrigido: era 'itents'
        intents.message_content = True
        
        bot = commands.Bot(command_prefix='&', intents=intents)
        
        @bot.event
        async def on_ready():
            print(f'Bot conectado como {bot.user}')
        
        @bot.command()
        async def anjo(ctx):
            await ctx.send('Namoral anjo brocha, conhece esse ritual aqui?',
                           file= self.arquivo_fox)
        
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
        
        @bot.command()
        async def add(ctx, url: str):
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
            
            registro = {
                'video_id': video_id,
                'titulo': None,
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
            
            embed = discord.Embed(title='Vídeo Adicionado à Playlist', color=0x00ff00, url=embed_url)
            embed.set_thumbnail(url=thumbnail_url)
            embed.add_field(name="Adicionado por", value=str(ctx.author), inline=True)  # Corrigido: era 'aadd_field' e 'adcionado'
            
            await ctx.send(embed=embed)
            
            
            
        bot.run(self.token)

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
    
    def extrair_video_id(self, url):
        # Expressão regular para extrair o ID do vídeo do YouTube
        regex = (
            r"(?:youtube\.com\/(?:watch\?v=|embed\/|shorts\/)|youtu\.be\/)"
            r"([a-zA-Z0-9_-]{11})"
        )
        
        # Procurar o ID do vídeo na URL fornecida
        match = re.search(regex, url)
        return match.group(1) if match else None
    
    
        

if __name__ == "__main__":
    bot = MyBot()
    bot.run()