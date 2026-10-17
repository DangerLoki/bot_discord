"""Testes do snapshot servido para a Discord Activity."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.services.activity_server import (
    ActivityServer,
    create_activity_control_token,
    validate_activity_control_token,
)
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


def test_token_de_controle_e_valido_apenas_para_a_guild_correta():
    token = create_activity_control_token(123456789, 998877665)

    assert validate_activity_control_token(123456789, token) == 998877665
    assert validate_activity_control_token(987654321, token) is None


def test_token_de_controle_adulterado_e_rejeitado():
    token = create_activity_control_token(123456789, 998877665)
    adulterado = token[:-1] + ('0' if token[-1] != '0' else '1')

    assert validate_activity_control_token(123456789, adulterado) is None


@pytest.mark.asyncio
async def test_controle_web_pausa_player_conectado(player_service, playlist_service):
    state = player_service.state
    state.player_channel_id = 777
    state.voice_client = MagicMock()
    state.voice_client.is_connected.return_value = True
    state.voice_client.is_playing.return_value = True
    player_service.atualizar_status_agora = AsyncMock()

    channel = MagicMock()
    channel.send = AsyncMock()
    guild = MagicMock()
    guild.get_channel.return_value = channel
    guild.get_member.return_value = 'Usuario Web'
    bot = MagicMock()
    bot.get_guild.return_value = guild
    server = ActivityServer(
        {state.guild_id: state},
        {state.guild_id: (playlist_service, player_service)},
        '.',
        client_id_provider=lambda: '123456',
        bot_provider=lambda: bot,
    )

    message = await server._execute_control(
        state.guild_id, 998877665, 'play_pause', {}
    )

    state.voice_client.pause.assert_called_once_with()
    player_service.atualizar_status_agora.assert_awaited_once()
    assert message == 'Reprodução pausada.'


@pytest.mark.asyncio
async def test_controle_web_conecta_na_call_do_usuario(
    player_service, playlist_service
):
    state = player_service.state
    state.player_channel_id = 777
    state.voice_client = None
    player_service.tocar_atual = AsyncMock()

    connected_voice = MagicMock()
    voice_channel = MagicMock()
    voice_channel.connect = AsyncMock(return_value=connected_voice)
    member = MagicMock()
    member.voice.channel = voice_channel
    guild = MagicMock()
    guild.get_channel.return_value = MagicMock()
    guild.get_member.return_value = member
    bot = MagicMock()
    bot.get_guild.return_value = guild
    server = ActivityServer(
        {state.guild_id: state},
        {state.guild_id: (playlist_service, player_service)},
        '.',
        client_id_provider=lambda: '123456',
        bot_provider=lambda: bot,
    )

    message = await server._execute_control(
        state.guild_id, 998877665, 'play_pause', {}
    )

    voice_channel.connect.assert_awaited_once_with()
    assert state.voice_client is connected_voice
    assert state.voice_bot is bot
    player_service.tocar_atual.assert_awaited_once()
    assert message == 'Bot conectado à sua call e reprodução iniciada.'


@pytest.mark.asyncio
async def test_controle_web_limita_volume_em_duzentos_porcento(
    player_service, playlist_service
):
    state = player_service.state
    state.player_channel_id = 777
    state.voice_client = MagicMock()
    state.voice_client.is_connected.return_value = True
    player_service.persistir_estado = AsyncMock()
    player_service.atualizar_status_agora = AsyncMock()

    guild = MagicMock()
    guild.get_channel.return_value = MagicMock()
    guild.get_member.return_value = 'Usuario Web'
    bot = MagicMock()
    bot.get_guild.return_value = guild
    server = ActivityServer(
        {state.guild_id: state},
        {state.guild_id: (playlist_service, player_service)},
        '.',
        client_id_provider=lambda: '123456',
        bot_provider=lambda: bot,
    )

    message = await server._execute_control(
        state.guild_id, 998877665, 'volume', {'value': 250}
    )

    assert state.voice_volume == 2.0
    assert state.voice_client.source.volume == 2.0
    player_service.persistir_estado.assert_awaited_once()
    assert message == 'Volume ajustado para 200%.'
