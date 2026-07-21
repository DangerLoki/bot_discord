"""Testes para src.utils.formatters."""
import pytest

from src.utils.formatters import (
    extrair_spotify_tipo_id,
    extrair_video_id,
    formatar_duracao,
    is_spotify_url,
)


class TestFormatarDuracao:
    def test_zero_ou_none_retorna_00_00(self):
        assert formatar_duracao(0) == "00:00"
        assert formatar_duracao(None) == "00:00"

    def test_apenas_segundos(self):
        assert formatar_duracao(45) == "00:45"

    def test_minutos_e_segundos(self):
        assert formatar_duracao(125) == "02:05"

    def test_com_horas(self):
        assert formatar_duracao(3661) == "01:01:01"

    def test_aceita_string_numerica(self):
        assert formatar_duracao("90") == "01:30"


class TestExtrairVideoId:
    @pytest.mark.parametrize(
        "url",
        [
            "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            "https://youtu.be/dQw4w9WgXcQ",
            "https://www.youtube.com/embed/dQw4w9WgXcQ",
            "https://www.youtube.com/shorts/dQw4w9WgXcQ",
            "https://www.youtube.com/watch?v=dQw4w9WgXcQ&list=PL123",
        ],
    )
    def test_extrai_id_valido(self, url):
        assert extrair_video_id(url) == "dQw4w9WgXcQ"

    def test_url_invalida_retorna_none(self):
        assert extrair_video_id("https://example.com/not-a-video") is None
        assert extrair_video_id("") is None


class TestSpotifyUrl:
    def test_is_spotify_url_true(self):
        assert is_spotify_url("https://open.spotify.com/track/123") is True

    def test_is_spotify_url_false(self):
        assert is_spotify_url("https://youtube.com/watch?v=123") is False

    @pytest.mark.parametrize(
        "url,tipo_esperado,id_esperado",
        [
            ("https://open.spotify.com/track/1A2B3C4D5E6F7G8H9I0J1K", "track", "1A2B3C4D5E6F7G8H9I0J1K"),
            ("https://open.spotify.com/album/1A2B3C4D5E6F7G8H9I0J1K", "album", "1A2B3C4D5E6F7G8H9I0J1K"),
            ("https://open.spotify.com/playlist/1A2B3C4D5E6F7G8H9I0J1K", "playlist", "1A2B3C4D5E6F7G8H9I0J1K"),
            ("https://open.spotify.com/intl-pt/track/1A2B3C4D5E6F7G8H9I0J1K", "track", "1A2B3C4D5E6F7G8H9I0J1K"),
        ],
    )
    def test_extrai_tipo_e_id(self, url, tipo_esperado, id_esperado):
        assert extrair_spotify_tipo_id(url) == (tipo_esperado, id_esperado)

    def test_url_invalida_retorna_none_none(self):
        assert extrair_spotify_tipo_id("https://example.com") == (None, None)
