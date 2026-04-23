"""Cliente de baixo nível para a API do Spotify e scraping do embed."""
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


class SpotifyAPIClient:
    """Gerencia autenticação, requests REST e fallback via embed HTML."""

    def __init__(self, client_id: str | None, client_secret: str | None) -> None:
        self.client_id = client_id
        self.client_secret = client_secret

    # ------------------------------------------------------------------
    # Autenticação
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

    # ------------------------------------------------------------------
    # Request REST
    # ------------------------------------------------------------------

    def _get(self, sp, path: str, **params) -> dict:
        """GET direto na API do Spotify sem parâmetros extras do spotipy."""
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
