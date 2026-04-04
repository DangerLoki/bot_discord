import re


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
