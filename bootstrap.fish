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
set LOCK_FILE "logs/bot.lock"
set REQUIREMENTS_STAMP "$VENV_DIR/.requirements.sha256"

function pause_before_close
    # O terminal aberto automaticamente já possui seu próprio `read` no final.
    if test "x$BOOTSTRAP_IN_TERMINAL" != "x1"; and isatty stdin
        echo
        read -l -P "Pressione Enter para fechar..." _
    end
end

function bootstrap_error --argument message code
    if not test -n "$code"
        set code 1
    end
    echo
    echo "[erro] $message"
    pause_before_close
    exit "$code"
end

function bot_running
    set FOUND_PIDS

    # O lock é criado pelo próprio main.py; o PID file, pelo modo em background.
    for PROCESS_FILE in "$LOCK_FILE" "$PID_FILE"
        if not test -f "$PROCESS_FILE"
            continue
        end
        set PROCESS_PID (string trim -- (cat "$PROCESS_FILE" 2>/dev/null))
        if string match -qr '^[0-9]+$' -- "$PROCESS_PID"; and kill -0 "$PROCESS_PID" 2>/dev/null
            if not contains -- "$PROCESS_PID" $FOUND_PIDS
                set -a FOUND_PIDS "$PROCESS_PID"
            end
        end
    end

    if test (count $FOUND_PIDS) -gt 0
        echo $FOUND_PIDS
        return 0
    end

    if command -sq pgrep
        for PROCESS_PID in (pgrep -f '[.]venv/bin/python( -u)? main\.py' 2>/dev/null)
            # Evita confundir outro projeto que também tenha um main.py.
            if test -d "/proc/$PROCESS_PID"
                set PROCESS_ROOT (readlink "/proc/$PROCESS_PID/cwd" 2>/dev/null)
                if test "$PROCESS_ROOT" = "$ROOT_DIR"
                    set -a FOUND_PIDS "$PROCESS_PID"
                end
            end
        end
    end

    if test (count $FOUND_PIDS) -gt 0
        echo $FOUND_PIDS
        return 0
    end
    return 1
end

echo "[bootstrap] diretório: $ROOT_DIR"

if not command -sq "$PYTHON_BIN"
    echo "Defina outra versão com: env PYTHON_BIN=python3.11 ./bootstrap.fish"
    bootstrap_error "Python não encontrado: $PYTHON_BIN"
end

if not test -d "$VENV_DIR"
    echo "[bootstrap] criando ambiente virtual em $VENV_DIR"
    "$PYTHON_BIN" -m venv "$VENV_DIR"
    or bootstrap_error "Não foi possível criar o ambiente virtual."
else
    echo "[bootstrap] reutilizando ambiente virtual existente"
end

if test "x$UPGRADE_PIP" = "x1"
    echo "[bootstrap] atualizando pip (UPGRADE_PIP=1)"
    "$VENV_PYTHON" -m pip install --disable-pip-version-check --upgrade pip
    or bootstrap_error "Falha ao atualizar o pip."
else
    set PIP_VERSION ("$VENV_PYTHON" -m pip --version 2>/dev/null)
    or bootstrap_error "O pip do ambiente virtual não está funcionando."
    echo "[bootstrap] $PIP_VERSION"
end

set REQUIREMENTS_FINGERPRINT ("$VENV_PYTHON" -c 'import hashlib, pathlib, sys; data = pathlib.Path("requirements.txt").read_bytes(); print(f"{sys.version_info.major}.{sys.version_info.minor}:{hashlib.sha256(data).hexdigest()}")')
or bootstrap_error "Não foi possível verificar requirements.txt."

set INSTALLED_FINGERPRINT ""
if test -f "$REQUIREMENTS_STAMP"
    set INSTALLED_FINGERPRINT (string trim -- (cat "$REQUIREMENTS_STAMP"))
end

set INSTALL_DEPENDENCIES 0
if test "x$FORCE_DEPENDENCIES" = "x1"; or test "$INSTALLED_FINGERPRINT" != "$REQUIREMENTS_FINGERPRINT"
    set INSTALL_DEPENDENCIES 1
end

if test "$INSTALL_DEPENDENCIES" -eq 1
    # Em ambientes já preparados, valida tudo sem consultar a internet.
    if test "x$FORCE_DEPENDENCIES" != "x1"; and "$VENV_PYTHON" -m pip install --dry-run --no-index -r requirements.txt >/dev/null 2>&1
        echo "[bootstrap] dependências existentes já satisfazem requirements.txt"
    else
        echo "[bootstrap] instalando dependências"
        "$VENV_PYTHON" -m pip install --disable-pip-version-check --no-input -r requirements.txt
        or bootstrap_error "Falha ao instalar as dependências. Verifique a internet e tente novamente."
    end
    printf '%s\n' "$REQUIREMENTS_FINGERPRINT" > "$REQUIREMENTS_STAMP"
else
    echo "[bootstrap] dependências inalteradas; instalação ignorada"
end

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
    or bootstrap_error "A configuração inicial falhou."
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
            pause_before_close
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
            sleep 2
            if not kill -0 "$BOT_PID" 2>/dev/null
                echo "[bootstrap] últimas linhas de logs/bot.out:"
                tail -n 30 logs/bot.out
                bootstrap_error "O bot encerrou durante a inicialização."
            end
            echo "[bootstrap] bot iniciado em segundo plano (PID: $BOT_PID)."
            echo "[bootstrap] para finalizar: ./stop_bot.fish"
        else
            echo "[bootstrap] iniciando bot..."
            "$VENV_PYTHON" main.py
            set BOT_STATUS $status
            if test "$BOT_STATUS" -ne 0
                bootstrap_error "O bot encerrou com código $BOT_STATUS." "$BOT_STATUS"
            end
            echo "[bootstrap] bot encerrado."
            pause_before_close
        end
    case '*'
        echo "[bootstrap] bot não iniciado."
end
