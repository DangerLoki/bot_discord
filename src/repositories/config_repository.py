"""Acesso à camada de persistência de configurações gerais do bot (JSON em disco)."""
import json
import os

from src.logger import get_logger

logger = get_logger(__name__)


class ConfigRepository:
    """Carrega e salva configurações simples (chave/valor) do bot em arquivo JSON."""

    def __init__(self, json_path: str) -> None:
        self.json_path = json_path

    def load(self) -> dict:
        """Retorna as configurações como dict. Retorna {} se vazio/inexistente."""
        if not os.path.exists(self.json_path):
            return {}
        try:
            with open(self.json_path, encoding='utf-8') as f:
                conteudo = f.read().strip()
                return json.loads(conteudo) if conteudo else {}
        except (json.JSONDecodeError, OSError) as e:
            logger.warning(f'[REPO] Erro ao carregar config: {e}')
            return {}

    def save(self, config: dict) -> None:
        """Persiste as configurações no disco."""
        os.makedirs(os.path.dirname(self.json_path), exist_ok=True)
        with open(self.json_path, 'w', encoding='utf-8') as f:
            json.dump(config, f, ensure_ascii=False, indent=2)

    def set_valor(self, chave: str, valor) -> None:
        """Atualiza uma única chave, preservando as demais configurações salvas."""
        config = self.load()
        config[chave] = valor
        self.save(config)
