#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

PYTHON_BIN="${PYTHON_BIN:-python3}"
VENV_DIR=".venv"
VENV_PYTHON="$VENV_DIR/bin/python"

echo "[bootstrap] diretório: $ROOT_DIR"

if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
    echo "[erro] Python não encontrado: $PYTHON_BIN"
    echo "Defina outra versão com: PYTHON_BIN=python3.11 ./bootstrap.sh"
    exit 1
fi

if [ ! -d "$VENV_DIR" ]; then
    echo "[bootstrap] criando ambiente virtual em $VENV_DIR"
    "$PYTHON_BIN" -m venv "$VENV_DIR"
else
    echo "[bootstrap] reutilizando ambiente virtual existente"
fi

echo "[bootstrap] atualizando pip"
"$VENV_PYTHON" -m pip install --upgrade pip

echo "[bootstrap] instalando dependências"
"$VENV_PYTHON" -m pip install -r requirements.txt

echo "[bootstrap] criando diretórios necessários"
mkdir -p cache data logs config

if [ ! -f "config/cookies.txt" ] && [ -f "config/cookies.txt.example" ]; then
    echo "[bootstrap] dica: copie config/cookies.txt.example para config/cookies.txt e cole cookies Netscape válidos, se precisar."
fi

if [ "${SKIP_SETUP:-0}" != "1" ]; then
    echo "[bootstrap] iniciando configuração interativa (config.env)"
    "$VENV_PYTHON" -m src.setup.cli_setup
else
    echo "[bootstrap] setup interativo ignorado (SKIP_SETUP=1)"
fi

echo
echo "[ok] bootstrap concluído."
echo "Próximo passo: .venv/bin/python main.py"
