"""Regressões dos fluxos críticos de comandos e views multi-guild."""

import asyncio
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.cogs.music_cog import MusicCog
from src.models.player_state import PlayerState
from src.repositories.playlist_repository import PlaylistRepository
from src.ui.player_controls import PlayerControlView, PlaylistQueueView
from src.utils.healthcheck import HealthCheck
from tests.conftest import make_video


def test_music_cog_helpers_resolvem_estado_e_servicos_da_guild():
    cog = object.__new__(MusicCog)
    estado = object()
    servicos = (object(), object())
    cog.get_state_from_ctx = MagicMock(return_value=estado)
    cog.get_services_from_ctx = MagicMock(return_value=servicos)
    ctx = object()

    assert cog._get_guild_state(ctx) is estado
    assert cog._get_guild_services(ctx) == servicos
    cog.get_state_from_ctx.assert_called_once_with(ctx)
    cog.get_services_from_ctx.assert_called_once_with(ctx)


def test_player_view_resolve_servicos_pela_guild_da_interacao():
    state_1 = PlayerState(1)
    state_2 = PlayerState(2)
    playlist_1, player_1 = MagicMock(), MagicMock(state=state_1)
    playlist_2, player_2 = MagicMock(), MagicMock(state=state_2)
    services = {1: (playlist_1, player_1), 2: (playlist_2, player_2)}
    view = PlayerControlView(
        state_1,
        player_1,
        playlist_1,
        service_resolver=lambda guild_id: services[guild_id],
    )
    interaction = MagicMock()
    interaction.guild.id = 2

    assert view._services_for(interaction) == (state_2, player_2, playlist_2)


def test_queue_view_resolve_servicos_pela_guild_da_interacao():
    state_1 = PlayerState(1)
    state_2 = PlayerState(2)
    playlist_1, player_1 = MagicMock(), MagicMock(state=state_1)
    playlist_2, player_2 = MagicMock(), MagicMock(state=state_2)
    services = {1: (playlist_1, player_1), 2: (playlist_2, player_2)}
    view = PlaylistQueueView(
        state_1,
        player_1,
        playlist_1,
        service_resolver=lambda guild_id: services[guild_id],
    )
    interaction = MagicMock()
    interaction.guild.id = 2

    assert view._services_for(interaction) == (state_2, player_2, playlist_2)


@pytest.mark.asyncio
async def test_tocando_carrega_playlist_da_guild_correta():
    cog = object.__new__(MusicCog)
    state = PlayerState(42)
    state.voice_client = MagicMock()
    state.voice_client.is_connected.return_value = True
    state.voice_client.is_playing.return_value = True
    state.voice_client.is_paused.return_value = False
    cog._guild_states = {42: state}
    cog.repo = MagicMock()
    cog.repo.load.return_value = [make_video('video000001')]
    ctx = MagicMock()
    ctx.guild.id = 42
    ctx.send = AsyncMock()

    await MusicCog.tocando.callback(cog, ctx)

    cog.repo.load.assert_called_once_with(42)
    ctx.send.assert_awaited_once()


@pytest.mark.asyncio
async def test_healthcheck_spotify_usa_token_disponivel():
    spotify = MagicMock(client_id='client-id')
    spotify.get_token = AsyncMock(return_value='token-valido')

    ok, mensagem = await HealthCheck.check_spotify(spotify)

    assert ok is True
    assert 'autenticação bem-sucedida' in mensagem


def test_add_unique_preserva_adicoes_concorrentes(tmp_path):
    repo = PlaylistRepository(str(tmp_path))
    guild_id = 123
    videos = [make_video(f'video{i:06d}') for i in range(20)]

    with ThreadPoolExecutor(max_workers=8) as executor:
        list(executor.map(lambda video: repo.add_unique(guild_id, [video]), videos))

    playlist = repo.load(guild_id)
    assert len(playlist) == len(videos)
    assert {video['video_id'] for video in playlist} == {
        video['video_id'] for video in videos
    }
    assert [video['posicao'] for video in playlist] == list(range(1, 21))


