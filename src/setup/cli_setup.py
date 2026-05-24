"""
Interface CLI para configuração inicial do bot.
Pergunta as credenciais necessárias e cria o arquivo config.env.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

ENV_FILE = Path(__file__).parent.parent.parent / "config.env"

_RESET = "\033[0m"
_BOLD = "\033[1m"
_GREEN = "\033[32m"
_YELLOW = "\033[33m"
_CYAN = "\033[36m"
_RED = "\033[31m"


def _print_header() -> None:
    print()
    print(f"{_BOLD}{_CYAN}{'=' * 52}{_RESET}")
    print(f"{_BOLD}{_CYAN}   Configuração do Bot Discord{_RESET}")
    print(f"{_BOLD}{_CYAN}{'=' * 52}{_RESET}")
    print()


def _ask(prompt: str, *, secret: bool = False, required: bool = True) -> str:
    """Solicita uma entrada ao usuário."""
    label = f"{_BOLD}{prompt}{_RESET}"
    while True:
        try:
            value = input(label).strip()
        except (KeyboardInterrupt, EOFError):
            print(f"\n{_RED}Configuração cancelada.{_RESET}")
            sys.exit(1)

        if value:
            return value
        if not required:
            return ""
        print(f"  {_RED}Este campo é obrigatório.{_RESET}")


def _write_env(config: dict[str, str]) -> None:
    lines: list[str] = [
        "# Arquivo gerado automaticamente pelo cli_setup.py\n",
        "# Edite conforme necessário.\n",
        "\n",
    ]

    # Token do Discord (obrigatório)
    lines.append("# Token do bot Discord (obrigatório)\n")
    lines.append(f"token_discord={config['token_discord']}\n")
    lines.append("\n")

    # Proxy (opcional)
    lines.append("# Proxy para yt-dlp (opcional, deixe em branco para desativar)\n")
    lines.append(f"ytdlp_proxy={config.get('ytdlp_proxy', '')}\n")
    lines.append("\n")

    # Spotify (opcional)
    lines.append("# Credenciais do Spotify (opcionais)\n")
    lines.append(f"spotify_client_id={config.get('spotify_client_id', '')}\n")
    lines.append(f"spotify_client_secret={config.get('spotify_client_secret', '')}\n")

    ENV_FILE.write_text("".join(lines), encoding="utf-8")


def clear_token() -> None:
    """Remove o token_discord do config.env para forçar nova configuração."""
    if not ENV_FILE.exists():
        return
    lines = ENV_FILE.read_text(encoding="utf-8").splitlines(keepends=True)
    new_lines = [
        (f"token_discord=\n" if l.strip().startswith("token_discord=") else l)
        for l in lines
    ]
    ENV_FILE.write_text("".join(new_lines), encoding="utf-8")


def _find_ffmpeg_path() -> Path | None:
    """
    Retorna o Path do ffmpeg.exe se encontrado fora do PATH do processo.
    Retorna None se não encontrar.
    """
    if sys.platform != "win32":
        return None

    import os
    candidates: list[Path] = []

    # Pacotes winget (~\AppData\Local\Microsoft\WinGet\Packages\**)
    winget_base = Path(os.environ.get("LOCALAPPDATA", "")) / "Microsoft" / "WinGet" / "Packages"
    if winget_base.exists():
        candidates.extend(winget_base.rglob("ffmpeg.exe"))

    # Chocolatey
    candidates.append(Path(r"C:\ProgramData\chocolatey\bin\ffmpeg.exe"))

    # Program Files
    for pf in [r"C:\Program Files\ffmpeg\bin\ffmpeg.exe",
               r"C:\Program Files (x86)\ffmpeg\bin\ffmpeg.exe"]:
        candidates.append(Path(pf))

    for path in candidates:
        if path.exists():
            return path

    return None


def _ffmpeg_available() -> bool:
    """Verifica se o ffmpeg está acessível, mesmo que não esteja no PATH do processo atual."""
    if shutil.which("ffmpeg"):
        return True

    if _find_ffmpeg_path():
        return True

    # Linux/macOS fallback
    try:
        result = subprocess.run(
            ["which", "ffmpeg"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return result.returncode == 0
    except FileNotFoundError:
        return False


def inject_ffmpeg_to_path() -> None:
    """
    Se o ffmpeg não estiver no PATH do processo, localiza-o e injeta o
    diretório no os.environ["PATH"] para que discord.py e yt-dlp o encontrem.
    Quando rodando dentro de um bundle PyInstaller, usa o ffmpeg embutido.
    """
    import os

    if shutil.which("ffmpeg"):
        return  # Já acessível, nada a fazer

    # Dentro do bundle PyInstaller: usa o ffmpeg embutido em sys._MEIPASS
    if getattr(sys, "frozen", False):
        import sys as _sys
        meipass = Path(getattr(_sys, "_MEIPASS", ""))
        ffmpeg_name = "ffmpeg.exe" if sys.platform == "win32" else "ffmpeg"
        bundled = meipass / ffmpeg_name
        if bundled.exists():
            os.environ["PATH"] = str(meipass) + os.pathsep + os.environ.get("PATH", "")
            return

    ffmpeg_exe = _find_ffmpeg_path()
    if ffmpeg_exe:
        bin_dir = str(ffmpeg_exe.parent)
        os.environ["PATH"] = bin_dir + os.pathsep + os.environ.get("PATH", "")


def check_ffmpeg() -> None:
    """
    Verifica se o ffmpeg está disponível no PATH.
    Se não estiver, avisa o usuário e exibe o link de download.
    """
    if _ffmpeg_available():
        return  # Já instalado, nada a fazer

    print()
    print(f"{_BOLD}{_YELLOW}⚠  ffmpeg não encontrado no PATH.{_RESET}")
    print(f"   O bot {_BOLD}não conseguirá reproduzir áudio{_RESET} sem ele.")
    print()
    print(f"   Instale o ffmpeg e certifique-se de que está no PATH:")
    print(f"   {_CYAN}https://ffmpeg.org/download.html{_RESET}")
    print()


def run_setup(*, force: bool = False) -> None:
    """
    Executa o assistente de configuração CLI.

    Parameters
    ----------
    force:
        Se True, executa mesmo que o arquivo já exista.
    """
    if ENV_FILE.exists() and not force:
        # Verifica se o token já está preenchido
        content = ENV_FILE.read_text(encoding="utf-8")
        for line in content.splitlines():
            stripped = line.strip()
            if stripped.startswith("token_discord="):
                value = stripped.split("=", 1)[1].strip()
                if value:
                    return  # Já configurado, nada a fazer

    _print_header()

    if ENV_FILE.exists():
        print(f"{_YELLOW}Arquivo {ENV_FILE.name} encontrado, mas o token do Discord está ausente.{_RESET}")
    else:
        print(f"{_YELLOW}Arquivo {ENV_FILE.name} não encontrado.{_RESET}")

    print("Vamos criar as configurações agora.\n")

    # --- Token Discord (obrigatório) ---
    print(f"{_GREEN}[1/3] Token do Discord{_RESET} {_BOLD}(obrigatório){_RESET}")
    print("  Obtenha em: https://discord.com/developers/applications")
    token_discord = _ask("  Token: ", secret=True, required=True)
    print()

    # --- Proxy (opcional) ---
    print(f"{_GREEN}[2/3] Proxy para yt-dlp{_RESET} {_YELLOW}(opcional — pressione Enter para pular){_RESET}")
    print("  Exemplo: socks5://127.0.0.1:1080")
    ytdlp_proxy = _ask("  Proxy: ", required=False)
    print()

    # --- Spotify (opcional) ---
    print(f"{_GREEN}[3/3] Credenciais do Spotify{_RESET} {_YELLOW}(opcional — necessário para links do Spotify){_RESET}")
    print("  Obtenha em: https://developer.spotify.com/dashboard")
    use_spotify = _ask("  Deseja configurar o Spotify? [s/N]: ", required=False).lower()
    print()

    spotify_client_id = ""
    spotify_client_secret = ""
    if use_spotify in ("s", "sim", "y", "yes"):
        spotify_client_id = _ask("  Client ID: ", required=True)
        spotify_client_secret = _ask("  Client Secret: ", required=True)
        print()

    config = {
        "token_discord": token_discord,
        "ytdlp_proxy": ytdlp_proxy,
        "spotify_client_id": spotify_client_id,
        "spotify_client_secret": spotify_client_secret,
    }

    _write_env(config)

    print(f"{_GREEN}{_BOLD}✔ Configuração salva em: {ENV_FILE}{_RESET}")
    print()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Configuração inicial do bot Discord.")
    parser.add_argument(
        "--force",
        action="store_true",
        help="Reexecuta o setup mesmo que o config.env já exista.",
    )
    args = parser.parse_args()
    run_setup(force=args.force)
