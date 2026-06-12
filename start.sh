#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

# ─── Colors ───
GREEN='\033[0;32m'
CYAN='\033[0;36m'
DIM='\033[2m'
BOLD='\033[1m'
RESET='\033[0m'

# ─── Helpers ───
log()  { echo -e "${GREEN}▸${RESET} $*"; }
info() { echo -e "${CYAN}▸${RESET} $*"; }

port_busy() {
  python3 -c "import socket; s=socket.socket(); s.bind(('127.0.0.1',$1)); s.close()" >/dev/null 2>&1 && return 1 || return 0
}

next_port() {
  local port=$1
  while port_busy "$port"; do
    port=$((port + 1))
  done
  echo "$port"
}

wait_for_port() {
  local port=$1 name=$2 tries=0
  while port_busy "$port"; do
    tries=$((tries + 1))
    if [ "$tries" -gt 30 ]; then
      echo -e "${name} failed to start on :${port}" >&2
      return 1
    fi
    sleep 0.5
  done
}

# ─── Cleanup ───
PIDS=()
cleanup() {
  echo ""
  info "Shutting down..."
  for pid in "${PIDS[@]}"; do
    kill "$pid" 2>/dev/null || true
  done
  wait 2>/dev/null
  log "Stopped."
  exit 0
}
trap cleanup INT TERM

# ─── Ports ───
BACK_PORT=$(next_port 8000)
FRONT_PORT=$(next_port 3000)

echo -e "${BOLD}Family Health Manager${RESET}"
echo ""
log "Backend  → ${DIM}http://localhost:${BACK_PORT}${RESET}"
log "Frontend → ${DIM}http://localhost:${FRONT_PORT}${RESET}"
echo ""

# ─── Backend ───
if [ ! -f backend/.env ]; then
  echo "⚠  Missing backend/.env — copy from .env.example and fill in secrets" >&2
  exit 1
fi

set -a; source backend/.env; set +a

info "Starting backend..."
(cd backend && .venv/bin/python -m uvicorn app.main:app \
  --reload \
  --port "$BACK_PORT" \
  --log-level warning) &
PIDS+=($!)

# ─── Frontend ───
info "Starting frontend..."
(cd frontend && API_URL="http://localhost:${BACK_PORT}" npx vite \
  --port "$FRONT_PORT" \
  --clearScreen false) &
PIDS+=($!)

# ─── Wait ───
echo ""
log "Ready — press ${DIM}Ctrl+C${RESET} to stop"
wait
