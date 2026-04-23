"""Busca de metadados e pesquisa de vídeos no YouTube."""
import asyncio
import time

import yt_dlp

from src.logger import get_logger
from src.utils import GeoBlockedError, _is_geo_blocked, formatar_duracao

logger = get_logger(__name__)


class YouTubeSearch:
    """Opts base, busca por metadados e busca textual no YouTube."""

    # ------------------------------------------------------------------
    # Helpers internos
    # ------------------------------------------------------------------

    def _base_opts(self, extra: dict | None = None) -> dict:
        import os
        opts = {
            'quiet': True,
            'no_warnings': True,
            'noplaylist': True,
            'js_runtimes': {'node': {}},
        }
        if self.cookies_file and os.path.exists(self.cookies_file):
            opts['cookiefile'] = self.cookies_file
        if self.proxy:
            opts['proxy'] = self.proxy
        if extra:
            opts.update(extra)
        return opts

    # ------------------------------------------------------------------
    # Metadados de vídeo único
    # ------------------------------------------------------------------

    async def obter_info_video(self, url: str) -> dict | None:
        """Obtém metadados de um vídeo. Retorna dict ou None em caso de erro."""
        opts = self._base_opts({'extract_flat': False})

        def _extract():
            t0 = time.perf_counter()
            try:
                with yt_dlp.YoutubeDL(opts) as ydl:
                    info = ydl.extract_info(url, download=False)
                elapsed = time.perf_counter() - t0
                logger.info(f'[PERF][INFO] url={url} tempo={elapsed:.2f}s')
                return {
                    'titulo': info.get('title', 'Título não disponível'),
                    'duracao': info.get('duration', 0),
                    'duracao_formatada': formatar_duracao(info.get('duration', 0)),
                    'canal': info.get('uploader', 'Desconhecido'),
                    'views': info.get('view_count', 0),
                    'is_live': bool(info.get('is_live') or info.get('live_status') == 'is_live'),
                }
            except Exception as e:
                elapsed = time.perf_counter() - t0
                if _is_geo_blocked(str(e)):
                    logger.warning(f'[PERF][INFO] geo-blocked após {elapsed:.2f}s: {url}')
                    return {'geo_blocked': True}
                logger.error(f'[PERF][INFO] erro após {elapsed:.2f}s: {e}', exc_info=True)
                return None

        return await asyncio.to_thread(_extract)

    # ------------------------------------------------------------------
    # Busca textual
    # ------------------------------------------------------------------

    async def buscar_videos(self, termo: str, max_resultados: int = 5) -> list:
        """Busca vídeos no YouTube e retorna lista de dicts."""
        opts = {
            'quiet': True,
            'no_warnings': True,
            'extract_flat': True,
            'default_search': 'ytsearch',
            'noplaylist': True,
            'http_headers': {
                'User-Agent': (
                    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                    'AppleWebKit/537.36 (KHTML, like Gecko) '
                    'Chrome/120.0.0.0 Safari/537.36'
                ),
                'Accept-Language': 'pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7',
            },
        }

        def _search():
            t0 = time.perf_counter()
            try:
                with yt_dlp.YoutubeDL(opts) as ydl:
                    info = ydl.extract_info(
                        f'ytsearch{max_resultados}:{termo}', download=False
                    )
                results = [
                    {
                        'video_id': e.get('id'),
                        'titulo': e.get('title'),
                        'url': e.get('webpage_url'),
                        'canal': e.get('uploader'),
                        'duracao_formatada': formatar_duracao(e.get('duration')),
                    }
                    for e in info.get('entries', [])
                ]
                elapsed = time.perf_counter() - t0
                logger.info(
                    f'[PERF][BUSCA] termo="{termo}" '
                    f'resultados={len(results)} tempo={elapsed:.2f}s'
                )
                return results
            except Exception as e:
                elapsed = time.perf_counter() - t0
                logger.error(f'[PERF][BUSCA] erro após {elapsed:.2f}s: {e}', exc_info=True)
                return []

        return await asyncio.to_thread(_search)
