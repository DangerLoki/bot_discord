"""Testes para src.models.player_state.PlayerState."""
import time

from src.models.player_state import PlayerState, RepeatMode


class TestEstadoInicial:
    def test_valores_padrao(self):
        st = PlayerState(guild_id=123456789)
        assert st.is_playing_voice is False
        assert st.repeat_mode == RepeatMode.OFF
        assert st.playlist_index == 0
        assert st.shuffle_mode is False
        assert st.shuffle_playlist == []
        assert st.voice_volume == 0.25


class TestRastreioTempo:
    def test_tempo_decorrido_sem_iniciar_e_zero(self, player_state):
        assert player_state.tempo_decorrido() == 0

    def test_tempo_decorrido_apos_iniciar(self, player_state):
        player_state.iniciar_rastreio_tempo(180)
        time.sleep(0.05)
        assert player_state.tempo_decorrido() >= 0

    def test_pausar_congela_tempo_decorrido(self, player_state):
        player_state.iniciar_rastreio_tempo(180)
        time.sleep(0.05)
        player_state.pausar_rastreio()
        decorrido_1 = player_state.tempo_decorrido()
        time.sleep(0.05)
        decorrido_2 = player_state.tempo_decorrido()
        assert decorrido_1 == decorrido_2

    def test_retomar_continua_apos_pausa(self, player_state):
        player_state.iniciar_rastreio_tempo(180)
        player_state.pausar_rastreio()
        player_state.retomar_rastreio()
        assert player_state._playback_paused_at is None

    def test_pausar_sem_iniciar_nao_quebra(self, player_state):
        player_state.pausar_rastreio()
        assert player_state._playback_paused_at is None

    def test_retomar_sem_pausar_nao_quebra(self, player_state):
        player_state.iniciar_rastreio_tempo(180)
        player_state.retomar_rastreio()
        assert player_state._playback_paused_at is None
