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
#   ./run-app.sh --install             # install deps first
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

# -- Install dependencies (--install) --------------------------------
if [[ "$INSTALL" -eq 1 ]]; then
    echo "${YELLOW}[install] pip install -r requirements.txt${RESET}"
    "$PYTHON" -m pip install -r "$ROOT/requirements.txt"
    if [[ -f "$ROOT/api/requirements.txt" ]]; then
        echo "${YELLOW}[install] pip install -r api/requirements.txt${RESET}"
        "$PYTHON" -m pip install -r "$ROOT/api/requirements.txt"
    fi
    echo "${YELLOW}[install] npm install (web)${RESET}"
    ( cd "$WEB_DIR" && npm install )
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
cleanup() {
    echo ""
    echo "${CYAN}Stopping servers...${RESET}"
    for pid in "${PIDS[@]}"; do
        kill "$pid" 2>/dev/null || true
    done
    wait 2>/dev/null || true
}
trap cleanup INT TERM EXIT

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

# Wait for either server to exit; cleanup trap handles the rest.
wait
