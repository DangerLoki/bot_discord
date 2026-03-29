#!/usr/bin/env python3
"""
Verifica se um vídeo pode ser baixado pelo bot.

Uso:
    python test_download.py [--proxy <url>] <url_ou_id_ou_termo>

Exemplos:
    python test_download.py https://www.youtube.com/watch?v=dQw4w9WgXcQ
    python test_download.py dQw4w9WgXcQ
    python test_download.py "black clover opening 1"
    python test_download.py --proxy socks5://127.0.0.1:1080 e_tjkZ8GzFQ

Proxy também pode ser definido em config.env:
    ytdlp_proxy=socks5://127.0.0.1:1080
"""

import sys
import re
import shutil
import yt_dlp
from pathlib import Path

ROOT         = Path(__file__).parent
COOKIES_FILE = ROOT / 'config' / 'cookies.txt'
CACHE_DIR    = ROOT / 'cache' / 'test'
CONFIG_ENV   = ROOT / 'config.env'

GEO_KEYWORDS = [
    'not made this video available in your country',
    'this video is not available in your country',
    'blocked it in your country',
    'geo restricted',
]


def _load_proxy_from_env() -> str | None:
    """Lê ytdlp_proxy do config.env sem dependência externa."""
    if not CONFIG_ENV.exists():
        return None
    for line in CONFIG_ENV.read_text().splitlines():
        line = line.strip()
        if line.startswith('ytdlp_proxy='):
            value = line.split('=', 1)[1].strip()
            return value or None
    return None


def resolver_url(entrada: str) -> tuple[str, str]:
    if entrada.startswith('http'):
        m = re.search(r'(?:v=|youtu\.be/)([a-zA-Z0-9_-]{11})', entrada)
        return entrada, (m.group(1) if m else 'unknown')

    if len(entrada) == 11 and ' ' not in entrada:
        return f'https://www.youtube.com/watch?v={entrada}', entrada

    print(f'🔍 Buscando "{entrada}"...')
    with yt_dlp.YoutubeDL({'quiet': True, 'extract_flat': True, 'default_search': 'ytsearch1'}) as ydl:
        info  = ydl.extract_info(f'ytsearch1:{entrada}', download=False)
        entry = info['entries'][0]
        url   = entry.get('webpage_url') or f"https://www.youtube.com/watch?v={entry['id']}"
        print(f'   → {entry.get("title", "?")} ({url})')
        return url, entry['id']


def base_opts(video_id: str, proxy: str | None) -> dict:
    opts = {
        'format': 'bestaudio/best',
        'outtmpl': str(CACHE_DIR / video_id) + '.%(ext)s',
        'quiet': True,
        'no_warnings': True,
        'noplaylist': True,
        'js_runtimes': {'node': {}},
        'postprocessors': [{'key': 'FFmpegExtractAudio', 'preferredcodec': 'opus', 'preferredquality': '0'}],
    }
    if COOKIES_FILE.exists():
        opts['cookiefile'] = str(COOKIES_FILE)
        print(f'🍪 Usando cookies: {COOKIES_FILE}')
    if proxy:
        opts['proxy'] = proxy
        print(f'🌐 Proxy: {proxy}')
    return opts


def main():
    args = sys.argv[1:]

    # extrai --proxy
    proxy: str | None = None
    if '--proxy' in args:
        idx = args.index('--proxy')
        if idx + 1 >= len(args):
            print('❌ --proxy requer um valor. Ex: --proxy socks5://127.0.0.1:1080')
            sys.exit(1)
        proxy = args[idx + 1]
        args = args[:idx] + args[idx + 2:]

    # fallback para config.env
    if not proxy:
        proxy = _load_proxy_from_env()

    if not args:
        print(__doc__)
        sys.exit(1)

    entrada = ' '.join(args)

    try:
        url, video_id = resolver_url(entrada)
    except Exception as e:
        print(f'❌ Erro ao resolver URL: {e}')
        sys.exit(1)

    print(f'\n📎 URL : {url}')
    print(f'🆔 ID  : {video_id}')
    print('─' * 55)

    CACHE_DIR.mkdir(parents=True, exist_ok=True)

    print('🔎 Verificando metadados... ', end='', flush=True)
    info_opts = {'quiet': True, 'no_warnings': True, 'noplaylist': True, 'js_runtimes': {'node': {}}}
    if COOKIES_FILE.exists():
        info_opts['cookiefile'] = str(COOKIES_FILE)
    if proxy:
        info_opts['proxy'] = proxy
    try:
        with yt_dlp.YoutubeDL(info_opts) as ydl:
            info = ydl.extract_info(url, download=False)
        print('✅')
        print(f'   Título  : {info.get("title", "?")}')
        print(f'   Canal   : {info.get("uploader", "?")}')
        print(f'   Duração : {info.get("duration", 0) // 60:02d}:{info.get("duration", 0) % 60:02d}')
    except Exception as e:
        err = str(e)
        if any(k in err.lower() for k in GEO_KEYWORDS):
            print('🌍 BLOQUEADO NA REGIÃO')
            print('\n❌ Este vídeo não está disponível no seu país.')
            if not proxy:
                print('   Use um proxy de uma região permitida:')
                print('   python test_download.py --proxy socks5://127.0.0.1:1080 ' + video_id)
                print('   Ou defina ytdlp_proxy= no config.env para aplicar sempre.')
            shutil.rmtree(CACHE_DIR, ignore_errors=True)
            sys.exit(2)
        print(f'❌ Erro: {err.splitlines()[0][:80]}')
        shutil.rmtree(CACHE_DIR, ignore_errors=True)
        sys.exit(1)

    print('\n⬇️  Testando download de áudio... ', end='', flush=True)
    try:
        with yt_dlp.YoutubeDL(base_opts(video_id, proxy)) as ydl:
            ydl.download([url])
        resultado = list(CACHE_DIR.glob(f'{video_id}.*'))
        if resultado:
            tamanho = resultado[0].stat().st_size / 1024 / 1024
            print(f'✅  ({tamanho:.2f} MB)')
            print(f'\n✅ DOWNLOAD OK — {resultado[0].name}')
        else:
            print('⚠️  arquivo não encontrado após download')
    except Exception as e:
        err = str(e)
        if any(k in err.lower() for k in GEO_KEYWORDS):
            print('🌍 BLOQUEADO NA REGIÃO')
            print('\n❌ Metadados disponíveis mas download bloqueado por geo-restrição.')
        else:
            print(f'❌\n   {err.splitlines()[0][:100]}')
    finally:
        shutil.rmtree(CACHE_DIR, ignore_errors=True)
        print('   Cache de teste removido.')


if __name__ == '__main__':
    main()
