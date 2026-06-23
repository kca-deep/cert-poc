#!/usr/bin/env bash
#
# Launch the cert-poc development servers (macOS / bash).
#
# Run this from the repository root. It starts two servers:
#   - FastAPI backend  : python -m uvicorn api.main:app  (default :8000, --reload)
#   - Next.js frontend : npm run dev                      (default :3000)
#
# web/.env.local NEXT_PUBLIC_API_BASE must match the backend port so the
# frontend connects to the real server (otherwise it runs in mock mode).
#
# Usage:
#   ./run-app.sh                       # start both servers (Ctrl+C stops both)
#   ./run-app.sh --install             # create .venv + install deps first
#   ./run-app.sh --api-port 8001 --web-port 3001
#   ./run-app.sh --no-reload           # disable uvicorn auto-reload
#

set -euo pipefail

# -- Defaults --------------------------------------------------------
API_PORT=8000
WEB_PORT=3000
INSTALL=0
NO_RELOAD=0

# -- Parse arguments -------------------------------------------------
while [[ $# -gt 0 ]]; do
    case "$1" in
        --api-port)  API_PORT="$2"; shift 2 ;;
        --web-port)  WEB_PORT="$2"; shift 2 ;;
        --install)   INSTALL=1; shift ;;
        --no-reload) NO_RELOAD=1; shift ;;
        -h|--help)
            grep '^#' "$0" | sed 's/^# \{0,1\}//'
            exit 0 ;;
        *)
            echo "[error] Unknown option: $1" >&2
            exit 1 ;;
    esac
done

# -- Pin paths to the script location (repo root) --------------------
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WEB_DIR="$ROOT/web"

# Colors (fall back to plain if not a TTY)
if [[ -t 1 ]]; then
    CYAN=$'\033[36m'; GREEN=$'\033[32m'; YELLOW=$'\033[33m'; RED=$'\033[31m'; GRAY=$'\033[90m'; RESET=$'\033[0m'
else
    CYAN=''; GREEN=''; YELLOW=''; RED=''; GRAY=''; RESET=''
fi

echo "${CYAN}cert-poc dev -- root: $ROOT${RESET}"

# -- Pre-flight checks -----------------------------------------------
if [[ ! -f "$ROOT/api/main.py" ]]; then
    echo "[error] Cannot find api/main.py. Run this from the repository root." >&2
    exit 1
fi
if [[ ! -f "$WEB_DIR/package.json" ]]; then
    echo "[error] Cannot find web/package.json." >&2
    exit 1
fi

# Prefer python3, fall back to python
if command -v python3 >/dev/null 2>&1; then
    PYTHON=python3
elif command -v python >/dev/null 2>&1; then
    PYTHON=python
else
    echo "[error] python not found on PATH." >&2
    exit 1
fi
if ! command -v npm >/dev/null 2>&1; then
    echo "[error] npm not found on PATH." >&2
    exit 1
fi

VENV_DIR="$ROOT/.venv"
VENV_PY="$VENV_DIR/bin/python"

ensure_venv() {
    if [[ -x "$VENV_PY" ]]; then
        return
    fi
    echo "${YELLOW}[setup] python -m venv .venv${RESET}"
    "$PYTHON" -m venv "$VENV_DIR"
}

# -- Install dependencies (--install) --------------------------------
if [[ "$INSTALL" -eq 1 ]]; then
    ensure_venv
    echo "${YELLOW}[install] pip install -r requirements.txt${RESET}"
    "$VENV_PY" -m pip install -r "$ROOT/requirements.txt"
    if [[ -f "$ROOT/api/requirements.txt" ]]; then
        echo "${YELLOW}[install] pip install -r api/requirements.txt${RESET}"
        "$VENV_PY" -m pip install -r "$ROOT/api/requirements.txt"
    fi
    echo "${YELLOW}[install] npm install (web)${RESET}"
    ( cd "$WEB_DIR" && npm install )
fi

if [[ -x "$VENV_PY" ]]; then
    PYTHON="$VENV_PY"
fi

