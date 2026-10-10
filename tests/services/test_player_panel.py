"""Regressões de sincronização entre a fila e os controles do player."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.models.player_state import RepeatMode
from src.repositories.config_repository import ConfigRepository
from tests.conftest import make_video


def _playlist():
    return [
        make_video('v1', titulo='Primeira'),
        make_video('v2', titulo='Segunda'),
        make_video('v3', titulo='Terceira'),
    ]


def test_embed_da_fila_respeita_ordem_do_shuffle(player_service):
    playlist = _playlist()
    state = player_service.state
    state.shuffle_mode = True
    state.shuffle_playlist = [2, 0, 1]
    state.shuffle_index = 1
    state.shuffle_id = 'abc12345'
    state.playlist_index = 2

    embed = player_service._construir_embed_playlist(playlist, state.playlist_index)

    linhas = embed.description.splitlines()
    assert embed.title == '🔀 Fila Aleatória'
    assert '▶️ **1.** [Terceira]' in linhas[0]
    assert '⏭️ **2.** [Primeira]' in linhas[1]
    assert '▫️ **3.** [Segunda]' in linhas[2]
    assert 'Shuffle abc12345' in embed.footer.text


def test_fila_normal_nao_marca_inicio_como_proximo_ao_chegar_no_fim(player_service):
    playlist = _playlist()
    player_service.state.playlist_index = 2
    player_service.state.repeat_mode = RepeatMode.OFF

    embed = player_service._construir_embed_playlist(playlist, 2)

    assert '⏭️' not in embed.description
    assert '▶️ **3.** [Terceira]' in embed.description


def test_paginacao_desabilita_botoes_nos_limites(player_service):
    playlist = [make_video(f'v{i}', titulo=f'Música {i}') for i in range(20)]

    player_service._construir_embed_playlist(playlist, 0, inicio=0)
    assert player_service.queue_view.pagina_anterior.disabled is True
    assert player_service.queue_view.proxima_pagina.disabled is False

    player_service._construir_embed_playlist(playlist, 19, inicio=5)
    assert player_service.queue_view.pagina_anterior.disabled is False
    assert player_service.queue_view.proxima_pagina.disabled is True


def test_botoes_refletem_shuffle_repeat_e_pausa(player_service):
    state = player_service.state
    state.shuffle_mode = True
    state.repeat_mode = RepeatMode.ONE
    state.voice_client = MagicMock()
    state.voice_client.is_paused.return_value = True
    state.voice_client.is_playing.return_value = False

    player_service.view.sincronizar_estado(state)

    assert player_service.view.alternar_shuffle.style.name == 'success'
    assert str(player_service.view.alternar_repeat.emoji) == '🔂'
    assert player_service.view.alternar_repeat.style.name == 'success'
    assert str(player_service.view.pausar_retomar.emoji) == '▶️'


def test_painel_ocioso_informa_quando_a_fila_esta_pronta(player_service):
    embed = player_service._construir_embed_ocioso(277)

    assert '277 música(s) aguardando na fila' in embed.description
    assert 'pressione **▶️** para começar' in embed.description
    assert 'adicionar uma música' not in embed.description
    assert embed.footer.text == 'A fila está pronta para reprodução.'


def test_painel_ocioso_so_pede_musica_quando_fila_esta_vazia(player_service):
    embed = player_service._construir_embed_ocioso(0)

    assert 'A fila está vazia' in embed.description
    assert 'adicionar uma música' in embed.description


@pytest.mark.asyncio
async def test_botao_volume_persiste_preferencia_da_guild(player_service, tmp_path):
    player_service.config_repo = ConfigRepository(str(tmp_path))
    player_service.atualizar_status_agora = AsyncMock()
    interaction = MagicMock()
    interaction.guild = None
    interaction.response.defer = AsyncMock()

    await player_service.view.volume_mais.callback(interaction)

    config = player_service.config_repo.load(player_service.state.guild_id)
    assert player_service.state.voice_volume == 0.35
    assert config['player_state']['voice_volume'] == 0.35


def test_falha_de_download_avanca_na_ordem_do_shuffle(player_service):
    playlist = _playlist()
    player_service.repo.save(player_service.state.guild_id, playlist)
    state = player_service.state
    state.playlist_index = 0
    state.shuffle_mode = True
    state.shuffle_playlist = [0, 2, 1]
    state.shuffle_index = 1

    assert player_service._avancar_apos_falha(playlist) is True

    assert state.playlist_index == 2
    assert state.shuffle_index == 2


@pytest.mark.asyncio
async def test_ativar_shuffle_mantem_atual_no_topo_e_atualiza_painel(
    playlist_service, fake_ctx
):
    playlist_service.repo.save(playlist_service.state.guild_id, _playlist())
    playlist_service.state.playlist_index = 1
    playlist_service.player_svc = MagicMock(atualizar_painel=AsyncMock())

    with patch('src.services.playlist_service.random.shuffle', side_effect=lambda itens: itens.reverse()):
        await playlist_service.toggle_shuffle(fake_ctx, silencioso=True)

    assert playlist_service.state.shuffle_playlist[0] == 1
    assert playlist_service.state.shuffle_index == 1
    playlist_service.player_svc.atualizar_painel.assert_awaited_once()


@pytest.mark.asyncio
async def test_limpar_fila_atualiza_painel_imediatamente(playlist_service, fake_ctx):
    playlist_service.repo.save(playlist_service.state.guild_id, _playlist())
    playlist_service.player_svc = MagicMock(atualizar_painel=AsyncMock())

    await playlist_service.limpar_playlist(fake_ctx)

    assert playlist_service.repo.load(playlist_service.state.guild_id) == []
    playlist_service.player_svc.atualizar_painel.assert_awaited_once()


@pytest.mark.asyncio
async def test_promover_no_shuffle_move_musica_para_proxima_posicao(
    playlist_service, fake_ctx
):
    playlist_service.repo.save(playlist_service.state.guild_id, _playlist())
    state = playlist_service.state
    state.playlist_index = 0
    state.shuffle_mode = True
    state.shuffle_playlist = [0, 2, 1]
    state.shuffle_index = 1

    await playlist_service.promover_video(fake_ctx, '3')

    assert state.shuffle_playlist == [0, 1, 2]
    assert state.shuffle_index == 1


@pytest.mark.asyncio
async def test_inverter_no_shuffle_inverte_somente_futuras(
    playlist_service, fake_ctx
):
    playlist_service.repo.save(playlist_service.state.guild_id, _playlist())
    state = playlist_service.state
    state.playlist_index = 0
    state.shuffle_mode = True
    state.shuffle_playlist = [0, 1, 2]
    state.shuffle_index = 1

    await playlist_service.inverter_playlist(fake_ctx, silencioso=True)

    assert state.shuffle_playlist == [0, 2, 1]


@pytest.mark.asyncio
async def test_remover_atual_no_shuffle_avanca_para_proxima_aleatoria(
    playlist_service, fake_ctx
):
    playlist_service.repo.save(playlist_service.state.guild_id, _playlist())
    state = playlist_service.state
    state.playlist_index = 0
    state.shuffle_mode = True
    state.shuffle_playlist = [0, 2, 1]
    state.shuffle_index = 1

    await playlist_service.remover_video(fake_ctx, '1')

    restante = playlist_service.repo.load(state.guild_id)
    assert [video['video_id'] for video in restante] == ['v2', 'v3']
    assert state.playlist_index == 1
    assert restante[state.playlist_index]['video_id'] == 'v3'
