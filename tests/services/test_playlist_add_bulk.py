"""Testes para src.services.playlist_add_bulk.PlaylistAddBulk (mock Spotify + yt-dlp)."""
from unittest.mock import AsyncMock
import pytest

URL_TRACK = "https://open.spotify.com/track/1A2B3C4D5E6F7G8H9I0J1K"


class TestAdicionarSpotifyNaoConfigurado:
    @pytest.mark.asyncio

    async def test_sem_credenciais_envia_erro(self, playlist_service, fake_ctx):
        playlist_service.spotify.client_id = None
        playlist_service.spotify.client_secret = None
        await playlist_service.adicionar_spotify(fake_ctx, URL_TRACK, bot=None)
        fake_ctx.send.assert_awaited_once()


class TestAdicionarSpotifyUrlInvalida:
    @pytest.mark.asyncio

    async def test_url_nao_reconhecida_envia_erro(self, playlist_service, fake_ctx):
        playlist_service.spotify.client_id = "id"
        playlist_service.spotify.client_secret = "secret"
        playlist_service.spotify.extrair_tipo_id = lambda url: (None, None)
        await playlist_service.adicionar_spotify(fake_ctx, "https://open.spotify.com/artist/x", bot=None)
        fake_ctx.send.assert_awaited_once()


class TestAdicionarSpotifyTrack:
    @pytest.mark.asyncio

    async def test_track_nao_encontrada_no_spotify(self, playlist_service, fake_ctx, fake_message):
        playlist_service.spotify.client_id = "id"
        playlist_service.spotify.client_secret = "secret"
        playlist_service.spotify.extrair_tipo_id = lambda url: ("track", "trackid123")
        playlist_service.spotify.obter_track = AsyncMock(return_value=None)
        await playlist_service.adicionar_spotify(fake_ctx, URL_TRACK, bot=None)
        fake_message.edit.assert_awaited_once()
        assert playlist_service.repo.load(123456789) == []

    @pytest.mark.asyncio


    async def test_track_nao_encontrada_no_youtube(self, playlist_service, fake_ctx, fake_message):
        playlist_service.spotify.client_id = "id"
        playlist_service.spotify.client_secret = "secret"
        playlist_service.spotify.extrair_tipo_id = lambda url: ("track", "trackid123")
        playlist_service.spotify.obter_track = AsyncMock(
            return_value={"titulo": "Musica", "artista": "Artista", "album": "Album", "duracao": 200}
        )
        playlist_service.yt.buscar_videos = AsyncMock(return_value=[])
        await playlist_service.adicionar_spotify(fake_ctx, URL_TRACK, bot=None)
        assert fake_message.edit.await_count == 2  # carregando -> buscando -> erro
        assert playlist_service.repo.load(123456789) == []

    @pytest.mark.asyncio


    async def test_track_encontrada_adiciona_via_youtube(self, playlist_service, fake_ctx, fake_message):
        playlist_service.spotify.client_id = "id"
        playlist_service.spotify.client_secret = "secret"
        playlist_service.spotify.extrair_tipo_id = lambda url: ("track", "trackid123")
        playlist_service.spotify.obter_track = AsyncMock(
            return_value={"titulo": "Musica", "artista": "Artista", "album": "Album", "duracao": 200}
        )
        playlist_service.yt.buscar_videos = AsyncMock(
            return_value=[{"video_id": "abc12345678"}]
        )
        playlist_service.yt.obter_info_video = AsyncMock(return_value={
            "titulo": "Artista - Musica",
            "duracao": 200,
            "duracao_formatada": "03:20",
            "canal": "Artista",
            "views": 500,
        })
        await playlist_service.adicionar_spotify(fake_ctx, URL_TRACK, bot=None)
        fake_message.delete.assert_awaited_once()
        playlist = playlist_service.repo.load(123456789)
        assert len(playlist) == 1
        assert playlist[0]["video_id"] == "abc12345678"
