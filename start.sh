#!/usr/bin/env bash
# Genesis — local dev startup
# Usage: ./start.sh
# Stop:  Ctrl+C

set -e

ROOT="$(cd "$(dirname "$0")" && pwd)"

if [ ! -f "$ROOT/.env" ]; then
  echo "ERROR: .env not found. Run: cp .env.example .env and fill in values."
  exit 1
fi

set -a; source "$ROOT/.env"; set +a

PIDS=()
cleanup() {
  echo ""
  echo "Stopping..."
  for pid in "${PIDS[@]}"; do kill "$pid" 2>/dev/null || true; done
  exit 0
}
trap cleanup INT TERM

# 1. Google Tools Server (Docs + Calendar via ADC)
echo "Starting Google Tools Server on :8001..."
uv run uvicorn mcp.google_tools_server:app --port 8001 --log-level warning \
  > /tmp/genesis-tools.log 2>&1 &
PIDS+=($!)

sleep 1

# 2. MCP Toolbox (proxies to Google Tools Server)
echo "Starting MCP Toolbox on :5000..."
toolbox --tools-file "$ROOT/mcp/tools.yaml" --port 5000 \
  > /tmp/genesis-toolbox.log 2>&1 &
PIDS+=($!)

sleep 1

# 3. Genesis API (ADK web UI)
echo "Starting Genesis API on :8080..."
echo ""
echo "  ADK UI   →  http://localhost:8080"
echo "  API docs →  http://localhost:8080/docs"
echo ""
uv run uvicorn api.main:app --host 0.0.0.0 --port 8080 --reload 2>&1 &
PIDS+=($!)

wait
