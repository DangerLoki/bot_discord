#!/usr/bin/env fish

set SCRIPT_DIR (cd (dirname (status --current-filename)); pwd)
set ROOT_DIR "$SCRIPT_DIR"
cd "$ROOT_DIR"

set PID_FILE "logs/bot.pid"
set STOPPED 0

function stop_pid --argument pid
    if not test -n "$pid"
        return 1
    end

    if not kill -0 "$pid" 2>/dev/null
        return 1
    end

    echo "[stop] enviando SIGTERM para PID $pid"
    kill -TERM "$pid" 2>/dev/null

    for _ in (seq 1 8)
        if not kill -0 "$pid" 2>/dev/null
            echo "[stop] processo finalizado."
            return 0
        end
        sleep 1
    end

    echo "[stop] SIGTERM não finalizou PID $pid; enviando SIGKILL"
    kill -KILL "$pid" 2>/dev/null

    if not kill -0 "$pid" 2>/dev/null
        echo "[stop] processo encerrado com SIGKILL."
        return 0
    end

    return 1
end

# 1) tenta pelo pid file
if test -f "$PID_FILE"
    set PID (string trim -- (cat "$PID_FILE"))
    if stop_pid "$PID"
        set STOPPED 1
    end
    rm -f "$PID_FILE"
end

# 2) fallback: procura qualquer main.py no diretório atual
if test "$STOPPED" -eq 0
    if command -sq pgrep
        set PIDS (pgrep -f "$ROOT_DIR/.venv/bin/python main.py" 2>/dev/null)
    end

    if test (count $PIDS) -eq 0
        echo "[stop] nenhum processo do bot encontrado."
        exit 0
    end

    for PID in $PIDS
        if stop_pid "$PID"
            set STOPPED 1
        end
    end
end

if test "$STOPPED" -eq 1
    echo "[stop] bot finalizado."
    exit 0
end

echo "[stop] não foi possível finalizar o bot."
exit 1
