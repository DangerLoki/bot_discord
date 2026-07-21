"""Testes para src.services.playlist_add.PlaylistAdd.adicionar_por_url (mock yt-dlp)."""
from unittest.mock import AsyncMock

from tests.conftest import make_video

URL_VALIDA = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"


class TestAdicionarPorUrl:
    async def test_url_invalida_envia_erro(self, playlist_service, fake_ctx):
        await playlist_service.adicionar_por_url(fake_ctx, "https://example.com/nao-e-video")
        fake_ctx.send.assert_awaited_once()
        assert playlist_service.repo.load() == []

    async def test_video_ja_na_playlist_envia_aviso(self, playlist_service, fake_ctx):
        playlist_service.repo.save([make_video("dQw4w9WgXcQ")])
        await playlist_service.adicionar_por_url(fake_ctx, URL_VALIDA)
        fake_ctx.send.assert_awaited_once()
        assert len(playlist_service.repo.load()) == 1

    async def test_geo_bloqueado_nao_adiciona(self, playlist_service, fake_ctx, fake_message):
        playlist_service.yt.obter_info_video = AsyncMock(return_value={"geo_blocked": True})
        await playlist_service.adicionar_por_url(fake_ctx, URL_VALIDA)
        fake_message.edit.assert_awaited_once()
        assert playlist_service.repo.load() == []

    async def test_live_nao_suportada(self, playlist_service, fake_ctx, fake_message):
        playlist_service.yt.obter_info_video = AsyncMock(return_value={"is_live": True})
        await playlist_service.adicionar_por_url(fake_ctx, URL_VALIDA)
        fake_message.edit.assert_awaited_once()
        assert playlist_service.repo.load() == []

    async def test_adiciona_com_sucesso(self, playlist_service, fake_ctx, fake_message):
        playlist_service.yt.obter_info_video = AsyncMock(return_value={
            "titulo": "Never Gonna Give You Up",
            "duracao": 213,
            "duracao_formatada": "03:33",
            "canal": "Rick Astley",
            "views": 1_000_000,
        })
        await playlist_service.adicionar_por_url(fake_ctx, URL_VALIDA)
        playlist = playlist_service.repo.load()
        assert len(playlist) == 1
        assert playlist[0]["video_id"] == "dQw4w9WgXcQ"
        assert playlist[0]["titulo"] == "Never Gonna Give You Up"
        assert playlist[0]["posicao"] == 1
        fake_message.edit.assert_awaited_once()

    async def test_adiciona_sem_info_video_usa_desconhecido(
        self, playlist_service, fake_ctx, fake_message
    ):
        playlist_service.yt.obter_info_video = AsyncMock(return_value=None)
        await playlist_service.adicionar_por_url(fake_ctx, URL_VALIDA)
        playlist = playlist_service.repo.load()
        assert len(playlist) == 1
        assert playlist[0]["titulo"] is None
        assert playlist[0]["duracao_formatada"] == "??:??"

    async def test_atualiza_shuffle_playlist_ao_adicionar(
        self, playlist_service, fake_ctx, fake_message
    ):
        playlist_service.repo.save([make_video("existente")])
        playlist_service.state.shuffle_mode = True
        playlist_service.state.shuffle_playlist = [0]
        playlist_service.yt.obter_info_video = AsyncMock(return_value={
            "titulo": "Nova Musica",
            "duracao": 100,
            "duracao_formatada": "01:40",
            "canal": "Canal X",
            "views": 10,
        })
        await playlist_service.adicionar_por_url(fake_ctx, URL_VALIDA)
        assert 1 in playlist_service.state.shuffle_playlist
        assert len(playlist_service.state.shuffle_playlist) == 2
