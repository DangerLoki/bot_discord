"""Testes para src.services.playlist_manage.PlaylistManage.remover_video."""
from tests.conftest import make_video
import pytest


class TestRemoverVideo:
    @pytest.mark.asyncio

    async def test_sem_argumento_envia_ajuda(self, playlist_service, fake_ctx):
        await playlist_service.remover_video(fake_ctx, None)
        fake_ctx.send.assert_awaited_once()
        assert playlist_service.repo.load(123456789) == []

    @pytest.mark.asyncio


    async def test_playlist_vazia_envia_aviso(self, playlist_service, fake_ctx):
        await playlist_service.remover_video(fake_ctx, "1")
        fake_ctx.send.assert_awaited_once_with("⚠️ A playlist está vazia.")

    @pytest.mark.asyncio


    async def test_remove_por_posicao(self, playlist_service, fake_ctx):
        playlist = [make_video("v1"), make_video("v2"), make_video("v3")]
        playlist_service.repo.save(123456789, playlist)
        await playlist_service.remover_video(fake_ctx, "2")
        restante = playlist_service.repo.load(123456789)
        assert [v["video_id"] for v in restante] == ["v1", "v3"]
        # posições renumeradas
        assert [v["posicao"] for v in restante] == [1, 2]

    @pytest.mark.asyncio


    async def test_posicao_invalida_envia_erro(self, playlist_service, fake_ctx):
        playlist = [make_video("v1")]
        playlist_service.repo.save(123456789, playlist)
        await playlist_service.remover_video(fake_ctx, "99")
        fake_ctx.send.assert_awaited_once()
        assert len(playlist_service.repo.load(123456789)) == 1

    @pytest.mark.asyncio


    async def test_remove_por_video_id(self, playlist_service, fake_ctx):
        playlist = [make_video("v1"), make_video("v2")]
        playlist_service.repo.save(123456789, playlist)
        await playlist_service.remover_video(fake_ctx, "v1")
        restante = playlist_service.repo.load(123456789)
        assert [v["video_id"] for v in restante] == ["v2"]

    @pytest.mark.asyncio


    async def test_video_id_inexistente_envia_erro(self, playlist_service, fake_ctx):
        playlist = [make_video("v1")]
        playlist_service.repo.save(123456789, playlist)
        await playlist_service.remover_video(fake_ctx, "naoexiste")
        fake_ctx.send.assert_awaited_once()
        assert len(playlist_service.repo.load(123456789)) == 1

    @pytest.mark.asyncio


    async def test_ajusta_playlist_index_quando_remove_anterior(self, playlist_service, fake_ctx):
        playlist = [make_video("v1"), make_video("v2"), make_video("v3")]
        playlist_service.repo.save(123456789, playlist)
        playlist_service.state.playlist_index = 2  # tocando v3
        await playlist_service.remover_video(fake_ctx, "1")  # remove v1 (antes do índice atual)
        assert playlist_service.state.playlist_index == 1

    @pytest.mark.asyncio


    async def test_remover_ultimo_video_zera_index(self, playlist_service, fake_ctx):
        playlist = [make_video("v1")]
        playlist_service.repo.save(123456789, playlist)
        playlist_service.state.playlist_index = 0
        await playlist_service.remover_video(fake_ctx, "1")
        assert playlist_service.repo.load(123456789) == []
        assert playlist_service.state.playlist_index == 0
