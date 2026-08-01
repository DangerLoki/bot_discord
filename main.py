import asyncio
import atexit
import os
import sys
from pathlib import Path

# Garante que o bundle do PyInstaller encontre os certificados SSL
try:
    import certifi
    os.environ.setdefault('SSL_CERT_FILE', certifi.where())
    os.environ.setdefault('REQUESTS_CA_BUNDLE', certifi.where())
except ImportError:
    pass

# DEBUG temporário — remove após confirmar que nacl funciona no binário
try:
    import nacl.secret
    print(f'[DEBUG] nacl OK: {nacl.__version__}')
except Exception as e:
    import traceback
    print(f'[DEBUG] nacl FALHOU: {type(e).__name__}: {e}')
    traceback.print_exc()

import discord
from discord.ext import commands
from dotenv import load_dotenv

from src.logger import get_logger, setup_logging
from src.models.player_state import PlayerState
from src.repositories.config_repository import ConfigRepository
from src.repositories.playlist_repository import PlaylistRepository
from src.services.player_service import PlayerService
from src.services.playlist_service import PlaylistService
from src.services.spotify_service import SpotifyService
from src.services.youtube_service import YouTubeService
from src.setup.cli_setup import check_ffmpeg, clear_token, inject_ffmpeg_to_path, run_setup

setup_logging()
logger = get_logger(__name__)

BASE_DIR = Path(__file__).parent
LOCK_FILE = BASE_DIR / 'logs' / 'bot.lock'


class ComandoForaDoPainelError(commands.CheckFailure):
    """Levantado quando um comando (que não seja &painel) é usado fora do canal do painel."""


