import re

_ANSI_RE = re.compile(r'\x1b\[[0-9;]*m')


class GeoBlockedError(Exception):
    """Levantado quando um vídeo está bloqueado por geo-restrição."""
    pass


class BotBlockedError(Exception):
    """Levantado quando o YouTube exige autenticação (detecção de bot)."""
    pass


_GEO_KEYWORDS = [
    'not made this video available in your country',
    'this video is not available in your country',
    'blocked it in your country',
    'geo restricted',
]

_BOT_KEYWORDS = [
    "sign in to confirm you're not a bot",
    'sign in to confirm',
    "confirm you're not a bot",
    'use --cookies-from-browser',
]


def _strip_ansi(msg: str) -> str:
    return _ANSI_RE.sub('', msg)


def _is_geo_blocked(msg: str) -> bool:
    m = _strip_ansi(msg).lower()
    return any(kw in m for kw in _GEO_KEYWORDS)


def _is_bot_blocked(msg: str) -> bool:
    m = _strip_ansi(msg).lower()
    return any(kw in m for kw in _BOT_KEYWORDS)
