import re

import discord


class GeoBlockedError(Exception):
    """Levantado quando um vídeo está bloqueado por geo-restrição."""
    pass


_GEO_KEYWORDS = [
    'not made this video available in your country',
    'this video is not available in your country',
    'blocked it in your country',
    'geo restricted',
]


def _is_geo_blocked(msg: str) -> bool:
    m = msg.lower()
    return any(kw in m for kw in _GEO_KEYWORDS)


def formatar_duracao(segundos) -> str:
    """Converte segundos para formato HH:MM:SS ou MM:SS."""
    if not segundos:
        return "00:00"
    segundos = int(segundos)
    horas = segundos // 3600
    minutos = (segundos % 3600) // 60
    segs = segundos % 60
    if horas > 0:
        return f"{horas:02d}:{minutos:02d}:{segs:02d}"
    return f"{minutos:02d}:{segs:02d}"


def extrair_video_id(url: str):
    """Extrai o ID de 11 caracteres de uma URL do YouTube."""
    regex = (
        r"(?:youtube\.com\/(?:watch\?v=|embed\/|shorts\/)|youtu\.be\/)"
        r"([a-zA-Z0-9_-]{11})"
    )
    match = re.search(regex, url)
    return match.group(1) if match else None


def is_spotify_url(url: str) -> bool:
    """Retorna True se a URL for do Spotify."""
    return 'open.spotify.com' in url


def extrair_spotify_tipo_id(url: str) -> tuple[str | None, str | None]:
    """Extrai o tipo (track/album/playlist) e o ID de uma URL do Spotify."""
    match = re.search(
        r'open\.spotify\.com/(?:[a-z]{2,5}-[a-z]{2,5}/)?(track|album|playlist)/([a-zA-Z0-9]+)', url
    )
    if match:
        return match.group(1), match.group(2)
    return None, None


# ------------------------------------------------------------------
# Helpers de embed padronizados
# ------------------------------------------------------------------

def embed_carregando(descricao: str) -> discord.Embed:
    """Embed roxo para estado de carregamento/processando."""
    return discord.Embed(description=descricao, color=0x5865F2)


def embed_erro(descricao: str) -> discord.Embed:
    """Embed vermelho para erros."""
    return discord.Embed(description=descricao, color=0xED4245)


def embed_aviso(descricao: str) -> discord.Embed:
    """Embed amarelo para avisos/informações."""
    return discord.Embed(description=descricao, color=0xFEE75C)


def embed_sucesso(descricao: str) -> discord.Embed:
    """Embed verde para confirmações de sucesso."""
    return discord.Embed(description=descricao, color=0x57F287)
