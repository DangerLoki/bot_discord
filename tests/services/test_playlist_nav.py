"""Testes para src.services.playlist_nav.PlaylistNav (via PlaylistService)."""
from tests.conftest import make_video


class TestPularVideo:
    async def test_playlist_vazia_envia_erro(self, playlist_service, fake_ctx):
        await playlist_service.pular_video(fake_ctx)
        fake_ctx.send.assert_awaited_once()

    async def test_avanca_para_proximo_indice(self, playlist_service, fake_ctx):
        playlist = [make_video("v1"), make_video("v2"), make_video("v3")]
        playlist_service.repo.save(playlist)
        playlist_service.state.playlist_index = 0
        await playlist_service.pular_video(fake_ctx)
        assert playlist_service.state.playlist_index == 1
        fake_ctx.send.assert_awaited_once()

    async def test_pula_musicas_ja_tocadas(self, playlist_service, fake_ctx):
        playlist = [
            make_video("v1"),
            make_video("v2", tocado=True),
            make_video("v3"),
        ]
        playlist_service.repo.save(playlist)
        playlist_service.state.playlist_index = 0
        await playlist_service.pular_video(fake_ctx)
        assert playlist_service.state.playlist_index == 2

    async def test_wrap_around_volta_ao_inicio(self, playlist_service, fake_ctx):
        playlist = [make_video("v1"), make_video("v2")]
        playlist_service.repo.save(playlist)
        playlist_service.state.playlist_index = 1
        await playlist_service.pular_video(fake_ctx)
        assert playlist_service.state.playlist_index == 0

    async def test_usa_proximo_aleatorio_em_modo_shuffle(self, playlist_service, fake_ctx):
        playlist = [make_video("v1"), make_video("v2")]
        playlist_service.repo.save(playlist)
        playlist_service.state.shuffle_mode = True
        await playlist_service.pular_video(fake_ctx)
        assert playlist_service.state.playlist_index in {0, 1}


class TestVoltarVideo:
    async def test_playlist_vazia_envia_erro(self, playlist_service, fake_ctx):
        await playlist_service.voltar_video(fake_ctx)
        fake_ctx.send.assert_awaited_once()

    async def test_volta_para_indice_anterior(self, playlist_service, fake_ctx):
        playlist = [make_video("v1"), make_video("v2", tocado=True)]
        playlist_service.repo.save(playlist)
        playlist_service.state.playlist_index = 1
        await playlist_service.voltar_video(fake_ctx)
        assert playlist_service.state.playlist_index == 0
        fake_ctx.send.assert_awaited_once()

    async def test_reseta_flag_tocado_do_video_anterior(self, playlist_service, fake_ctx):
        playlist = [make_video("v1", tocado=True), make_video("v2")]
        playlist_service.repo.save(playlist)
        playlist_service.state.playlist_index = 1
        await playlist_service.voltar_video(fake_ctx)
        salvo = playlist_service.repo.load()
        assert salvo[0]["tocado"] is False

    async def test_wrap_around_no_inicio_volta_para_ultimo(self, playlist_service, fake_ctx):
        playlist = [make_video("v1"), make_video("v2")]
        playlist_service.repo.save(playlist)
        playlist_service.state.playlist_index = 0
        await playlist_service.voltar_video(fake_ctx)
        assert playlist_service.state.playlist_index == 1
