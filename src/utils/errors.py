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
