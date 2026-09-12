"""Testes para isolamento de dados entre múltiplos servidores (multi-guild)."""
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.models.player_state import PlayerState
from src.repositories.config_repository import ConfigRepository
from src.repositories.playlist_repository import PlaylistRepository
from tests.conftest import make_video


class TestPlaylistIsolationMultiGuild:
    """Testes que garantem que playlists de diferentes servidores não se misturam."""

    def test_cada_servidor_tem_playlist_independente(self, tmp_path):
        """Playlist do servidor 1 não interfere com servidor 2."""
        repo = PlaylistRepository(str(tmp_path))
        guild1 = 111111111
        guild2 = 222222222

        # Adiciona video no servidor 1
        pl1 = [make_video("v1", titulo="Musica Guild1")]
        repo.save(guild1, pl1)

        # Adiciona video diferente no servidor 2
        pl2 = [make_video("v2", titulo="Musica Guild2")]
        repo.save(guild2, pl2)

        # Verifica isolamento
        assert repo.load(guild1) == pl1
        assert repo.load(guild2) == pl2
        assert repo.load(guild1)[0]["titulo"] == "Musica Guild1"
        assert repo.load(guild2)[0]["titulo"] == "Musica Guild2"

    def test_remocao_em_um_servidor_nao_afeta_outro(self, tmp_path):
        """Remover música no servidor 1 não afeta servidor 2."""
        repo = PlaylistRepository(str(tmp_path))
        guild1 = 111111111
        guild2 = 222222222

        # Setup: ambos servidores com 2 vídeos
        pl1 = [make_video("v1"), make_video("v2")]
        pl2 = [make_video("v3"), make_video("v4")]
        repo.save(guild1, pl1)
        repo.save(guild2, pl2)

        # Remove primeiro vídeo do servidor 1
        repo.save(guild1, pl1[1:])

        # Verifica: servidor 1 tem 1, servidor 2 continua com 2
        assert len(repo.load(guild1)) == 1
        assert len(repo.load(guild2)) == 2
        assert repo.load(guild1)[0]["video_id"] == "v2"
        assert repo.load(guild2)[0]["video_id"] == "v3"


class TestConfigIsolationMultiGuild:
    """Testes que garantem que configs de diferentes servidores não se misturam."""

    def test_cada_servidor_tem_config_independente(self, tmp_path):
        """Config do servidor 1 não interfere com servidor 2."""
        repo = ConfigRepository(str(tmp_path))
        guild1 = 111111111
        guild2 = 222222222

        # Setup configs diferentes
        cfg1 = {"player_channel_id": 1001, "prefix": "&"}
        cfg2 = {"player_channel_id": 2002, "prefix": "!"}
        repo.save(guild1, cfg1)
        repo.save(guild2, cfg2)

        # Verifica isolamento
        assert repo.load(guild1)["player_channel_id"] == 1001
        assert repo.load(guild2)["player_channel_id"] == 2002

    def test_set_valor_em_um_servidor_nao_afeta_outro(self, tmp_path):
        """Mudar config no servidor 1 não afeta servidor 2."""
        repo = ConfigRepository(str(tmp_path))
        guild1 = 111111111
        guild2 = 222222222

        # Setup
        repo.save(guild1, {"player_channel_id": 0})
        repo.save(guild2, {"player_channel_id": 0})

        # Muda config no servidor 1
        repo.set_valor(guild1, "player_channel_id", 9999)

        # Verifica
        assert repo.load(guild1)["player_channel_id"] == 9999
        assert repo.load(guild2)["player_channel_id"] == 0


class TestPlayerStateIsolationMultiGuild:
    """Testes que garantem que states de diferentes servidores não se misturam."""

    def test_cada_servidor_tem_state_independente(self):
        """PlayerState do servidor 1 não interfere com servidor 2."""
        guild1 = 111111111
        guild2 = 222222222

        state1 = PlayerState(guild_id=guild1)
        state2 = PlayerState(guild_id=guild2)

        # Modifica apenas state1
        state1.playlist_index = 5
        state1.voice_volume = 0.75

        # Verifica isolamento
        assert state1.playlist_index == 5
        assert state2.playlist_index == 0
        assert state1.voice_volume == 0.75
        assert state2.voice_volume == 0.25

    def test_estado_persistencia_isolada(self):
        """Serialização de state preserva isolamento."""
        guild1 = 111111111
        guild2 = 222222222

        state1 = PlayerState(guild_id=guild1)
        state2 = PlayerState(guild_id=guild2)

        state1.playlist_index = 3
        state1.voice_volume = 0.80

        state2.playlist_index = 7
        state2.voice_volume = 0.50

        # Serializa ambos
        dict1 = state1.to_dict()
        dict2 = state2.to_dict()

        # Verifica que estados foram salvos corretamente
        assert dict1["playlist_index"] == 3
        assert dict1["voice_volume"] == 0.80
        assert dict2["playlist_index"] == 7
        assert dict2["voice_volume"] == 0.50

        # Desserializa em novos states
        state1_novo = PlayerState(guild_id=guild1)
        state2_novo = PlayerState(guild_id=guild2)
        state1_novo.from_dict(dict1)
        state2_novo.from_dict(dict2)

        # Verifica restauração
        assert state1_novo.playlist_index == 3
        assert state1_novo.voice_volume == 0.80
        assert state2_novo.playlist_index == 7
        assert state2_novo.voice_volume == 0.50


