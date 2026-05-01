#!/usr/bin/env bash
set -e
cd "$(dirname "$0")"

# --- helper: check if a port is available ---
port_busy() {
  python3 -c "import socket; s=socket.socket(); s.bind(('127.0.0.1',$1)); s.close()" >/dev/null 2>&1 && return 1 || return 0
}

# --- helper: find next available port starting from $1 ---
next_port() {
  local port=$1
  while port_busy "$port"; do
    port=$((port + 1))
  done
  echo "$port"
}

BACK_PORT=$(next_port 8000)
FRONT_PORT=$(next_port 3000)

echo "Backend  → http://localhost:${BACK_PORT}"
echo "Frontend → http://localhost:${FRONT_PORT}"
echo ""

# Source backend .env to ensure API keys are current (overrides stale shell env vars)
set -a; source backend/.env; set +a

# Backend
(cd backend && .venv/bin/python -m uvicorn app.main:app --reload --port "$BACK_PORT") &
BACK_PID=$!

# Frontend — API_URL env var is read by vite.config.ts to set the proxy target
(cd frontend && API_URL="http://localhost:${BACK_PORT}" npx vite --port "$FRONT_PORT") &
FRONT_PID=$!

echo "Backend PID: $BACK_PID  |  Frontend PID: $FRONT_PID"
echo "Press Ctrl+C to stop both"

wait
