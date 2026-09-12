"""Gerenciador de cache com limpeza automática de orfãos."""
import os
from pathlib import Path

from src.logger import get_logger

logger = get_logger(__name__)


class CacheManager:
    """Gerencia cache local e remove orfãos."""

    def __init__(self, cache_dir: Path) -> None:
        self.cache_dir = Path(cache_dir)

    def cleanup_orphaned_files(self, guild_id: int, video_ids_in_playlist: set[str]) -> None:
        """Remove arquivos de cache de um servidor que não estão mais na playlist.

        Args:
            guild_id: ID do servidor
            video_ids_in_playlist: Set de video_ids atualmente na playlist
        """
        guild_cache_dir = self.cache_dir / str(guild_id)
        if not guild_cache_dir.exists():
            return

        removed_count = 0
        try:
            for cache_file in guild_cache_dir.glob('*.opus'):
                video_id = cache_file.stem
                if video_id not in video_ids_in_playlist:
                    try:
                        cache_file.unlink()
                        removed_count += 1
                        logger.debug(f'[CACHE] removido arquivo orfão: {cache_file.name}')
                    except OSError as e:
                        logger.warning(f'[CACHE] erro ao remover {cache_file.name}: {e}')

            if removed_count > 0:
                logger.info(f'[CACHE:{guild_id}] limpeza: {removed_count} arquivo(s) orfão(s) removido(s)')
        except Exception as e:
            logger.error(f'[CACHE:{guild_id}] erro ao limpar orfãos: {e}')

    def get_cache_path(self, guild_id: int, video_id: str) -> Path:
        """Retorna o caminho do arquivo de cache para um servidor e video_id."""
        guild_cache_dir = self.cache_dir / str(guild_id)
        guild_cache_dir.mkdir(parents=True, exist_ok=True)
        return guild_cache_dir / f'{video_id}.opus'

    def cache_exists(self, guild_id: int, video_id: str) -> bool:
        """Verifica se existe cache para um servidor e video_id."""
        return self.get_cache_path(guild_id, video_id).exists()

    def get_cache_size_mb(self, guild_id: int = None) -> float:
        """Retorna o tamanho do cache em MB. Se guild_id=None, retorna tamanho total."""
        if not self.cache_dir.exists():
            return 0.0
        if guild_id is None:
            total_bytes = sum(f.stat().st_size for f in self.cache_dir.rglob('*.opus'))
        else:
            guild_cache_dir = self.cache_dir / str(guild_id)
            if not guild_cache_dir.exists():
                return 0.0
            total_bytes = sum(f.stat().st_size for f in guild_cache_dir.glob('*.opus'))
        return total_bytes / (1024 * 1024)
