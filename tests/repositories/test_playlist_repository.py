"""Testes para src.repositories.playlist_repository.PlaylistRepository."""
import json


class TestLoad:
    def test_arquivo_inexistente_retorna_lista_vazia(self, playlist_repo):
        assert playlist_repo.load() == []

    def test_arquivo_vazio_retorna_lista_vazia(self, playlist_repo, tmp_path):
        path = tmp_path / "data"
        path.mkdir(parents=True, exist_ok=True)
        (path / "playlist.json").write_text("", encoding="utf-8")
        assert playlist_repo.load() == []

    def test_json_invalido_retorna_lista_vazia(self, playlist_repo, tmp_path):
        path = tmp_path / "data"
        path.mkdir(parents=True, exist_ok=True)
        (path / "playlist.json").write_text("{invalido", encoding="utf-8")
        assert playlist_repo.load() == []

    def test_carrega_playlist_existente(self, playlist_repo):
        dados = [{"video_id": "abc", "titulo": "Musica"}]
        playlist_repo.save(dados)
        assert playlist_repo.load() == dados


class TestSave:
    def test_cria_diretorio_se_nao_existir(self, playlist_repo):
        dados = [{"video_id": "abc", "titulo": "Musica"}]
        playlist_repo.save(dados)
        assert playlist_repo.load() == dados

    def test_salva_com_encoding_utf8(self, playlist_repo):
        dados = [{"video_id": "abc", "titulo": "Música com acentuação"}]
        playlist_repo.save(dados)
        conteudo = json.loads(open(playlist_repo.json_path, encoding="utf-8").read())
        assert conteudo[0]["titulo"] == "Música com acentuação"

    def test_sobrescreve_playlist_anterior(self, playlist_repo):
        playlist_repo.save([{"video_id": "a"}])
        playlist_repo.save([{"video_id": "b"}])
        assert playlist_repo.load() == [{"video_id": "b"}]
