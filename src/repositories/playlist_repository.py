"""Acesso à camada de persistência da playlist (JSON em disco)."""
import json
import os

from src.logger import get_logger

logger = get_logger(__name__)


class PlaylistRepository:
    """Carrega e salva a playlist em arquivo JSON."""

    def __init__(self, json_path: str) -> None:
        self.json_path = json_path

    def load(self) -> list:
        """Retorna a playlist como lista de dicts. Retorna [] se vazia/inexistente."""
        if not os.path.exists(self.json_path):
            return []
        try:
            with open(self.json_path, 'r', encoding='utf-8') as f:
                conteudo = f.read().strip()
                return json.loads(conteudo) if conteudo else []
        except (json.JSONDecodeError, FileNotFoundError) as e:
            logger.warning(f'[REPO] Erro ao carregar playlist: {e}')
            return []

    def save(self, playlist: list) -> None:
        """Persiste a playlist no disco."""
        os.makedirs(os.path.dirname(self.json_path), exist_ok=True)
        with open(self.json_path, 'w', encoding='utf-8') as f:
            json.dump(playlist, f, ensure_ascii=False, indent=2)
