import os
import asyncio
import random
from pathlib import Path

import discord
import yt_dlp

from src.logger import get_logger
from src.bot.utils import GeoBlockedError, _is_geo_blocked

logger = get_logger(__name__)


class PlayerService:
    """Serviço de reprodução de áudio em canal de voz."""

    def __init__(self, cache_dir: Path, cookies_file: str = None, proxy: str = None):
        self.cache_dir = cache_dir
        self.cookies_file = cookies_file
        self.proxy = proxy

    # Download e cache
    async def baixar_audio(self, video_url: str, video_id: str) -> str | None:
        """Baixa o áudio para o cache e retorna o caminho do arquivo.
        Lança GeoBlockedError se o vídeo estiver bloqueado na região.
        """
        existente = list(self.cache_dir.glob(f'{video_id}.*'))
        if existente:
            logger.debug(f'[CACHE] usando arquivo em cache: {existente[0]}')
            return str(existente[0])

        destino = self.cache_dir / video_id
        opts = {
            'format': 'bestaudio/best',
            'outtmpl': str(destino) + '.%(ext)s',
            'quiet': True,
            'no_warnings': True,
            'noplaylist': True,
            'js_runtimes': {'node': {}},
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'opus',
                'preferredquality': '0',
            }],
        }
        if self.cookies_file and os.path.exists(self.cookies_file):
            opts['cookiefile'] = self.cookies_file
        if self.proxy:
            opts['proxy'] = self.proxy

        def _download():
            try:
                with yt_dlp.YoutubeDL(opts) as ydl:
                    ydl.download([video_url])
                resultado = list(self.cache_dir.glob(f'{video_id}.*'))
                return str(resultado[0]) if resultado else None
            except Exception as e:
                if _is_geo_blocked(str(e)):
                    raise GeoBlockedError(str(e))
                logger.error(f'[yt-dlp] erro ao baixar {video_url}: {e}')
                return None

        return await asyncio.to_thread(_download)

    def limpar_cache(self, video_id: str) -> None:
        for f in self.cache_dir.glob(f'{video_id}.*'):
            try:
                f.unlink()
                logger.debug(f'[CACHE] removido: {f}')
            except Exception as e:
                logger.warning(f'[CACHE] falha ao remover {f}: {e}')

    def atualizar_shuffle_com_novo_video(self, novo_indice: int, shuffle_mode: bool, 
                                        shuffle_playlist: list, shuffle_id: str) -> list:
        """Atualiza a lista de shuffle inserindo novo vídeo em posição aleatória."""
        if not shuffle_mode or not shuffle_playlist:
            return shuffle_playlist
        
        posicao_aleatoria = random.randint(0, len(shuffle_playlist))
        shuffle_playlist.insert(posicao_aleatoria, novo_indice)
        
        logger.info(f'[SHUFFLE] Vídeo na posição {novo_indice} inserido na posição {posicao_aleatoria} (ID: {shuffle_id})')
        return shuffle_playlist

    def proximo_aleatorio(self, playlist: list, shuffle_playlist: list, shuffle_index: int,
                         salvar_callback) -> tuple[int, list, int]:
        """Retorna próximo índice da lista aleatória e atualiza estado.
        Retorna (novo_index, novo_shuffle_playlist, novo_shuffle_index)
        """
        if not shuffle_playlist or shuffle_index >= len(shuffle_playlist):
            # Regenera lista
            nao_tocados = [i for i, v in enumerate(playlist) if not v.get('tocado', False)]
            if nao_tocados:
                random.shuffle(nao_tocados)
                shuffle_playlist = nao_tocados
                shuffle_index = 0
            else:
                # Se todos foram tocados, reinicia ciclo
                for v in playlist:
                    v['tocado'] = False
                salvar_callback(playlist)
                indices = list(range(len(playlist)))
                random.shuffle(indices)
                shuffle_playlist = indices
                shuffle_index = 0

        if shuffle_playlist:
            index = shuffle_playlist[shuffle_index]
            shuffle_index += 1
            return index, shuffle_playlist, shuffle_index
        
        return 0, shuffle_playlist, shuffle_index
