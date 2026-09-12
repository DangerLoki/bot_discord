"""Testes para src.repositories.playlist_repository.PlaylistRepository."""
import json

GUILD_ID = 123456789


class TestLoad:
    def test_arquivo_inexistente_retorna_lista_vazia(self, playlist_repo):
        assert playlist_repo.load(GUILD_ID) == []

    def test_arquivo_vazio_retorna_lista_vazia(self, playlist_repo, tmp_path):
        path = tmp_path / "data" / "guilds" / str(GUILD_ID)
        path.mkdir(parents=True, exist_ok=True)
        (path / "playlist.json").write_text("", encoding="utf-8")
        assert playlist_repo.load(GUILD_ID) == []

    def test_json_invalido_retorna_lista_vazia(self, playlist_repo, tmp_path):
        path = tmp_path / "data" / "guilds" / str(GUILD_ID)
        path.mkdir(parents=True, exist_ok=True)
        (path / "playlist.json").write_text("{invalido", encoding="utf-8")
        assert playlist_repo.load(GUILD_ID) == []

    def test_carrega_playlist_existente(self, playlist_repo):
        dados = [{"video_id": "abc", "titulo": "Musica"}]
        playlist_repo.save(GUILD_ID, dados)
        assert playlist_repo.load(GUILD_ID) == dados


class TestSave:
    def test_cria_diretorio_se_nao_existir(self, playlist_repo):
        dados = [{"video_id": "abc", "titulo": "Musica"}]
        playlist_repo.save(GUILD_ID, dados)
        assert playlist_repo.load(GUILD_ID) == dados

    def test_salva_com_encoding_utf8(self, playlist_repo):
        dados = [{"video_id": "abc", "titulo": "Música com acentuação"}]
        playlist_repo.save(GUILD_ID, dados)
        path = playlist_repo._get_playlist_path(GUILD_ID)
        conteudo = json.loads(open(path, encoding="utf-8").read())
        assert conteudo[0]["titulo"] == "Música com acentuação"

    def test_sobrescreve_playlist_anterior(self, playlist_repo):
        playlist_repo.save(GUILD_ID, [{"video_id": "a"}])
        playlist_repo.save(GUILD_ID, [{"video_id": "b"}])
        assert playlist_repo.load(GUILD_ID) == [{"video_id": "b"}]
