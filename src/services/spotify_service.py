"""Serviço de integração com a API do Spotify."""
import asyncio
import re
import time
import requests as _requests

from src.logger import get_logger

try:
    import spotipy
    from spotipy.oauth2 import SpotifyClientCredentials
    _SPOTIPY_AVAILABLE = True
except ImportError:
    spotipy = None  # type: ignore[assignment]
    SpotifyClientCredentials = None  # type: ignore[assignment,misc]
    _SPOTIPY_AVAILABLE = False

logger = get_logger(__name__)


class SpotifyService:
    """Consulta metadados de faixas, álbuns e playlists do Spotify."""

    def __init__(self, client_id: str | None, client_secret: str | None) -> None:
        self.client_id = client_id
        self.client_secret = client_secret

    # ------------------------------------------------------------------
    # Helpers estáticos
    # ------------------------------------------------------------------

    @staticmethod
    def extrair_tipo_id(url: str) -> tuple[str | None, str | None]:
        """Extrai (tipo, id) de uma URL do Spotify.

        Tipos suportados: track, album, playlist.
        """
        match = re.search(
            r'open\.spotify\.com/(?:[a-z]{2,5}-[a-z]{2,5}/)?(track|album|playlist)/([a-zA-Z0-9]+)',
            url,
        )
        if match:
            return match.group(1), match.group(2)
        return None, None

    @staticmethod
    def is_spotify_url(url: str) -> bool:
        return 'open.spotify.com' in url

    # ------------------------------------------------------------------
    # Cliente
    # ------------------------------------------------------------------

    def _criar_cliente(self):
        if not _SPOTIPY_AVAILABLE:
            logger.error('[SPOTIFY] spotipy não instalado. Execute: pip install spotipy')
            return None
        if not self.client_id or not self.client_secret:
            return None
        try:
            auth = SpotifyClientCredentials(
                client_id=self.client_id,
                client_secret=self.client_secret,
            )
            return spotipy.Spotify(auth_manager=auth)
        except Exception as e:
            logger.error(f'[SPOTIFY] Erro ao autenticar: {e}')
            return None

    def _get(self, sp, path: str, **params) -> dict:
        """GET direto na API do Spotify (sem parâmetros extras do spotipy)."""
        token = sp.auth_manager.get_access_token(as_dict=False)
        url = f'https://api.spotify.com/v1/{path}'
        clean_params = {k: v for k, v in params.items() if v is not None}
        r = _requests.get(
            url,
            headers={'Authorization': f'Bearer {token}'},
            params=clean_params,
            timeout=15,
        )
        r.raise_for_status()
        return r.json()

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

    # ------------------------------------------------------------------
    # Fallback: scraping do embed do Spotify
    # ------------------------------------------------------------------

    def _tracks_via_embed(self, playlist_id: str) -> tuple[str | None, list]:
        import json as _json

        embed_url = f'https://open.spotify.com/embed/playlist/{playlist_id}'
        r = _requests.get(
            embed_url,
            headers={'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36'},
            timeout=15,
        )
        r.raise_for_status()

        match = re.search(
            r'<script[^>]*id="__NEXT_DATA__"[^>]*>(.*?)</script>', r.text
        )
        if not match:
            logger.warning('[SPOTIFY] Embed: __NEXT_DATA__ não encontrado')
            return None, []

        data = _json.loads(match.group(1))
        entity = (
            data.get('props', {})
            .get('pageProps', {})
            .get('state', {})
            .get('data', {})
            .get('entity', {})
        )
        nome_pl = entity.get('name', 'Playlist Spotify')
        tracks = [
            {
                'titulo': t.get('title', ''),
                'artista': t.get('subtitle', ''),
                'album': '',
                'duracao': t.get('duration', 0) // 1000,
            }
            for t in entity.get('trackList', [])
            if t.get('entityType') == 'track' and t.get('isPlayable', False)
        ]
        logger.info(f'[SPOTIFY] Embed: extraídas {len(tracks)} faixas de "{nome_pl}"')
        return nome_pl, tracks
