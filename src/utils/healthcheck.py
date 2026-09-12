"""Healthcheck para diagnóstico de dependências."""
import asyncio
import shutil
from pathlib import Path

from src.logger import get_logger

logger = get_logger(__name__)


class HealthCheck:
    """Verifica se dependências críticas estão funcionando."""

    @staticmethod
    def check_ffmpeg() -> tuple[bool, str]:
        """Verifica se FFmpeg está instalado e acessível."""
        ffmpeg_path = shutil.which('ffmpeg')
        if not ffmpeg_path:
            return False, 'FFmpeg não encontrado no PATH'
        return True, f'FFmpeg OK: {ffmpeg_path}'

    @staticmethod
    def check_cache_dir(cache_dir: Path) -> tuple[bool, str]:
        """Verifica se o diretório de cache é acessível."""
        try:
            cache_dir.mkdir(parents=True, exist_ok=True)
            test_file = cache_dir / '.health_check'
            test_file.write_text('ok')
            test_file.unlink()
            return True, f'Cache dir OK: {cache_dir}'
        except Exception as e:
            return False, f'Erro ao acessar cache: {e}'

    @staticmethod
    def check_cookies(cookies_file: str) -> tuple[bool, str]:
        """Verifica se arquivo de cookies existe e é válido."""
        if not cookies_file:
            return False, 'Caminho de cookies não configurado'
        path = Path(cookies_file)
        if not path.exists():
            return False, f'Arquivo de cookies não encontrado: {cookies_file}'
        try:
            with open(cookies_file, 'r') as f:
                f.read(1024)
            return True, f'Cookies OK: {cookies_file}'
        except Exception as e:
            return False, f'Erro ao ler cookies: {e}'

    @staticmethod
    async def check_spotify(spotify_service) -> tuple[bool, str]:
        """Verifica se Spotify está configurado."""
        if not spotify_service or not spotify_service.client_id:
            return False, 'Spotify não configurado (client_id ausente)'
        try:
            await asyncio.wait_for(spotify_service.get_token(), timeout=5.0)
            return True, 'Spotify OK: autenticação bem-sucedida'
        except asyncio.TimeoutError:
            return False, 'Spotify: timeout ao verificar autenticação'
        except Exception as e:
            return False, f'Spotify: erro na autenticação: {type(e).__name__}: {str(e)[:50]}'

    @staticmethod
    async def full_check(
        ffmpeg_ok: bool = None,
        cache_dir: Path = None,
        cookies_file: str = None,
        spotify_service = None,
    ) -> dict:
        """Executa todos os checks e retorna relatório."""
        results = {}

        if ffmpeg_ok is not None or cache_dir or cookies_file or spotify_service:
            results['ffmpeg'], results['ffmpeg_msg'] = HealthCheck.check_ffmpeg()
            if cache_dir:
                results['cache'], results['cache_msg'] = HealthCheck.check_cache_dir(cache_dir)
            if cookies_file:
                results['cookies'], results['cookies_msg'] = HealthCheck.check_cookies(cookies_file)
            if spotify_service:
                results['spotify'], results['spotify_msg'] = await HealthCheck.check_spotify(
                    spotify_service
                )

        return results