def _pid_exists(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def _acquire_single_instance_lock() -> None:
    """Impede múltiplas instâncias simultâneas do bot no mesmo diretório."""
    LOCK_FILE.parent.mkdir(parents=True, exist_ok=True)
    current_pid = os.getpid()

    if LOCK_FILE.exists():
        try:
            existing_pid = int(LOCK_FILE.read_text(encoding='utf-8').strip() or '0')
        except ValueError:
            existing_pid = 0

        if existing_pid and existing_pid != current_pid and _pid_exists(existing_pid):
            print(f'[ERRO] Bot já está em execução (PID: {existing_pid}).')
            raise SystemExit(1)

    LOCK_FILE.write_text(str(current_pid), encoding='utf-8')

    def _cleanup_lock() -> None:
        if not LOCK_FILE.exists():
            return
        try:
            pid_in_file = int(LOCK_FILE.read_text(encoding='utf-8').strip() or '0')
        except ValueError:
            pid_in_file = 0
        if pid_in_file == current_pid:
            LOCK_FILE.unlink(missing_ok=True)

    atexit.register(_cleanup_lock)


async def main() -> None:
    # --- Configuração inicial (cria config.env se necessário) ---
    inject_ffmpeg_to_path()
    check_ffmpeg()
    run_setup()

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
    json_config = str(BASE_DIR / 'data' / 'bot_config.json')

    repo = PlaylistRepository(json_playlist)
    config_repo = ConfigRepository(json_config)
    yt = YouTubeService(cache_dir=cache_dir, cookies_file=cookies_file, proxy=proxy)
    spotify = SpotifyService(client_id=spotify_client_id, client_secret=spotify_client_secret)

    # --- Estado e serviços ---
    state = PlayerState()
    state.player_channel_id = config_repo.load().get('player_channel_id')
    playlist_svc = PlaylistService(repo=repo, yt=yt, spotify=spotify, state=state)
    player_svc = PlayerService(state=state, repo=repo, yt=yt, playlist_svc=playlist_svc)
    playlist_svc.player_svc = player_svc

    # Retoma da última posição não tocada
    playlist_svc.encontrar_proxima_nao_tocada()

    # --- Bot ---
    intents = discord.Intents.default()
    intents.message_content = True
    bot = commands.Bot(command_prefix='&', intents=intents, help_command=None)

    async def _apenas_no_painel(ctx: commands.Context) -> bool:
        """Restringe todos os comandos ao canal definido, exceto o próprio &definircanal."""
        if ctx.command and ctx.command.qualified_name == 'definircanal':
            return True
        if not ctx.guild:
            return True
        if ctx.channel.id == state.player_channel_id:
            return True
        raise ComandoForaDoPainelError()

    bot.add_check(_apenas_no_painel)

    @bot.event
    async def on_ready():
        logger.info(f'Bot conectado como {bot.user} (ID: {bot.user.id})')
        try:
            synced = await bot.tree.sync()
            logger.info(f'[SLASH] {len(synced)} slash command(s) sincronizados.')
        except Exception as e:
            logger.error(f'[SLASH] Erro ao sincronizar slash commands: {e}')

        if not getattr(bot, '_painel_view_registrada', False):
            bot.add_view(player_svc.view)
            bot.add_view(player_svc.queue_view)
            bot._painel_view_registrada = True
            logger.info('[PAINEL] views persistentes de controles registradas.')

        if state.player_channel_id:
            canal = bot.get_channel(state.player_channel_id)
            if canal:
                player_svc.iniciar_limpeza_canal(canal)
                logger.info(
                    f'[CANAL] retomando canal de comandos salvo: #{canal.name} ({canal.id})'
                )
            else:
                logger.warning(
                    f'[CANAL] canal salvo (ID {state.player_channel_id}) não encontrado.'
                )

    @bot.event
    async def on_command_error(ctx: commands.Context, error: commands.CommandError) -> None:
        if isinstance(error, ComandoForaDoPainelError):
            if state.player_channel_id:
                texto = f'❌ Use os comandos no canal <#{state.player_channel_id}>.'
            else:
                texto = '❌ Primeiro defina o canal de comandos com `&definircanal`.'
            try:
                aviso = await ctx.send(texto)
            except discord.HTTPException:
                return
            mensagem = getattr(ctx, 'message', None)
            if mensagem is not None:
                try:
                    await mensagem.delete()
                except (discord.Forbidden, discord.NotFound, discord.HTTPException):
                    pass
            await asyncio.sleep(5)
            try:
                await aviso.delete()
            except (discord.NotFound, discord.HTTPException):
                pass
            return
        if isinstance(error, commands.CommandNotFound):
            return
        if isinstance(error, commands.MissingRequiredArgument):
            nome_comando = ctx.command.qualified_name if ctx.command else '?'
            try:
                aviso = await ctx.send(
                    f'❌ Faltou informar `{error.param.name}`. '
                    f'Uso: `&{nome_comando} <{error.param.name}>`'
                )
            except discord.HTTPException:
                return
            await asyncio.sleep(6)
            try:
                await aviso.delete()
            except (discord.NotFound, discord.HTTPException):
                pass
            return
        if isinstance(error, commands.UserInputError):
            try:
                await ctx.send(f'❌ {error}')
            except discord.HTTPException:
                pass
            return
        logger.error(f'[COMANDO] erro não tratado: {error}', exc_info=error)

    # --- Cogs ---
    shared = dict(
        state=state,
        repo=repo,
        playlist_svc=playlist_svc,
        player_svc=player_svc,
    )
    from src.cogs.music_cog import MusicCog
    from src.cogs.playlist_cog import PlaylistCog
    await bot.add_cog(MusicCog(bot, config_repo=config_repo, **shared))
    await bot.add_cog(PlaylistCog(bot, **{k: v for k, v in shared.items() if k != 'player_svc'}))

    try:
        await bot.start(token)
    except discord.errors.LoginFailure:
        print()
        print("\033[1m\033[31m✖ Token do Discord inválido ou expirado.\033[0m")
        print("  O token salvo será apagado. Informe o novo token abaixo.\n")
        logger.error('[TOKEN] Token inválido. Limpando config.env e solicitando novo token.')
        await bot.close()
        clear_token()
        run_setup(force=False)
        print("\033[1m\033[32m↺ Reiniciando o bot...\033[0m\n")
        os.execv(sys.executable, [sys.executable] + sys.argv)


if __name__ == '__main__':
    _acquire_single_instance_lock()
    asyncio.run(main())
