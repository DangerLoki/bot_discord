import asyncio
import re
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


class SpotifyMixin:
    """Métodos de consulta à API do Spotify via spotipy."""

    # ------------------------------------------------------------------
    # Helpers estáticos
    # ------------------------------------------------------------------

    @staticmethod
    def is_spotify_url(url: str) -> bool:
        return 'open.spotify.com' in url

    @staticmethod
    def _extrair_spotify_tipo_id(url: str) -> tuple[str | None, str | None]:
        """Extrai o tipo (track/album/playlist) e o ID de uma URL do Spotify.

        Exemplos aceitos:
            https://open.spotify.com/track/1dGr1c8CrMLDpV6mPbImSI?si=...
            https://open.spotify.com/intl-pt/track/1dGr1c8CrMLDpV6mPbImSI
            https://open.spotify.com/album/1DFixLWuPkv3KT3TnV35m3
            https://open.spotify.com/playlist/37i9dQZF1DXcBWIGoYBM5M
        """
        match = re.search(
            r'open\.spotify\.com/(?:[a-z]{2,5}-[a-z]{2,5}/)?(track|album|playlist)/([a-zA-Z0-9]+)', url
        )
        if match:
            return match.group(1), match.group(2)
        return None, None

    # ------------------------------------------------------------------
    # Cliente Spotify
    # ------------------------------------------------------------------

    def _criar_spotify_client(self):
        """Cria e retorna um cliente Spotify autenticado, ou None se não configurado."""
        if not _SPOTIPY_AVAILABLE:
            logger.error('[SPOTIFY] spotipy não instalado. Execute: pip install spotipy')
            return None
        client_id = getattr(self, 'spotify_client_id', None)
        client_secret = getattr(self, 'spotify_client_secret', None)
        if not client_id or not client_secret:
            return None
        try:
            auth = SpotifyClientCredentials(
                client_id=client_id,
                client_secret=client_secret,
            )
            return spotipy.Spotify(auth_manager=auth)
        except Exception as e:
            logger.error(f'[SPOTIFY] Erro ao autenticar na API: {e}')
            return None

    def _spotify_get(self, sp, path: str, **params) -> dict:
        """Faz GET na API do Spotify sem parâmetros extras injetados pelo spotipy.

        O spotipy injeta `additional_types` e `market` automaticamente, o que
        causa 401/403 em certas chamadas com Client Credentials. Aqui usamos
        requests diretamente com apenas os parâmetros que precisamos.
        """
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

    async def obter_info_spotify_track(self, track_id: str) -> dict | None:
        """Obtém metadados de uma faixa do Spotify."""

        def _fetch():
            sp = self._criar_spotify_client()
            if not sp:
                return None
            try:
                t = self._spotify_get(sp, f'tracks/{track_id}')
                return {
                    'titulo': t['name'],
                    'artista': ', '.join(a['name'] for a in t['artists']),
                    'album': t['album']['name'],
                    'duracao': t['duration_ms'] // 1000,
                }
            except Exception as e:
                logger.error(f'[SPOTIFY] Erro ao obter track {track_id}: {e}')
                return None

        return await asyncio.to_thread(_fetch)

    async def obter_tracks_spotify_album(
        self, album_id: str
    ) -> tuple[str | None, str | None, list]:
        """Retorna (nome_album, artista_album, lista_de_tracks) para um álbum."""

        def _fetch():
            sp = self._criar_spotify_client()
            if not sp:
                return None, None, []
            try:
                album = self._spotify_get(sp, f'albums/{album_id}')
                nome_album = album['name']
                artista_album = ', '.join(a['name'] for a in album['artists'])
                tracks = []
                for item in album['tracks']['items']:
                    tracks.append({
                        'titulo': item['name'],
                        'artista': ', '.join(a['name'] for a in item['artists']),
                        'album': nome_album,
                        'duracao': item['duration_ms'] // 1000,
                    })
                return nome_album, artista_album, tracks
            except Exception as e:
                logger.error(f'[SPOTIFY] Erro ao obter álbum {album_id}: {e}')
                return None, None, []

        return await asyncio.to_thread(_fetch)

    # ------------------------------------------------------------------
    # Fallback: scraping da página de embed do Spotify
    # ------------------------------------------------------------------

    def _obter_tracks_via_embed(self, playlist_id: str) -> tuple[str | None, list]:
        """Extrai faixas da página de embed do Spotify (sem autenticação).

        Funciona mesmo para playlists onde a API REST retorna 403 com
        Client Credentials, pois o embed é público por design.
        """
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
        track_list = entity.get('trackList', [])

        tracks = []
        for t in track_list:
            if t.get('entityType') != 'track' or not t.get('isPlayable', False):
                continue
            tracks.append({
                'titulo': t.get('title', ''),
                'artista': t.get('subtitle', ''),
                'album': '',
                'duracao': t.get('duration', 0) // 1000,
            })

        logger.info(f'[SPOTIFY] Embed: extraídas {len(tracks)} faixas de "{nome_pl}"')
        return nome_pl, tracks

    # ------------------------------------------------------------------
    # Consultas de playlists
    # ------------------------------------------------------------------

    async def obter_tracks_spotify_playlist(
        self, playlist_id: str
    ) -> tuple[str | None, list]:
        """Retorna (nome_playlist, lista_de_tracks) para uma playlist do Spotify.

        Tenta primeiro via API REST. Se receber 403 (restrição da API com
        Client Credentials), usa fallback via página de embed.
        """

        def _fetch():
            sp = self._criar_spotify_client()
            if not sp:
                return None, []

            # --- Tentativa 1: API REST ---
            try:
                meta = self._spotify_get(sp, f'playlists/{playlist_id}', fields='name')
                nome_pl = meta.get('name', 'Playlist Spotify')

                tracks = []
                limit = 50
                offset = 0
                while True:
                    page = self._spotify_get(
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
                    logger.info(f'[SPOTIFY] API retornou {status} para playlist {playlist_id}, tentando via embed...')
                else:
                    logger.error(f'[SPOTIFY] Erro HTTP {status} para playlist {playlist_id}: {e}')
                    return None, []
            except Exception as e:
                logger.error(f'[SPOTIFY] Erro ao obter playlist {playlist_id} via API: {e}')

            # --- Tentativa 2: Fallback via embed ---
            try:
                return self._obter_tracks_via_embed(playlist_id)
            except Exception as e:
                logger.error(f'[SPOTIFY] Fallback embed também falhou para {playlist_id}: {e}', exc_info=True)
                return None, []

        return await asyncio.to_thread(_fetch)
