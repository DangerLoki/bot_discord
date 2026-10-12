"""Testes do snapshot servido para a Discord Activity."""

from unittest.mock import MagicMock, patch

from src.services.activity_server import ActivityServer
from tests.conftest import make_video


def _server(player_service, playlist_service):
    guild_id = player_service.state.guild_id
    return ActivityServer(
        {guild_id: player_service.state},
        {guild_id: (playlist_service, player_service)},
        '.',
        client_id_provider=lambda: '123456',
    )


def test_snapshot_activity_reflete_faixa_tempo_e_proximas(
    player_service, playlist_service
):
    playlist = [
        make_video('video000001', titulo='Atual'),
        make_video('video000002', titulo='Próxima'),
        make_video('video000003', titulo='Depois'),
    ]
    player_service.repo.save(player_service.state.guild_id, playlist)
    player_service._current_video = playlist[0]
    state = player_service.state
    state.playlist_index = 0
    state.is_playing_voice = True
    state.voice_client = MagicMock()
    state.voice_client.is_playing.return_value = True
    state.voice_client.is_paused.return_value = False

    with patch.object(state, 'tempo_decorrido', return_value=37):
        snapshot = _server(player_service, playlist_service).snapshot(state.guild_id)

    assert snapshot['playback'] == {
        'status': 'playing',
        'position_seconds': 37,
        'duration_seconds': 120,
        'muted_clip_recommended': True,
    }
    assert snapshot['video']['video_id'] == 'video000001'
    assert [item['video_id'] for item in snapshot['queue']] == [
        'video000002',
        'video000003',
    ]


def test_snapshot_activity_respeita_pausa_e_shuffle(
    player_service, playlist_service
):
    playlist = [
        make_video('video000001'),
        make_video('video000002'),
        make_video('video000003'),
    ]
    player_service.repo.save(player_service.state.guild_id, playlist)
    player_service._current_video = playlist[2]
    state = player_service.state
    state.playlist_index = 2
    state.is_playing_voice = True
    state.voice_client = MagicMock()
    state.voice_client.is_playing.return_value = False
    state.voice_client.is_paused.return_value = True
    state.shuffle_mode = True
    state.shuffle_playlist = [2, 0, 1]
    state.shuffle_index = 1

    snapshot = _server(player_service, playlist_service).snapshot(state.guild_id)

    assert snapshot['playback']['status'] == 'paused'
    assert snapshot['modes']['shuffle'] is True
    assert [item['video_id'] for item in snapshot['queue']] == [
        'video000001',
        'video000002',
    ]


def test_snapshot_activity_rejeita_guild_desconhecida(
    player_service, playlist_service
):
    assert _server(player_service, playlist_service).snapshot(999999) is None
