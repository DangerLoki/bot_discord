"""Testes para src.services.playlist_resolver.resolver_entrada_por_titulo."""
import asyncio

from src.services.playlist_resolver import resolver_entrada_por_titulo
from tests.conftest import make_reaction, make_video


class TestMatchExato:
    async def test_retorna_direto_sem_confirmacao(self, fake_ctx, fake_bot):
        playlist = [make_video("v1", titulo="Never Gonna Give You Up")]
        idx, video, msg = await resolver_entrada_por_titulo(
            fake_ctx, fake_bot, playlist, "Never Gonna Give You Up"
        )
        assert idx == 0
        assert video["video_id"] == "v1"
        assert msg is None
        fake_ctx.send.assert_not_called()


class TestSemCandidatos:
    async def test_retorna_none_quando_nao_encontra(self, fake_ctx, fake_bot):
        playlist = [make_video("v1", titulo="Outra Musica")]
        idx, video, msg = await resolver_entrada_por_titulo(
            fake_ctx, fake_bot, playlist, "inexistente"
        )
        assert (idx, video, msg) == (None, None, None)
        fake_ctx.send.assert_not_called()


class TestUnicoCandidato:
    async def test_confirmacao_aceita(self, fake_ctx, fake_bot, fake_message):
        playlist = [make_video("v1", titulo="Rick Astley - Never Gonna Give You Up")]
        fake_bot.wait_for.return_value = (make_reaction("✅", fake_message.id), "TesterUser")
        idx, video, msg = await resolver_entrada_por_titulo(
            fake_ctx, fake_bot, playlist, "never gonna"
        )
        assert idx == 0
        assert video["video_id"] == "v1"
        assert msg is fake_message
        fake_ctx.send.assert_awaited_once()
        assert fake_message.add_reaction.await_count == 2

    async def test_confirmacao_recusada(self, fake_ctx, fake_bot, fake_message):
        playlist = [make_video("v1", titulo="Rick Astley - Never Gonna Give You Up")]
        fake_bot.wait_for.return_value = (make_reaction("❌", fake_message.id), "TesterUser")
        idx, video, msg = await resolver_entrada_por_titulo(
            fake_ctx, fake_bot, playlist, "never gonna"
        )
        assert (idx, video, msg) == (None, None, None)
        fake_message.edit.assert_awaited_once()

    async def test_timeout_cancela(self, fake_ctx, fake_bot, fake_message):
        playlist = [make_video("v1", titulo="Rick Astley - Never Gonna Give You Up")]
        fake_bot.wait_for.side_effect = asyncio.TimeoutError()
        idx, video, msg = await resolver_entrada_por_titulo(
            fake_ctx, fake_bot, playlist, "never gonna"
        )
        assert (idx, video, msg) == (None, None, None)
        fake_message.edit.assert_awaited_once()


class TestMultiplosCandidatos:
    async def test_seleciona_pela_reacao_escolhida(self, fake_ctx, fake_bot, fake_message):
        playlist = [
            make_video("v1", titulo="musica um teste"),
            make_video("v2", titulo="musica dois teste"),
        ]
        fake_bot.wait_for.return_value = (make_reaction("2️⃣", fake_message.id), "TesterUser")
        idx, video, msg = await resolver_entrada_por_titulo(fake_ctx, fake_bot, playlist, "teste")
        assert idx == 1
        assert video["video_id"] == "v2"
        assert fake_message.add_reaction.await_count == 2

    async def test_timeout_cancela_multiplos(self, fake_ctx, fake_bot, fake_message):
        playlist = [
            make_video("v1", titulo="musica um teste"),
            make_video("v2", titulo="musica dois teste"),
        ]
        fake_bot.wait_for.side_effect = asyncio.TimeoutError()
        idx, video, msg = await resolver_entrada_por_titulo(fake_ctx, fake_bot, playlist, "teste")
        assert (idx, video, msg) == (None, None, None)
        fake_message.edit.assert_awaited_once()
