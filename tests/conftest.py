"""Fixtures compartilhadas entre os testes."""
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.models.player_state import PlayerState
from src.repositories.playlist_repository import PlaylistRepository
from src.services.player_service import PlayerService
from src.services.playlist_service import PlaylistService


def make_video(
    video_id: str = "vid001",
    titulo: str = "Musica Teste",
    tocado: bool = False,
    **extra,
) -> dict:
    """Cria um dicionário de vídeo com os campos padrão usados na playlist."""
    video = {
        "video_id": video_id,
        "titulo": titulo,
        "duracao": 120,
        "duracao_formatada": "02:00",
        "canal": "Canal Teste",
        "embed_url": f"https://www.youtube.com/watch?v={video_id}",
        "thumbnail_url": f"https://img.youtube.com/vi/{video_id}/hqdefault.jpg",
        "adicionado_por": "tester",
        "url": f"https://www.youtube.com/watch?v={video_id}",
        "tocado": tocado,
    }
    video.update(extra)
    return video


@pytest.fixture
def playlist_repo(tmp_path):
    """Repositório de playlist apontando para um arquivo JSON temporário."""
    json_path = tmp_path / "data" / "playlist.json"
    return PlaylistRepository(str(json_path))


@pytest.fixture
def player_state():
    return PlayerState()


@pytest.fixture
def fake_message():
    """Mensagem Discord falsa com edit/add_reaction/clear_reactions assíncronos."""
    msg = MagicMock()
    msg.id = 999
    msg.edit = AsyncMock()
    msg.add_reaction = AsyncMock()
    msg.clear_reactions = AsyncMock()
    msg.delete = AsyncMock()
    return msg


@pytest.fixture
def fake_ctx(fake_message):
    """Contexto de comando Discord falso."""
    ctx = MagicMock()
    ctx.author = "TesterUser"
    ctx.send = AsyncMock(return_value=fake_message)
    return ctx


def make_reaction(emoji: str, message_id: int = 999):
    """Cria um mock de discord.Reaction com o emoji e o id de mensagem dados."""
    reaction = MagicMock()
    reaction.emoji = emoji
    reaction.message.id = message_id
    return reaction


@pytest.fixture
def fake_bot(fake_ctx):
    """Bot falso com wait_for assíncrono (configurável por teste)."""
    bot = MagicMock()
    bot.wait_for = AsyncMock()
    return bot


@pytest.fixture
def playlist_service(playlist_repo, player_state):
    """PlaylistService com repo real (tmp) e yt/spotify mockados (não usados na navegação)."""
    return PlaylistService(
        repo=playlist_repo,
        yt=MagicMock(),
        spotify=MagicMock(),
        state=player_state,
    )


@pytest.fixture
def player_service(playlist_repo, player_state, playlist_service):
    """PlayerService com repo real (tmp), yt mockado e playlist_service real."""
    return PlayerService(
        state=player_state,
        repo=playlist_repo,
        yt=MagicMock(),
        playlist_svc=playlist_service,
    )

