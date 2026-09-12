"""Lógica de negócio para gerenciamento da playlist e navegação."""
import random
import uuid

from src.logger import get_logger
from src.models.player_state import PlayerState
from src.repositories.playlist_repository import PlaylistRepository
from src.services.playlist_add import PlaylistAdd
from src.services.playlist_add_bulk import PlaylistAddBulk
from src.services.playlist_manage import PlaylistManage
from src.services.playlist_nav import PlaylistNav
from src.services.spotify_service import SpotifyService
from src.services.youtube_service import YouTubeService

logger = get_logger(__name__)


class PlaylistService(PlaylistAdd, PlaylistAddBulk, PlaylistManage, PlaylistNav):
    """Façade principal: shuffle, navegação core e composição dos helpers.

    Métodos herdados:
      PlaylistAdd     → adicionar_por_url, adicionar_por_busca
      PlaylistAddBulk → adicionar_spotify, adicionar_playlist_youtube
      PlaylistManage  → remover_video, promover_video, limpar_playlist
      PlaylistNav     → pular_video, voltar_video
    """

    def __init__(
        self,
        repo: PlaylistRepository,
        yt: YouTubeService,
        spotify: SpotifyService,
        state: PlayerState,
        cache_mgr=None,
    ) -> None:
        self.repo = repo
        self.yt = yt
        self.spotify = spotify
        self.state = state
        self.cache_mgr = cache_mgr
        self.player_svc = None  # setado externamente após a criação do PlayerService
        self._cleanup_tasks: set = set()  # referências das tasks de limpeza pós-add

    def _cleanup_orphaned_cache(self) -> None:
        """Limpa arquivos de cache que não estão mais na playlist."""
        if not self.cache_mgr:
            return
        guild_id = self.state.guild_id
        playlist = self.repo.load(guild_id)
        video_ids = {v.get('video_id') for v in playlist if v.get('video_id')}
        self.cache_mgr.cleanup_orphaned_files(guild_id, video_ids)

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
                self.repo.save(self.state.guild_id, playlist)
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
        playlist = self.repo.load(self.state.guild_id)
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

    async def toggle_shuffle(self, ctx, *, silencioso: bool = False) -> None:
        st = self.state
        st.shuffle_mode = not st.shuffle_mode
        if st.shuffle_mode:
            playlist = self.repo.load(self.state.guild_id)
            nao_tocados = [i for i, v in enumerate(playlist) if not v.get('tocado', False)]
            if nao_tocados:
                random.shuffle(nao_tocados)
                st.shuffle_playlist = nao_tocados
                st.shuffle_index = 0
                st.shuffle_id = str(uuid.uuid4())[:8]
                if not silencioso:
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
                if not silencioso:
                    await ctx.send(
                        f'🔀 Modo aleatório **ativado**! (ID: `{st.shuffle_id}`) '
                        f'Todas as músicas foram resetadas e embaralhadas.'
                    )
        elif not silencioso:
            await ctx.send('➡️ Modo aleatório **desativado**. Ordem normal retomada.')
        logger.info(
            f'[SHUFFLE] {"ON" if st.shuffle_mode else "OFF"} '
            f'({st.shuffle_id if st.shuffle_mode else "N/A"}) por {ctx.author}'
        )
