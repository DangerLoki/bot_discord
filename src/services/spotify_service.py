"""Serviço de integração com a API do Spotify."""
import asyncio
import re
import time
import requests as _requests

from src.logger import get_logger
from src.services.spotify_client import SpotifyAPIClient
# Métodos herdados do cliente: _criar_cliente, _get, _tracks_via_embed,
#                               extrair_tipo_id, is_spotify_url

logger = get_logger(__name__)


class SpotifyService(SpotifyAPIClient):
    """Consulta metadados de faixas, álbuns e playlists do Spotify."""

    # __init__ herdado de SpotifyAPIClient(client_id, client_secret)

    # ------------------------------------------------------------------
    # Consultas
    # ------------------------------------------------------------------

    async def obter_track(self, track_id: str) -> dict | None:
        """Retorna metadados de uma faixa."""

        def _fetch():
            t0 = time.perf_counter()
            sp = self._criar_cliente()
            if not sp:
                return None
            try:
                t = self._get(sp, f'tracks/{track_id}')
                elapsed = time.perf_counter() - t0
                logger.info(f'[PERF][SPOTIFY_TRACK] track_id={track_id} tempo={elapsed:.2f}s')
                return {
                    'titulo': t['name'],
                    'artista': ', '.join(a['name'] for a in t['artists']),
                    'album': t['album']['name'],
                    'duracao': t['duration_ms'] // 1000,
                }
            except Exception as e:
                elapsed = time.perf_counter() - t0
                logger.error(
                    f'[PERF][SPOTIFY_TRACK] erro após {elapsed:.2f}s track_id={track_id}: {e}'
                )
                return None

        return await asyncio.to_thread(_fetch)

    async def obter_tracks_album(
        self, album_id: str
    ) -> tuple[str | None, str | None, list]:
        """Retorna (nome_album, artista_album, tracks) de um álbum."""

        def _fetch():
            sp = self._criar_cliente()
            if not sp:
                return None, None, []
            try:
                album = self._get(sp, f'albums/{album_id}')
                nome_album = album['name']
                artista_album = ', '.join(a['name'] for a in album['artists'])
                tracks = [
                    {
                        'titulo': item['name'],
                        'artista': ', '.join(a['name'] for a in item['artists']),
                        'album': nome_album,
                        'duracao': item['duration_ms'] // 1000,
                    }
                    for item in album['tracks']['items']
                ]
                return nome_album, artista_album, tracks
            except Exception as e:
                logger.error(f'[SPOTIFY] Erro ao obter álbum {album_id}: {e}')
                return None, None, []

        return await asyncio.to_thread(_fetch)

    async def obter_tracks_playlist(
        self, playlist_id: str
    ) -> tuple[str | None, list]:
        """Retorna (nome_playlist, tracks). Usa fallback via embed se necessário."""

        def _fetch():
            sp = self._criar_cliente()
            if not sp:
                return None, []

            # Tentativa 1: API REST
            try:
                meta = self._get(sp, f'playlists/{playlist_id}', fields='name')
                nome_pl = meta.get('name', 'Playlist Spotify')
                tracks = []
                limit, offset = 50, 0
                while True:
                    page = self._get(
                        sp,
                        f'playlists/{playlist_id}/tracks',
                        fields='items(track(name,type,duration_ms,artists(name),album(name))),next',
                        limit=limit,
                        offset=offset,
                    )
                    for item in page.get('items', []):
                        t = item.get('track')
                        if not t or t.get('type') != 'track' or not t.get('artists'):
                            continue
                        tracks.append({
                            'titulo': t['name'],
                            'artista': ', '.join(a['name'] for a in t['artists']),
                            'album': t.get('album', {}).get('name', ''),
                            'duracao': t['duration_ms'] // 1000,
                        })
                    if not page.get('next'):
                        break
                    offset += limit
                if tracks:
                    return nome_pl, tracks
            except _requests.exceptions.HTTPError as e:
                status = e.response.status_code if e.response is not None else 0
                if status in (401, 403):
                    logger.info(
                        f'[SPOTIFY] API retornou {status} para playlist '
                        f'{playlist_id}, tentando via embed...'
                    )
                else:
                    logger.error(f'[SPOTIFY] HTTP {status} para playlist {playlist_id}: {e}')
                    return None, []
            except Exception as e:
                logger.error(f'[SPOTIFY] Erro ao obter playlist via API: {e}')

            # Tentativa 2: Fallback embed
            try:
                return self._tracks_via_embed(playlist_id)
            except Exception as e:
                logger.error(f'[SPOTIFY] Fallback embed falhou: {e}')
                return None, []

        return await asyncio.to_thread(_fetch)

    # NOTE: _tracks_via_embed herdado de SpotifyAPIClient (spotify_client.py)
