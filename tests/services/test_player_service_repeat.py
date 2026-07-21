"""Testes para os modos de repetição (repeat) em PlayerService._auto_next."""
from unittest.mock import AsyncMock

from src.models.player_state import RepeatMode
from tests.conftest import make_video


class TestRepeatOne:
    async def test_repete_musica_atual_sem_marcar_tocada(self, player_service, fake_ctx):
        playlist = [make_video("v1"), make_video("v2")]
        player_service.repo.save(playlist)
        player_service.state.playlist_index = 0
        player_service.state.repeat_mode = RepeatMode.ONE
        player_service.state.is_playing_voice = True
        player_service.tocar_atual = AsyncMock()

        await player_service._auto_next(fake_ctx)

        player_service.tocar_atual.assert_awaited_once_with(fake_ctx)
        assert player_service.state.playlist_index == 0
        salvo = player_service.repo.load()
        assert salvo[0]["tocado"] is False


class TestRepeatOff:
    async def test_avanca_para_proxima_musica(self, player_service, fake_ctx):
        playlist = [make_video("v1"), make_video("v2")]
        player_service.repo.save(playlist)
        player_service.state.playlist_index = 0
        player_service.state.repeat_mode = RepeatMode.OFF
        player_service.state.is_playing_voice = True
        player_service.tocar_atual = AsyncMock()

        await player_service._auto_next(fake_ctx)

        assert player_service.repo.load()[0]["tocado"] is True
        assert player_service.state.playlist_index == 1
        player_service.tocar_atual.assert_awaited_once_with(fake_ctx)

    async def test_termina_playlist_ao_chegar_no_fim(self, player_service, fake_ctx):
        playlist = [make_video("v1")]
        player_service.repo.save(playlist)
        player_service.state.playlist_index = 0
        player_service.state.repeat_mode = RepeatMode.OFF
        player_service.state.is_playing_voice = True
        player_service.tocar_atual = AsyncMock()

        await player_service._auto_next(fake_ctx)

        assert player_service.state.is_playing_voice is False
        assert player_service.state.playlist_index == 0
        fake_ctx.send.assert_awaited_once()
        player_service.tocar_atual.assert_not_awaited()

    async def test_pula_musicas_ja_tocadas_ao_avancar(self, player_service, fake_ctx):
        playlist = [make_video("v1"), make_video("v2", tocado=True), make_video("v3")]
        player_service.repo.save(playlist)
        player_service.state.playlist_index = 0
        player_service.state.repeat_mode = RepeatMode.OFF
        player_service.state.is_playing_voice = True
        player_service.tocar_atual = AsyncMock()

        await player_service._auto_next(fake_ctx)

        assert player_service.state.playlist_index == 2
        player_service.tocar_atual.assert_awaited_once_with(fake_ctx)


class TestRepeatAll:
    async def test_reseta_playlist_ao_chegar_no_fim(self, player_service, fake_ctx):
        playlist = [make_video("v1")]
        player_service.repo.save(playlist)
        player_service.state.playlist_index = 0
        player_service.state.repeat_mode = RepeatMode.ALL
        player_service.state.is_playing_voice = True
        player_service.tocar_atual = AsyncMock()

        await player_service._auto_next(fake_ctx)

        salvo = player_service.repo.load()
        assert all(v["tocado"] is False for v in salvo)
        assert player_service.state.playlist_index == 0
        player_service.tocar_atual.assert_awaited_once_with(fake_ctx)


class TestShuffleAutoNext:
    async def test_usa_proximo_aleatorio_do_playlist_svc(self, player_service, fake_ctx):
        playlist = [make_video("v1"), make_video("v2")]
        player_service.repo.save(playlist)
        player_service.state.playlist_index = 0
        player_service.state.shuffle_mode = True
        player_service.state.shuffle_playlist = [1, 0]
        player_service.state.shuffle_index = 0
        player_service.state.is_playing_voice = True
        player_service.tocar_atual = AsyncMock()

        await player_service._auto_next(fake_ctx)

        assert player_service.state.playlist_index == 1
        player_service.tocar_atual.assert_awaited_once_with(fake_ctx)


class TestAutoNextNaoTocando:
    async def test_nao_faz_nada_se_ja_parou(self, player_service, fake_ctx):
        player_service.state.is_playing_voice = False
        player_service.tocar_atual = AsyncMock()

        await player_service._auto_next(fake_ctx)

        player_service.tocar_atual.assert_not_awaited()
        fake_ctx.send.assert_not_called()
