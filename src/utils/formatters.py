import re


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
