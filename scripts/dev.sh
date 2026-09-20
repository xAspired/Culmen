#!/usr/bin/env bash
#
# Culmen development stack, one command.
#
#   ./scripts/dev.sh
#
# Starts the API on :8000 and the UI on :5173, and stops both on Ctrl-C.
# Everything runs offline: no network access is needed at any point.

set -euo pipefail

cd "$(dirname "$0")/.."
ROOT="$PWD"

log() { printf '\033[1;36m[culmen]\033[0m %s\n' "$*"; }
die() { printf '\033[1;31m[culmen]\033[0m %s\n' "$*" >&2; exit 1; }

command -v python3 >/dev/null || die "python3 not found"
command -v node >/dev/null || die "node not found — install Node 20 or newer"

# --- Python -----------------------------------------------------------------
if [ ! -d .venv ]; then
  log "creating .venv"
  python3 -m venv .venv
fi
# shellcheck disable=SC1091
source .venv/bin/activate

if ! python -c "import fastapi, skyfield" 2>/dev/null; then
  log "installing Python dependencies"
  pip install --quiet --upgrade pip
  pip install --quiet -e ".[dev]"
fi

# --- frontend ---------------------------------------------------------------
if [ ! -d frontend/node_modules ]; then
  log "installing frontend dependencies"
  (cd frontend && npm install --no-audit --no-fund --silent)
fi

# --- run both ---------------------------------------------------------------
pids=()
cleanup() {
  log "stopping"
  for pid in "${pids[@]:-}"; do
    kill "$pid" 2>/dev/null || true
  done
  wait 2>/dev/null || true
}
trap cleanup EXIT INT TERM

log "API   → http://localhost:8000/docs"
python -m uvicorn backend.app.main:app --reload --port 8000 &
pids+=($!)

# Wait for the API before starting the UI, so the first page load is not a
# wall of proxy errors.
for _ in $(seq 1 40); do
  if curl -fsS http://localhost:8000/health >/dev/null 2>&1; then break; fi
  sleep 0.25
done
curl -fsS http://localhost:8000/health >/dev/null 2>&1 \
  || die "the API did not start — see the output above"

loaded=$(curl -fsS http://localhost:8000/health)
log "loaded: $loaded"

log "UI    → http://localhost:5173"
(cd "$ROOT/frontend" && npm run dev --silent) &
pids+=($!)

log "ready. Ctrl-C stops both."
wait
