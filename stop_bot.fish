#!/usr/bin/env fish

set SCRIPT_DIR (cd (dirname (status --current-filename)); pwd)
set ROOT_DIR "$SCRIPT_DIR"
cd "$ROOT_DIR"

set PID_FILE "logs/bot.pid"
set LOCK_FILE "logs/bot.lock"
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

    for ATTEMPT in (seq 1 8)
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

# 1) tenta pelos arquivos mantidos pelo bootstrap e pelo próprio main.py
for PROCESS_FILE in "$PID_FILE" "$LOCK_FILE"
    if test -f "$PROCESS_FILE"
        set PID (string trim -- (cat "$PROCESS_FILE"))
        if stop_pid "$PID"
            set STOPPED 1
        end
        rm -f "$PROCESS_FILE"
    end
end

# 2) fallback: procura qualquer main.py no diretório atual
if test "$STOPPED" -eq 0
    if command -sq pgrep
        set CANDIDATE_PIDS (pgrep -f '[.]venv/bin/python( -u)? main\.py' 2>/dev/null)
        set PIDS
        for PID in $CANDIDATE_PIDS
            if test -d "/proc/$PID"
                set PROCESS_ROOT (readlink "/proc/$PID/cwd" 2>/dev/null)
                if test "$PROCESS_ROOT" = "$ROOT_DIR"
                    set -a PIDS "$PID"
                end
            end
        end
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
