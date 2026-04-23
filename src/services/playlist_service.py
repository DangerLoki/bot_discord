"""Lógica de negócio para gerenciamento da playlist e navegação."""
import random
import uuid

from src.logger import get_logger
from src.models.player_state import PlayerState
from src.repositories.playlist_repository import PlaylistRepository
from src.services.youtube_service import YouTubeService
from src.services.spotify_service import SpotifyService
from src.services.playlist_add_mixin import PlaylistAddMixin
from src.services.playlist_manage_mixin import PlaylistManageMixin

logger = get_logger(__name__)


class PlaylistService(PlaylistAddMixin, PlaylistManageMixin):
    """Fachada principal: shuffle, navegação core e composição dos mixins.

    Métodos herdados:
      PlaylistAddMixin    → adicionar_por_url, adicionar_por_busca,
                            adicionar_spotify, adicionar_playlist_youtube
      PlaylistManageMixin → remover_video, promover_video, limpar_playlist,
                            pular_video, voltar_video
    """

    def __init__(
        self,
        repo: PlaylistRepository,
        yt: YouTubeService,
        spotify: SpotifyService,
        state: PlayerState,
    ) -> None:
        self.repo = repo
        self.yt = yt
        self.spotify = spotify
        self.state = state

    # ------------------------------------------------------------------
    # Shuffle helpers
    # ------------------------------------------------------------------

    def _atualizar_shuffle_com_novo_video(self, novo_indice: int) -> None:
        if not self.state.shuffle_mode or not self.state.shuffle_playlist:
            return
        posicao = random.randint(0, len(self.state.shuffle_playlist))
        self.state.shuffle_playlist.insert(posicao, novo_indice)
        logger.info(
            f'[SHUFFLE] Vídeo {novo_indice} inserido na posição {posicao} '
            f'(ID: {self.state.shuffle_id})'
        )

    def proximo_aleatorio(self, playlist: list) -> int:
        """Retorna o próximo índice da lista aleatória."""
        st = self.state
        if not st.shuffle_playlist or st.shuffle_index >= len(st.shuffle_playlist):
            nao_tocados = [i for i, v in enumerate(playlist) if not v.get('tocado', False)]
            if nao_tocados:
                random.shuffle(nao_tocados)
                st.shuffle_playlist = nao_tocados
                st.shuffle_index = 0
            else:
                for v in playlist:
                    v['tocado'] = False
                self.repo.save(playlist)
                indices = list(range(len(playlist)))
                random.shuffle(indices)
                st.shuffle_playlist = indices
                st.shuffle_index = 0
        if st.shuffle_playlist:
            index = st.shuffle_playlist[st.shuffle_index]
            st.shuffle_index += 1
            return index
        return st.playlist_index

    def encontrar_proxima_nao_tocada(self) -> None:
        """Define playlist_index na primeira música não tocada ao iniciar."""
        playlist = self.repo.load()
        if not playlist:
            self.state.playlist_index = 0
            return
        for i, video in enumerate(playlist):
            if not video.get('tocado', False):
                self.state.playlist_index = i
                logger.info(
                    f'[INIT] Continuando de: {video.get("titulo", "?")} (posição {i + 1})'
                )
                return
        self.state.playlist_index = 0
        logger.info('[INIT] Todas as músicas foram tocadas. Bot parado.')

    # ------------------------------------------------------------------
    # Shuffle toggle
    # ------------------------------------------------------------------

    async def toggle_shuffle(self, ctx) -> None:
        st = self.state
        st.shuffle_mode = not st.shuffle_mode
        if st.shuffle_mode:
            playlist = self.repo.load()
            nao_tocados = [i for i, v in enumerate(playlist) if not v.get('tocado', False)]
            if nao_tocados:
                random.shuffle(nao_tocados)
                st.shuffle_playlist = nao_tocados
                st.shuffle_index = 0
                st.shuffle_id = str(uuid.uuid4())[:8]
                await ctx.send(
                    f'🔀 Modo aleatório **ativado**! (ID: `{st.shuffle_id}`) '
                    f'Lista criada com {len(nao_tocados)} músicas.'
                )
            else:
                indices = list(range(len(playlist)))
                random.shuffle(indices)
                st.shuffle_playlist = indices
                st.shuffle_index = 0
                st.shuffle_id = str(uuid.uuid4())[:8]
                await ctx.send(
                    f'🔀 Modo aleatório **ativado**! (ID: `{st.shuffle_id}`) '
                    f'Todas as músicas foram resetadas e embaralhadas.'
                )
        else:
            await ctx.send('➡️ Modo aleatório **desativado**. Ordem normal retomada.')
        logger.info(
            f'[SHUFFLE] {"ON" if st.shuffle_mode else "OFF"} '
            f'({st.shuffle_id if st.shuffle_mode else "N/A"}) por {ctx.author}'
        )
