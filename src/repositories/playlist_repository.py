"""Acesso à camada de persistência da playlist (JSON em disco) - Multi-Guild."""
import asyncio
import json
import os
import threading
from pathlib import Path

from src.logger import get_logger

logger = get_logger(__name__)


class PlaylistRepository:
    """Carrega e salva playlists por servidor (guild) com thread-safety."""

    def __init__(self, data_dir: str) -> None:
        self.data_dir = Path(data_dir)
        self._sync_lock = threading.Lock()
        self._async_lock = asyncio.Lock()

    def _get_playlist_path(self, guild_id: int) -> Path:
        """Retorna o caminho do arquivo de playlist para um servidor."""
        return self.data_dir / "guilds" / str(guild_id) / "playlist.json"

    def load(self, guild_id: int) -> list:
        """Retorna a playlist de um servidor como lista de dicts. Retorna [] se vazia/inexistente."""
        path = self._get_playlist_path(guild_id)
        if not path.exists():
            return []
        try:
            with open(path, 'r', encoding='utf-8') as f:
                conteudo = f.read().strip()
                return json.loads(conteudo) if conteudo else []
        except (json.JSONDecodeError, FileNotFoundError) as e:
            logger.warning(f'[REPO] Erro ao carregar playlist do servidor {guild_id}: {e}')
            return []

    def save(self, guild_id: int, playlist: list) -> None:
        """Persiste a playlist de um servidor no disco de forma thread-safe (síncrono)."""
        with self._sync_lock:
            path = self._get_playlist_path(guild_id)
            path.parent.mkdir(parents=True, exist_ok=True)
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(playlist, f, ensure_ascii=False, indent=2)

    async def save_async(self, guild_id: int, playlist: list) -> None:
        """Persiste a playlist de um servidor no disco de forma thread-safe (assíncrono)."""
        async with self._async_lock:
            path = self._get_playlist_path(guild_id)
            path.parent.mkdir(parents=True, exist_ok=True)
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(playlist, f, ensure_ascii=False, indent=2)
