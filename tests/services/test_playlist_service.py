"""Testes para src.services.playlist_service.PlaylistService (navegação/shuffle)."""

from tests.conftest import make_video


class TestEncontrarProximaNaoTocada:
    def test_playlist_vazia_define_index_zero(self, playlist_service):
        playlist_service.encontrar_proxima_nao_tocada()
        assert playlist_service.state.playlist_index == 0

    def test_encontra_primeira_nao_tocada(self, playlist_service):
        playlist = [
            make_video("v1", tocado=True),
            make_video("v2", tocado=True),
            make_video("v3", tocado=False),
        ]
        playlist_service.repo.save(playlist)
        playlist_service.encontrar_proxima_nao_tocada()
        assert playlist_service.state.playlist_index == 2

    def test_todas_tocadas_define_index_zero(self, playlist_service):
        playlist = [make_video("v1", tocado=True), make_video("v2", tocado=True)]
        playlist_service.repo.save(playlist)
        playlist_service.encontrar_proxima_nao_tocada()
        assert playlist_service.state.playlist_index == 0


class TestProximoAleatorio:
    def test_gera_lista_shuffle_com_nao_tocados(self, playlist_service):
        playlist = [make_video("v1"), make_video("v2"), make_video("v3")]
        index = playlist_service.proximo_aleatorio(playlist)
        assert index in {0, 1, 2}
        assert playlist_service.state.shuffle_index == 1

    def test_reseta_quando_todos_tocados(self, playlist_service):
        playlist = [make_video("v1", tocado=True), make_video("v2", tocado=True)]
        playlist_service.proximo_aleatorio(playlist)
        # todos ficam resetados (tocado=False) e uma nova ordem embaralhada é criada
        salvo = playlist_service.repo.load()
        assert all(v["tocado"] is False for v in salvo)
        assert len(playlist_service.state.shuffle_playlist) == 2

    def test_consome_shuffle_playlist_sequencialmente(self, playlist_service):
        playlist = [make_video("v1"), make_video("v2")]
        st = playlist_service.state
        st.shuffle_playlist = [1, 0]
        st.shuffle_index = 0
        assert playlist_service.proximo_aleatorio(playlist) == 1
        assert playlist_service.proximo_aleatorio(playlist) == 0


class TestToggleShuffle:
    async def test_ativa_shuffle_com_playlist_nao_vazia(self, playlist_service, fake_ctx):
        playlist = [make_video("v1"), make_video("v2")]
        playlist_service.repo.save(playlist)
        await playlist_service.toggle_shuffle(fake_ctx)
        assert playlist_service.state.shuffle_mode is True
        assert playlist_service.state.shuffle_id is not None
        fake_ctx.send.assert_awaited_once()

    async def test_desativa_shuffle(self, playlist_service, fake_ctx):
        playlist_service.state.shuffle_mode = True
        await playlist_service.toggle_shuffle(fake_ctx)
        assert playlist_service.state.shuffle_mode is False
        fake_ctx.send.assert_awaited_once()
