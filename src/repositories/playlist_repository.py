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
        self._sync_lock = threading.RLock()

    def _get_playlist_path(self, guild_id: int) -> Path:
        """Retorna o caminho do arquivo de playlist para um servidor."""
        return self.data_dir / "guilds" / str(guild_id) / "playlist.json"

    def load(self, guild_id: int) -> list:
        """Retorna a playlist de um servidor como lista de dicts. Retorna [] se vazia/inexistente."""
        with self._sync_lock:
            return self._load_unlocked(guild_id)

    def _load_unlocked(self, guild_id: int) -> list:
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

    def _save_unlocked(self, guild_id: int, playlist: list) -> None:
        path = self._get_playlist_path(guild_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = path.with_suffix('.json.tmp')
        with open(temp_path, 'w', encoding='utf-8') as f:
            json.dump(playlist, f, ensure_ascii=False, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(temp_path, path)

    def save(self, guild_id: int, playlist: list) -> None:
        """Persiste a playlist de um servidor no disco de forma thread-safe (síncrono)."""
        with self._sync_lock:
            self._save_unlocked(guild_id, playlist)

    async def save_async(self, guild_id: int, playlist: list) -> None:
        """Persiste a playlist de um servidor no disco de forma thread-safe (assíncrono)."""
        await asyncio.to_thread(self.save, guild_id, playlist)

    def add_unique(self, guild_id: int, videos: list[dict]) -> tuple[list, list[int]]:
        """Adiciona vídeos sem duplicar IDs em uma única transação."""
        with self._sync_lock:
            playlist = self._load_unlocked(guild_id)
            ids = {item.get('video_id') for item in playlist}
            novos_indices = []
            for video in videos:
                video_id = video.get('video_id')
                if not video_id or video_id in ids:
                    continue
                item = video.copy()
                item['posicao'] = len(playlist) + 1
                playlist.append(item)
                ids.add(video_id)
                novos_indices.append(len(playlist) - 1)
            if novos_indices:
                self._save_unlocked(guild_id, playlist)
            return playlist, novos_indices
