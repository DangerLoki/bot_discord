import os
import asyncio
import urllib.parse
import yt_dlp

from src.logger import get_logger
from src.bot.utils import _is_geo_blocked, formatar_duracao

logger = get_logger(__name__)


class YouTubeMixin:
    """Métodos de consulta ao YouTube via yt-dlp (sem download)."""

    async def obter_info_video(self, url: str):
        """Obtém metadados de um vídeo. Retorna dict ou None em caso de erro."""
        import time as _time
        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'extract_flat': False,
            'noplaylist': True,
            'js_runtimes': {'node': {}},
        }
        if os.path.exists(self.cookies_file):
            ydl_opts['cookiefile'] = self.cookies_file
        if self.proxy:
            ydl_opts['proxy'] = self.proxy

        def _extract():
            t0 = _time.perf_counter()
            try:
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    info = ydl.extract_info(url, download=False)
                elapsed = _time.perf_counter() - t0
                logger.info(f'[PERF][INFO] url={url} tempo={elapsed:.2f}s')
                return {
                    'titulo': info.get('title', 'Título não disponível'),
                    'duracao': info.get('duration', 0),
                    'duracao_formatada': formatar_duracao(info.get('duration', 0)),
                    'canal': info.get('uploader', 'Desconhecido'),
                    'views': info.get('view_count', 0),
                }
            except Exception as e:
                elapsed = _time.perf_counter() - t0
                if _is_geo_blocked(str(e)):
                    logger.warning(f'[PERF][INFO] geo-blocked após {elapsed:.2f}s: {url}')
                    return {'geo_blocked': True}
                logger.error(f'[PERF][INFO] erro após {elapsed:.2f}s: {e}', exc_info=True)
                return None

        return await asyncio.to_thread(_extract)

    async def buscar_videos_youtube(self, termo_busca: str, max_resultados: int = 5):
        """Busca vídeos no YouTube e retorna lista de dicts."""
        ydl_opts = {
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
            import time as _time
            t0 = _time.perf_counter()
            try:
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    info = ydl.extract_info(
                        f"ytsearch{max_resultados}:{termo_busca}", download=False
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
                elapsed = _time.perf_counter() - t0
                logger.info(
                    f'[PERF][BUSCA] termo="{termo_busca}" '
                    f'resultados={len(results)} tempo={elapsed:.2f}s'
                )
                return results
            except Exception as e:
                elapsed = _time.perf_counter() - t0
                logger.error(f'[PERF][BUSCA] erro após {elapsed:.2f}s: {e}', exc_info=True)
                return []

        return await asyncio.to_thread(_search)

    async def obter_videos_playlist(self, url: str, mix_limit: int = 50):
        """Extrai todos os vídeos de uma playlist do YouTube (modo flat).
        Retorna tupla (titulo_pl, lista_de_videos, is_mix).
        """
        parsed = urllib.parse.urlparse(url)
        params = urllib.parse.parse_qs(parsed.query)
        playlist_id = params['list'][0] if 'list' in params else None
        is_mix = bool(playlist_id and playlist_id.startswith('RD'))

        if is_mix:
            extract_url = url
            ydl_opts = {
                'quiet': True,
                'no_warnings': True,
                'extract_flat': True,
                'ignoreerrors': True,
                'playlistend': mix_limit,
            }
            logger.debug(f'Extraindo YouTube Mix (limite {mix_limit}): {extract_url}')
        else:
            extract_url = (
                f'https://www.youtube.com/playlist?list={playlist_id}'
                if playlist_id else url
            )
            ydl_opts = {
                'quiet': True,
                'no_warnings': True,
                'extract_flat': 'in_playlist',
                'ignoreerrors': True,
            }
            logger.debug(f'Extraindo playlist: {extract_url}')

        if os.path.exists(self.cookies_file):
            ydl_opts['cookiefile'] = self.cookies_file

        def _extract():
            import time as _time
            t0 = _time.perf_counter()
            try:
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    info = ydl.extract_info(extract_url, download=False)
                    if not info:
                        logger.warning(f'[PERF][PLAYLIST] sem resposta após {_time.perf_counter()-t0:.2f}s: {extract_url}')
                        return None, [], is_mix
                    if info.get('_type') == 'video' or 'entries' not in info:
                        logger.warning('yt-dlp retornou vídeo único, esperava playlist')
                        return None, [], is_mix
                    titulo_pl = info.get('title') or ('YouTube Mix' if is_mix else 'Playlist')
                    videos = []
                    for entry in list(info.get('entries', [])):
                        if not entry or not entry.get('id'):
                            continue
                        vid_id = entry.get('id')
                        videos.append({
                            'video_id': vid_id,
                            'titulo': entry.get('title') or f'Vídeo {vid_id[:8]}',
                            'duracao': entry.get('duration') or 0,
                            'duracao_formatada': formatar_duracao(entry.get('duration') or 0),
                            'canal': (
                                entry.get('uploader') or entry.get('channel') or 'Desconhecido'
                            ),
                            'embed_url': f'https://www.youtube.com/watch?v={vid_id}',
                            'thumbnail_url': f'https://img.youtube.com/vi/{vid_id}/hqdefault.jpg',
                        })
                    elapsed = _time.perf_counter() - t0
                    logger.info(
                        f'[PERF][PLAYLIST] "{titulo_pl}" '
                        f'{len(videos)} vídeos extraídos (mix={is_mix}) tempo={elapsed:.2f}s'
                    )
                    return titulo_pl, videos, is_mix
            except Exception as e:
                elapsed = _time.perf_counter() - t0
                logger.error(f'[PERF][PLAYLIST] erro após {elapsed:.2f}s: {e}', exc_info=True)
                return None, [], is_mix

        return await asyncio.to_thread(_extract)
