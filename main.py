import asyncio
import os
from pathlib import Path

import discord
from discord.ext import commands
from dotenv import load_dotenv

from src.logger import setup_logging, get_logger
from src.models.player_state import PlayerState
from src.repositories.playlist_repository import PlaylistRepository
from src.services.youtube_service import YouTubeService
from src.services.spotify_service import SpotifyService
from src.services.playlist_service import PlaylistService
from src.services.player_service import PlayerService

setup_logging()
logger = get_logger(__name__)

BASE_DIR = Path(__file__).parent


async def main() -> None:
    # --- Configurações ---
    load_dotenv(BASE_DIR / 'config.env')
    token = os.getenv('token_discord')
    proxy = os.getenv('ytdlp_proxy', '').strip() or None
    spotify_client_id = os.getenv('spotify_client_id', '').strip() or None
    spotify_client_secret = os.getenv('spotify_client_secret', '').strip() or None

    if proxy:
        logger.info(f'[PROXY] usando proxy para yt-dlp: {proxy}')
    if spotify_client_id:
        logger.info('[SPOTIFY] credenciais carregadas.')
    else:
        logger.info('[SPOTIFY] não configurado (spotify_client_id ausente).')

    # --- Infra ---
    cache_dir = BASE_DIR / 'cache'
    cache_dir.mkdir(parents=True, exist_ok=True)
    cookies_file = str(BASE_DIR / 'config' / 'cookies.txt')
    json_playlist = str(BASE_DIR / 'data' / 'playlist.json')

    repo = PlaylistRepository(json_playlist)
    yt = YouTubeService(cache_dir=cache_dir, cookies_file=cookies_file, proxy=proxy)
    spotify = SpotifyService(client_id=spotify_client_id, client_secret=spotify_client_secret)

    # --- Estado e serviços ---
    state = PlayerState()
    playlist_svc = PlaylistService(repo=repo, yt=yt, spotify=spotify, state=state)
    player_svc = PlayerService(state=state, repo=repo, yt=yt, playlist_svc=playlist_svc)

    # Retoma da última posição não tocada
    playlist_svc.encontrar_proxima_nao_tocada()

    # --- Bot ---
    intents = discord.Intents.default()
    intents.message_content = True
    bot = commands.Bot(command_prefix='&', intents=intents, help_command=None)

    @bot.event
    async def on_ready():
        logger.info(f'Bot conectado como {bot.user} (ID: {bot.user.id})')

    # --- Cogs ---
    shared = dict(
        state=state,
        repo=repo,
        playlist_svc=playlist_svc,
        player_svc=player_svc,
    )
    from src.cogs.music_cog import MusicCog
    from src.cogs.playlist_cog import PlaylistCog
    await bot.add_cog(MusicCog(bot, **shared))
    await bot.add_cog(PlaylistCog(bot, **{k: v for k, v in shared.items() if k != 'player_svc'}))

    await bot.start(token)


if __name__ == '__main__':
    asyncio.run(main())
