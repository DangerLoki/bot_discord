"""Serviço para consultas e downloads via yt-dlp."""
import os
import asyncio
import time
import urllib.parse
from pathlib import Path

import yt_dlp

from src.logger import get_logger
from src.utils import GeoBlockedError, _is_geo_blocked, formatar_duracao

logger = get_logger(__name__)


class YouTubeService:
    """Busca metadados, realiza buscas e baixa áudio do YouTube."""

    def __init__(
        self,
        cache_dir: Path,
        cookies_file: str = None,
        proxy: str = None,
    ) -> None:
        self.cache_dir = cache_dir
        self.cookies_file = cookies_file
        self.proxy = proxy

    # ------------------------------------------------------------------
    # Helpers internos
    # ------------------------------------------------------------------

    def _base_opts(self, extra: dict | None = None) -> dict:
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
    # Metadados
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
    # Busca
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

    # ------------------------------------------------------------------
    # Playlist
    # ------------------------------------------------------------------

    async def obter_videos_playlist(
        self, url: str, mix_limit: int = 50
    ) -> tuple[str | None, list, bool]:
        """Extrai todos os vídeos de uma playlist do YouTube (modo flat).

        Retorna (titulo_pl, lista_de_videos, is_mix).
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
                if playlist_id
                else url
            )
            ydl_opts = {
                'quiet': True,
                'no_warnings': True,
                'extract_flat': 'in_playlist',
                'ignoreerrors': True,
            }
            logger.debug(f'Extraindo playlist: {extract_url}')

        if self.cookies_file and os.path.exists(self.cookies_file):
            ydl_opts['cookiefile'] = self.cookies_file

        def _extract():
            t0 = time.perf_counter()
            try:
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    info = ydl.extract_info(extract_url, download=False)
                    if not info:
                        logger.warning(
                            f'[PERF][PLAYLIST] sem resposta após '
                            f'{time.perf_counter()-t0:.2f}s: {extract_url}'
                        )
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
                                entry.get('uploader')
                                or entry.get('channel')
                                or 'Desconhecido'
                            ),
                            'embed_url': f'https://www.youtube.com/watch?v={vid_id}',
                            'thumbnail_url': (
                                f'https://img.youtube.com/vi/{vid_id}/hqdefault.jpg'
                            ),
                        })
                    elapsed = time.perf_counter() - t0
                    logger.info(
                        f'[PERF][PLAYLIST] "{titulo_pl}" '
                        f'{len(videos)} vídeos extraídos (mix={is_mix}) tempo={elapsed:.2f}s'
                    )
                    return titulo_pl, videos, is_mix
            except Exception as e:
                elapsed = time.perf_counter() - t0
                logger.error(
                    f'[PERF][PLAYLIST] erro após {elapsed:.2f}s: {e}', exc_info=True
                )
                return None, [], is_mix

        return await asyncio.to_thread(_extract)

    # ------------------------------------------------------------------
    # Download de áudio
    # ------------------------------------------------------------------

    async def baixar_audio(self, video_url: str, video_id: str) -> str | None:
        """Baixa o áudio para o cache. Lança GeoBlockedError se geo-bloqueado."""
        existente = list(self.cache_dir.glob(f'{video_id}.*'))
        if existente:
            logger.debug(f'[CACHE][HIT] usando arquivo em cache: {existente[0]}')
            return str(existente[0])

        logger.debug(f'[CACHE][MISS] iniciando download video_id={video_id}')
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
            t0 = time.perf_counter()
            try:
                with yt_dlp.YoutubeDL(opts) as ydl:
                    ydl.download([video_url])
                resultado = list(self.cache_dir.glob(f'{video_id}.*'))
                elapsed = time.perf_counter() - t0
                if resultado:
                    size_mb = resultado[0].stat().st_size / (1024 * 1024)
                    logger.info(
                        f'[PERF][DOWNLOAD] video_id={video_id} '
                        f'tempo={elapsed:.2f}s tamanho={size_mb:.1f}MB'
                    )
                else:
                    logger.warning(
                        f'[PERF][DOWNLOAD] video_id={video_id} '
                        f'tempo={elapsed:.2f}s — nenhum arquivo gerado'
                    )
                return str(resultado[0]) if resultado else None
            except Exception as e:
                elapsed = time.perf_counter() - t0
                logger.error(
                    f'[PERF][DOWNLOAD] video_id={video_id} falhou após {elapsed:.2f}s: {e}'
                )
                if _is_geo_blocked(str(e)):
                    raise GeoBlockedError(str(e))
                return None

        return await asyncio.to_thread(_download)

    def limpar_cache(self, video_id: str) -> None:
        """Remove os arquivos de cache de um vídeo."""
        for f in self.cache_dir.glob(f'{video_id}.*'):
            try:
                f.unlink()
                logger.debug(f'[CACHE] removido: {f}')
            except Exception as e:
                logger.warning(f'[CACHE] falha ao remover {f}: {e}')
