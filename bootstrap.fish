#!/usr/bin/env fish

set SCRIPT_PATH (realpath (status --current-filename))
set ROOT_DIR (cd (dirname "$SCRIPT_PATH"); pwd)

# Quando executado por clique (sem TTY), tenta abrir um terminal automaticamente.
if not isatty stdout; and test "x$BOOTSTRAP_IN_TERMINAL" != "x1"
    set LAUNCH_CMD "cd '$ROOT_DIR'; env RUN_BOT=1 BOOTSTRAP_IN_TERMINAL=1 '$SCRIPT_PATH'; echo; read -P 'Pressione Enter para fechar...' _"

    if command -sq gnome-terminal
        gnome-terminal -- fish -lc "$LAUNCH_CMD"
        exit $status
    else if command -sq konsole
        konsole -e fish -lc "$LAUNCH_CMD"
        exit $status
    else if command -sq xfce4-terminal
        xfce4-terminal --command="fish -lc \"$LAUNCH_CMD\""
        exit $status
    else if command -sq kitty
        kitty fish -lc "$LAUNCH_CMD"
        exit $status
    else if command -sq alacritty
        alacritty -e fish -lc "$LAUNCH_CMD"
        exit $status
    else if command -sq xterm
        xterm -e fish -lc "$LAUNCH_CMD"
        exit $status
    else
        echo "[erro] Nenhum terminal suportado encontrado (gnome-terminal, konsole, xfce4-terminal, kitty, alacritty, xterm)."
        echo "Execute manualmente no terminal: ./bootstrap.fish"
        exit 1
    end
end

cd "$ROOT_DIR"

if not set -q PYTHON_BIN
    set PYTHON_BIN "python3"
end

set VENV_DIR ".venv"
set VENV_PYTHON "$VENV_DIR/bin/python"
set PID_FILE "logs/bot.pid"

function bot_running
    if command -sq pgrep
        set PIDS (pgrep -f "$ROOT_DIR/.venv/bin/python main.py" 2>/dev/null)
        if test (count $PIDS) -gt 0
            echo $PIDS
            return 0
        end
    end
    return 1
end

echo "[bootstrap] diretório: $ROOT_DIR"

if not command -sq "$PYTHON_BIN"
    echo "[erro] Python não encontrado: $PYTHON_BIN"
    echo "Defina outra versão com: env PYTHON_BIN=python3.11 ./bootstrap.fish"
    exit 1
end

if not test -d "$VENV_DIR"
    echo "[bootstrap] criando ambiente virtual em $VENV_DIR"
    "$PYTHON_BIN" -m venv "$VENV_DIR"
else
    echo "[bootstrap] reutilizando ambiente virtual existente"
end

echo "[bootstrap] atualizando pip"
"$VENV_PYTHON" -m pip install --upgrade pip

echo "[bootstrap] instalando dependências"
"$VENV_PYTHON" -m pip install -r requirements.txt

echo "[bootstrap] criando diretórios necessários"
mkdir -p cache data logs config

if not test -f config/cookies.txt
    if test -f config/cookies.txt.example
        echo "[bootstrap] dica: copie config/cookies.txt.example para config/cookies.txt e cole cookies Netscape válidos, se precisar."
    end
end

if test "x$SKIP_SETUP" != "x1"
    echo "[bootstrap] iniciando configuração interativa (config.env)"
    "$VENV_PYTHON" -m src.setup.cli_setup
else
    echo "[bootstrap] setup interativo ignorado (SKIP_SETUP=1)"
end

echo
echo "[ok] bootstrap concluído."
echo "Próximo passo: .venv/bin/python main.py"

set START_BOT ""
if set -q RUN_BOT
    set START_BOT "$RUN_BOT"
else
    read -l -P "Deseja iniciar o bot agora neste terminal? [S/n]: " START_BOT
end

switch (string lower -- (string trim -- "$START_BOT"))
    case "" "s" "sim" "y" "yes" "1" "true"
        if set RUNNING_PIDS (bot_running)
            echo "[bootstrap] bot já está em execução (PID(s): $RUNNING_PIDS)."
            echo "[bootstrap] finalize com: ./stop_bot.fish"
            exit 0
        end

        if test "x$RUN_BOT_BG" = "x1"
            if test -f "$PID_FILE"
                set EXISTING_PID (string trim -- (cat "$PID_FILE"))
                if test -n "$EXISTING_PID"; and kill -0 "$EXISTING_PID" 2>/dev/null
                    echo "[bootstrap] bot já está rodando em segundo plano (PID: $EXISTING_PID)."
                    exit 0
                end
            end

            echo "[bootstrap] iniciando bot em segundo plano..."
            nohup "$VENV_PYTHON" main.py >> logs/bot.out 2>&1 &
            set BOT_PID $last_pid
            echo "$BOT_PID" > "$PID_FILE"
            echo "[bootstrap] bot iniciado em segundo plano (PID: $BOT_PID)."
            echo "[bootstrap] para finalizar: ./stop_bot.fish"
        else
            echo "[bootstrap] iniciando bot..."
            exec "$VENV_PYTHON" main.py
        end
    case '*'
        echo "[bootstrap] bot não iniciado."
end
