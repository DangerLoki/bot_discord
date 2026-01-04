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
        itents = discord.Intents.default()
        itents.message_content = True
        
        bot = commands.Bot(command_prefix='&', intents=itents)
        
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
                await ctx.send('O número de lados deve ser pelo menos 1.')
                return
            
            resultado = random.randint(1, lados_int)
            
            await ctx.send(f'🎲 {ctx.author.mention} lançou um dado de {lados_int} lados e o resultado foi {resultado}')
        
        @bot.command()
        async def add(ctx, url: str):
            
        bot.run(self.token)

    def carregar_playlist(self):
        
        # se o arquivo nao existir, retorna lista vazia
        if not os.path.exists(self.json_playlist):
            return []
    
        with open(self.json_playlist, 'r', encoding='utf-8') as f:
            return json.load(f)
        
    def salvar_playlist(self, playlist):
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