require_python_module() {
    local module="$1"
    local install_hint="$2"
    if ! "$PYTHON" -c "import ${module}" >/dev/null 2>&1; then
        echo "${RED}[error] Python module '${module}' is missing in: $PYTHON${RESET}" >&2
        echo "        Run: ./run-app.sh --install" >&2
        echo "        Missing package group: $install_hint" >&2
        exit 1
    fi
}

require_python_module "uvicorn" "api/requirements.txt"

if ! ( cd "$ROOT" && "$PYTHON" -c "import api.main" ) >/dev/null 2>&1; then
    echo "${RED}[error] FastAPI app cannot be imported with: $PYTHON${RESET}" >&2
    echo "        Run: ./run-app.sh --install" >&2
    echo "        If it still fails, run this for the detailed error:" >&2
    echo "        cd \"$ROOT\" && \"$PYTHON\" -c 'import api.main'" >&2
    exit 1
fi

if [[ ! -x "$WEB_DIR/node_modules/.bin/next" ]]; then
    echo "${RED}[error] Next.js dependencies are missing in web/node_modules.${RESET}" >&2
    echo "        Run: ./run-app.sh --install" >&2
    exit 1
fi

# -- Port-in-use check (warning only) --------------------------------
port_in_use() {
    lsof -nP -iTCP:"$1" -sTCP:LISTEN >/dev/null 2>&1
}
for p in "$API_PORT" "$WEB_PORT"; do
    if port_in_use "$p"; then
        echo "${RED}[warn] Port $p is already in use. Use --api-port/--web-port to change it if it conflicts.${RESET}"
    fi
done

# -- Build launch commands -------------------------------------------
RELOAD_ARG="--reload"
if [[ "$NO_RELOAD" -eq 1 ]]; then
    RELOAD_ARG=""
fi

echo ""
echo "${GREEN}[backend]  $PYTHON -m uvicorn api.main:app --port $API_PORT $RELOAD_ARG   (cwd: $ROOT)${RESET}"
echo "${GREEN}[frontend] npm run dev -- --port $WEB_PORT  (cwd: $WEB_DIR)${RESET}"
echo ""

# -- Launch both servers; Ctrl+C stops both --------------------------
PIDS=()
CLEANED=0
cleanup() {
    # Guard against double-invocation (e.g. INT trap then EXIT trap).
    [[ "$CLEANED" -eq 1 ]] && return 0
    CLEANED=1
    echo ""
    echo "${CYAN}Stopping servers...${RESET}"
    for pid in "${PIDS[@]}"; do
        kill "$pid" 2>/dev/null || true
    done
    wait 2>/dev/null || true
}
# Single cleanup path: INT/TERM just exit, the EXIT trap does the teardown once.
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

(
    cd "$ROOT"
    exec "$PYTHON" -m uvicorn api.main:app --port "$API_PORT" $RELOAD_ARG
) &
PIDS+=($!)

(
    cd "$WEB_DIR"
    exec npm run dev -- --port "$WEB_PORT"
) &
PIDS+=($!)

echo "${CYAN}Both servers launched.${RESET}"
echo "  - API : http://localhost:$API_PORT  (health: /health, docs: /docs)"
echo "  - WEB : http://localhost:$WEB_PORT  (-> /sessions)"
echo "${GRAY}Press Ctrl+C to stop both.${RESET}"

# Bash 3.2 on macOS has no `wait -n`; poll liveness with `kill -0` so one
# failed server tears down the other instead of leaving a half-running app.
# (Don't use `jobs`/`wait $pid` here: the cleanup trap's bare `wait` reaps the
#  jobs, after which `wait $pid` reports "not a child" and a bogus status 127.)
status=0
while true; do
    for pid in "${PIDS[@]}"; do
        if ! kill -0 "$pid" 2>/dev/null; then
            # Reap the real exit status before the EXIT trap's bare `wait` runs.
            if wait "$pid" 2>/dev/null; then status=0; else status=$?; fi
            if [[ "$status" -ne 0 ]]; then
                echo "" >&2
                echo "${RED}[error] A server (pid=$pid) exited with status $status. Stopping the other...${RESET}" >&2
            else
                echo "${CYAN}A server (pid=$pid) exited. Stopping the other...${RESET}"
            fi
            exit "$status"   # EXIT trap runs cleanup to stop the survivor
        fi
    done
    sleep 1
done
