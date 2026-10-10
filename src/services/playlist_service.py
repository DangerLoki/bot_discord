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

    async def _atualizar_painel(
        self,
        ctx,
        *,
        fila: bool = True,
        player: bool = True,
        preservar_pagina: bool = False,
    ) -> None:
        """Sincroniza as mensagens do painel depois de uma alteração de estado."""
        if self.player_svc:
            await self.player_svc.atualizar_painel(
                ctx,
                atualizar_fila=fila,
                atualizar_player=player,
                preservar_pagina=preservar_pagina,
            )

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
        posicao = random.randint(
            min(self.state.shuffle_index, len(self.state.shuffle_playlist)),
            len(self.state.shuffle_playlist),
        )
        self.state.shuffle_playlist.insert(posicao, novo_indice)
        logger.info(
            f'[SHUFFLE] Vídeo {novo_indice} inserido na posição {posicao} '
            f'(ID: {self.state.shuffle_id})'
        )

    def remover_indice_shuffle(self, indice_removido: int) -> None:
        """Remove um índice da ordem aleatória e renumera os posteriores."""
        st = self.state
        if not st.shuffle_mode or not st.shuffle_playlist:
            return
        posicao_removida = next(
            (
                posicao
                for posicao, indice in enumerate(st.shuffle_playlist)
                if indice == indice_removido
            ),
            None,
        )
        st.shuffle_playlist = [
            indice if indice < indice_removido else indice - 1
            for indice in st.shuffle_playlist
            if indice != indice_removido
        ]
        if posicao_removida is not None and posicao_removida < st.shuffle_index:
            st.shuffle_index = max(0, st.shuffle_index - 1)

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
            self.state.shuffle_playlist = []
            self.state.shuffle_index = 0
            return

        # Restaura apenas índices válidos e sem duplicatas. Assim uma ordem de
        # shuffle persistida não quebra se a playlist foi alterada no disco.
        vistos = set()
        ordem_valida = []
        for indice in self.state.shuffle_playlist:
            if 0 <= indice < len(playlist) and indice not in vistos:
                ordem_valida.append(indice)
                vistos.add(indice)
        self.state.shuffle_playlist = ordem_valida
        self.state.shuffle_index = max(
            0, min(self.state.shuffle_index, len(self.state.shuffle_playlist))
        )

        if (
            self.state.shuffle_mode
            and self.state.shuffle_playlist
            and 0 <= self.state.playlist_index < len(playlist)
        ):
            logger.info(
                f'[INIT] Restaurando shuffle {self.state.shuffle_id or "sem-id"} '
                f'na posição {self.state.shuffle_index}'
            )
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
            resetou = False
            if not nao_tocados and playlist:
                for video in playlist:
                    video['tocado'] = False
                self.repo.save(self.state.guild_id, playlist)
                nao_tocados = list(range(len(playlist)))
                resetou = True

            # Mantém a faixa atual no topo e embaralha somente as próximas.
            # shuffle_index aponta sempre para a próxima faixa a consumir.
            atual = st.playlist_index if 0 <= st.playlist_index < len(playlist) else None
            proximas = [indice for indice in nao_tocados if indice != atual]
            random.shuffle(proximas)
            st.shuffle_playlist = ([atual] if atual is not None else []) + proximas
            st.shuffle_index = 1 if atual is not None else 0
            st.shuffle_id = str(uuid.uuid4())[:8]
            if not silencioso:
                detalhe = (
                    'Todas as músicas foram resetadas e embaralhadas.'
                    if resetou
                    else f'Lista criada com {len(st.shuffle_playlist)} músicas.'
                )
                await ctx.send(
                    f'🔀 Modo aleatório **ativado**! (ID: `{st.shuffle_id}`) {detalhe}'
                )
        elif not silencioso:
            await ctx.send('➡️ Modo aleatório **desativado**. Ordem normal retomada.')
        logger.info(
            f'[SHUFFLE] {"ON" if st.shuffle_mode else "OFF"} '
            f'({st.shuffle_id if st.shuffle_mode else "N/A"}) por {ctx.author}'
        )
        await self._atualizar_painel(ctx)