class TestMultiGuildServiceInteraction:
    """Testes integrando repositories e states para múltiplos servidores."""

    @pytest.mark.asyncio
    async def test_3_servidores_simultaneos_com_playlists_diferentes(self, tmp_path):
        """Simula 3 servidores operando simultaneamente com dados independentes."""
        playlist_repo = PlaylistRepository(str(tmp_path))
        config_repo = ConfigRepository(str(tmp_path))

        # Servidores
        servers = [111111111, 222222222, 333333333]
        states = {sid: PlayerState(guild_id=sid) for sid in servers}

        # Setup: cada servidor tem uma playlist diferente
        playlists = {
            servers[0]: [make_video("v1", titulo="Server1-Musica1"), make_video("v2", titulo="Server1-Musica2")],
            servers[1]: [make_video("v3", titulo="Server2-Musica1")],
            servers[2]: [make_video("v4", titulo="Server3-Musica1"), make_video("v5", titulo="Server3-Musica2"), make_video("v6", titulo="Server3-Musica3")],
        }

        configs = {
            servers[0]: {"player_channel_id": 1001, "player_state": {"playlist_index": 0}},
            servers[1]: {"player_channel_id": 2002, "player_state": {"playlist_index": 1}},
            servers[2]: {"player_channel_id": 3003, "player_state": {"playlist_index": 2}},
        }

        # Salva playlists e configs
        for sid, pl in playlists.items():
            playlist_repo.save(sid, pl)
            config_repo.save(sid, configs[sid])

        # Carrega de volta e verifica isolamento
        for sid in servers:
            loaded_pl = playlist_repo.load(sid)
            loaded_cfg = config_repo.load(sid)

            assert len(loaded_pl) == len(playlists[sid])
            assert loaded_cfg["player_channel_id"] == configs[sid]["player_channel_id"]

            # Verifica que não há dados de outros servidores
            for video in loaded_pl:
                for other_sid in servers:
                    if other_sid != sid:
                        # Não deve haver vídeo de outro servidor
                        for other_video in playlists[other_sid]:
                            assert video["video_id"] != other_video["video_id"]

    @pytest.mark.asyncio
    async def test_adicionar_em_paralelo_em_3_servidores(self, tmp_path):
        """Simula adição paralela de vídeos em 3 servidores diferentes."""
        playlist_repo = PlaylistRepository(str(tmp_path))

        servers = [111111111, 222222222, 333333333]

        # Adiciona vídeo inicial em cada servidor
        for i, sid in enumerate(servers):
            pl = [make_video(f"initial_{i}", titulo=f"Initial-{i}")]
            playlist_repo.save(sid, pl)

        # "Paralelo": adiciona novo vídeo em cada servidor
        for i, sid in enumerate(servers):
            pl = playlist_repo.load(sid)
            pl.append(make_video(f"added_{i}", titulo=f"Added-{i}"))
            playlist_repo.save(sid, pl)

        # Verifica que cada servidor tem exatamente 2 vídeos e nenhum duplicado entre servidores
        for i, sid in enumerate(servers):
            pl = playlist_repo.load(sid)
            assert len(pl) == 2
            assert pl[0]["video_id"] == f"initial_{i}"
            assert pl[1]["video_id"] == f"added_{i}"

            # Verifica que outros vídeos não existem aqui
            for other_i in range(len(servers)):
                if other_i != i:
                    video_ids = [v["video_id"] for v in pl]
                    assert f"initial_{other_i}" not in video_ids
                    assert f"added_{other_i}" not in video_ids

    def test_limpeza_orfao_isolada_por_servidor(self, tmp_path):
        """Cache cleanup de um servidor não afeta outro."""
        from src.utils.cache_manager import CacheManager

        cache_dir = tmp_path / "cache"
        cache_dir.mkdir(parents=True, exist_ok=True)
        cache_mgr = CacheManager(cache_dir)

        guild1 = 111111111
        guild2 = 222222222

        # Simula cache de ambos servidores
        (cache_dir / str(guild1)).mkdir(exist_ok=True)
        (cache_dir / str(guild2)).mkdir(exist_ok=True)

        # Cria arquivos de cache
        (cache_dir / str(guild1) / "v1.opus").write_text("cache_data_1")
        (cache_dir / str(guild1) / "v2.opus").write_text("cache_data_2")
        (cache_dir / str(guild2) / "v3.opus").write_text("cache_data_3")
        (cache_dir / str(guild2) / "v4.opus").write_text("cache_data_4")

        # Limpa cache orfão do servidor 1 (mantém apenas v1)
        cache_mgr.cleanup_orphaned_files(guild1, {"v1"})

        # Verifica: v2 deletado, v1 mantido em guild1
        assert (cache_dir / str(guild1) / "v1.opus").exists()
        assert not (cache_dir / str(guild1) / "v2.opus").exists()

        # Verifica: guild2 não foi afetado
        assert (cache_dir / str(guild2) / "v3.opus").exists()
        assert (cache_dir / str(guild2) / "v4.opus").exists()
