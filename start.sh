#!/usr/bin/env bash
# Genesis — local dev + Cloud Run startup
# Usage: ./start.sh
# Stop:  Ctrl+C

set -e

ROOT="$(cd "$(dirname "$0")" && pwd)"

# Load .env for local dev; on Cloud Run env vars are injected directly
if [ -f "$ROOT/.env" ]; then
  set -a; source "$ROOT/.env"; set +a
fi

PIDS=()
cleanup() {
  echo ""
  echo "Stopping..."
  for pid in "${PIDS[@]}"; do kill "$pid" 2>/dev/null || true; done
  exit 0
}
trap cleanup INT TERM

# 1. Google Tools Server (Docs + Calendar via ADC) — background, no wait
echo "Starting Google Tools Server on :8001..."
uv run uvicorn tools_server.google_tools_server:app --port 8001 --log-level warning \
  > /tmp/genesis-tools.log 2>&1 &
PIDS+=($!)

# 2. MCP Toolbox — background, no wait
echo "Starting MCP Toolbox on :5000..."
toolbox --tools-file "$ROOT/tools_server/tools.yaml" --port 5000 \
  > /tmp/genesis-toolbox.log 2>&1 &
PIDS+=($!)

# 3. Genesis API — starts immediately so Cloud Run sees :8080 bound quickly
#    MCP Toolbox will be ready by the time the first agent request arrives
echo "Starting Genesis API on :8080..."
echo ""
echo "  ADK UI   →  http://localhost:8080"
echo "  API docs →  http://localhost:8080/docs"
echo ""
RELOAD_FLAG=""
[ -f "$ROOT/.env" ] && RELOAD_FLAG="--reload"
uv run uvicorn api.main:app --host 0.0.0.0 --port 8080 $RELOAD_FLAG 2>&1 &
PIDS+=($!)

wait