@pytest.mark.asyncio
async def test_download_obsoleto_nao_toca_depois_de_skip(player_service, fake_ctx):
    playlist = [make_video('video000001'), make_video('video000002')]
    player_service.repo.save(player_service.state.guild_id, playlist)
    player_service.state.voice_client = MagicMock()
    player_service.state.voice_client.is_connected.return_value = True
    player_service.state.voice_client.is_playing.return_value = False
    player_service.state.voice_client.is_paused.return_value = False
    player_service._preparar_canal_painel = AsyncMock()
    player_service._atualizar_mensagem_playlist = AsyncMock()
    loading_message = MagicMock(edit=AsyncMock())
    player_service._get_status_message = AsyncMock(return_value=loading_message)
    player_service._iniciar_reproducao = AsyncMock()

    async def baixar(video_url, video_id):
        if video_id == 'video000001':
            player_service.state.playlist_index = 1
        await asyncio.sleep(0)
        return f'/tmp/{video_id}.opus'

    player_service.yt.baixar_audio = AsyncMock(side_effect=baixar)

    with (
        patch('src.services.player_service.discord.FFmpegPCMAudio', return_value=object()),
        patch(
            'src.services.player_service.discord.PCMVolumeTransformer',
            return_value=object(),
        ),
    ):
        await player_service.tocar_atual(fake_ctx)

    ids_baixados = [
        call.kwargs['video_id'] for call in player_service.yt.baixar_audio.await_args_list
    ]
    assert ids_baixados == ['video000001', 'video000002']
    video_tocado = player_service._iniciar_reproducao.await_args.args[2]
    assert video_tocado['video_id'] == 'video000002'


@pytest.mark.asyncio
async def test_remover_faixa_atual_inicia_a_proxima(playlist_service, fake_ctx):
    playlist_service.repo.save(
        playlist_service.state.guild_id,
        [make_video('video000001'), make_video('video000002')],
    )
    voice_client = MagicMock()
    voice_client.is_connected.return_value = True
    playlist_service.state.voice_client = voice_client
    playlist_service.player_svc = MagicMock()
    playlist_service.player_svc.tocar_atual = AsyncMock()

    await playlist_service.remover_video(fake_ctx, '1')

    playlist_service.player_svc.tocar_atual.assert_awaited_once_with(fake_ctx)
    assert playlist_service.repo.load(playlist_service.state.guild_id)[0]['video_id'] == 'video000002'


@pytest.mark.asyncio
async def test_garantir_painel_cria_fila_vazia_com_botao_de_adicionar(
    player_service, fake_ctx
):
    player_service._preparar_canal_painel = AsyncMock()
    player_service._atualizar_mensagem_playlist = AsyncMock()
    player_service._get_status_message = AsyncMock()

    await player_service.garantir_painel(fake_ctx)

    player_service._preparar_canal_painel.assert_awaited_once_with(fake_ctx)
    player_service._atualizar_mensagem_playlist.assert_awaited_once_with(
        fake_ctx, [], 0
    )
    player_service._get_status_message.assert_awaited_once()


@pytest.mark.asyncio
async def test_definircanal_cria_painel_imediatamente():
    cog = object.__new__(MusicCog)
    state = PlayerState(42)
    playlist_svc = MagicMock()
    player_svc = MagicMock()
    player_svc.garantir_painel = AsyncMock()
    cog.get_state_from_ctx = MagicMock(return_value=state)
    cog.get_services_from_ctx = MagicMock(return_value=(playlist_svc, player_svc))
    cog.config_repo = MagicMock()
    ctx = MagicMock()
    ctx.guild.id = 42
    ctx.channel.id = 99
    ctx.channel.mention = '#musica'
    ctx.channel.name = 'musica'
    ctx.send = AsyncMock()

    await MusicCog.definircanal.callback(cog, ctx)

    assert state.player_channel_id == 99
    player_svc.garantir_painel.assert_awaited_once_with(ctx)
