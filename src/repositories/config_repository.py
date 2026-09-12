"""Acesso à camada de persistência de configurações - Multi-Guild."""
import asyncio
import json
import os
import threading
from pathlib import Path

from src.logger import get_logger

logger = get_logger(__name__)


class ConfigRepository:
    """Carrega e salva configurações por servidor (guild) em arquivo JSON com thread-safety."""

    def __init__(self, data_dir: str) -> None:
        self.data_dir = Path(data_dir)
        self._sync_lock = threading.Lock()
        self._async_lock = asyncio.Lock()

    def _get_config_path(self, guild_id: int) -> Path:
        """Retorna o caminho do arquivo de config para um servidor."""
        return self.data_dir / "guilds" / str(guild_id) / "config.json"

    def load(self, guild_id: int) -> dict:
        """Retorna as configurações de um servidor como dict. Retorna {} se vazio/inexistente."""
        path = self._get_config_path(guild_id)
        if not path.exists():
            return {}
        try:
            with open(path, encoding='utf-8') as f:
                conteudo = f.read().strip()
                return json.loads(conteudo) if conteudo else {}
        except (json.JSONDecodeError, OSError) as e:
            logger.warning(f'[REPO] Erro ao carregar config do servidor {guild_id}: {e}')
            return {}

    def save(self, guild_id: int, config: dict) -> None:
        """Persiste as configurações de um servidor no disco de forma thread-safe (síncrono)."""
        with self._sync_lock:
            path = self._get_config_path(guild_id)
            path.parent.mkdir(parents=True, exist_ok=True)
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(config, f, ensure_ascii=False, indent=2)

    async def save_async(self, guild_id: int, config: dict) -> None:
        """Persiste as configurações de um servidor no disco de forma thread-safe (assíncrono)."""
        async with self._async_lock:
            path = self._get_config_path(guild_id)
            path.parent.mkdir(parents=True, exist_ok=True)
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(config, f, ensure_ascii=False, indent=2)

    def set_valor(self, guild_id: int, chave: str, valor) -> None:
        """Atualiza uma única chave de um servidor, preservando as demais (thread-safe)."""
        with self._sync_lock:
            config = self.load(guild_id)
            config[chave] = valor
            path = self._get_config_path(guild_id)
            path.parent.mkdir(parents=True, exist_ok=True)
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(config, f, ensure_ascii=False, indent=2)

    async def set_valor_async(self, guild_id: int, chave: str, valor) -> None:
        """Atualiza uma única chave de um servidor, preservando as demais (thread-safe, assíncrono)."""
        async with self._async_lock:
            config = self.load(guild_id)
            config[chave] = valor
            path = self._get_config_path(guild_id)
            path.parent.mkdir(parents=True, exist_ok=True)
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(config, f, ensure_ascii=False, indent=2)
