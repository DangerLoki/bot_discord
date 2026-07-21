"""Testes para src.utils.errors."""
from src.utils.errors import _is_bot_blocked, _is_geo_blocked, _strip_ansi


class TestStripAnsi:
    def test_remove_codigos_ansi(self):
        assert _strip_ansi("\x1b[31mErro\x1b[0m") == "Erro"

    def test_sem_codigos_retorna_igual(self):
        assert _strip_ansi("mensagem normal") == "mensagem normal"


class TestIsGeoBlocked:
    def test_detecta_bloqueio_regional(self):
        msg = "ERROR: This video is not available in your country"
        assert _is_geo_blocked(msg) is True

    def test_case_insensitive(self):
        msg = "GEO RESTRICTED content"
        assert _is_geo_blocked(msg) is True

    def test_mensagem_normal_nao_detectada(self):
        assert _is_geo_blocked("download concluído com sucesso") is False


class TestIsBotBlocked:
    def test_detecta_bloqueio_de_bot(self):
        msg = "Sign in to confirm you're not a bot"
        assert _is_bot_blocked(msg) is True

    def test_detecta_variacao_cookies(self):
        msg = "Use --cookies-from-browser or --cookies for the authentication"
        assert _is_bot_blocked(msg) is True

    def test_mensagem_normal_nao_detectada(self):
        assert _is_bot_blocked("download concluído com sucesso") is False
