#!/usr/bin/env bash
# ============================================================================
#  Frisk — one-command setup
#
#    ./setup.sh              install everything, generate data, run tests
#    ./setup.sh --run        ...and start the server when finished
#
#  Works on macOS / Linux / Git Bash on Windows. Python 3.11+ required.
# ============================================================================
set -euo pipefail

cyan() { printf "\033[36m%s\033[0m\n" "$1"; }
green(){ printf "\033[32m%s\033[0m\n" "$1"; }
warn() { printf "\033[33m%s\033[0m\n" "$1"; }
die()  { printf "\033[31m%s\033[0m\n" "$1" >&2; exit 1; }

cyan "──────────────────────────────────────────────"
cyan " Frisk — Financial Risk Signal Aggregator"
cyan "──────────────────────────────────────────────"

# ---- 1. Python version -----------------------------------------------------
PY="${PYTHON:-python3}"
command -v "$PY" >/dev/null 2>&1 || PY=python
command -v "$PY" >/dev/null 2>&1 || die "Python not found. Install Python 3.11+ and retry."

"$PY" - <<'EOF' || die "Python 3.11+ is required."
import sys
raise SystemExit(0 if sys.version_info >= (3, 11) else 1)
EOF
green "✓ $("$PY" --version)"

# ---- 2. Virtual environment ------------------------------------------------
if [ ! -d .venv ]; then
  cyan "→ creating virtual environment (.venv)"
  "$PY" -m venv .venv
fi
# venv layout differs between Windows (Scripts) and POSIX (bin)
if   [ -f .venv/bin/python ];        then VPY=.venv/bin/python
elif [ -f .venv/Scripts/python.exe ]; then VPY=.venv/Scripts/python.exe
else die "Could not locate the virtualenv interpreter."; fi
green "✓ virtualenv ready"

# ---- 3. Dependencies -------------------------------------------------------
cyan "→ installing dependencies (this takes a minute)"
"$VPY" -m pip install --quiet --upgrade pip
"$VPY" -m pip install --quiet -e ".[llm,api,dev]"
green "✓ dependencies installed"

# ---- 4. API key ------------------------------------------------------------
if [ ! -f .env ]; then
  cat > .env <<'ENVEOF'
# Add your OpenRouter key to score with a real LLM (https://openrouter.ai/keys).
# Leave blank to run entirely on the deterministic mock provider — the whole app
# still works end-to-end, just with reproducible mock scores instead of live ones.
OPENROUTER_API_KEY=
ENVEOF
  warn "! created .env — add OPENROUTER_API_KEY for live scoring (optional)"
else
  green "✓ .env present"
fi

# ---- 5. Data + database ----------------------------------------------------
cyan "→ generating synthetic customers + database"
"$VPY" -m frisk.cli generate  >/dev/null
"$VPY" -m frisk.cli samples   >/dev/null
"$VPY" -m frisk.cli migrate   >/dev/null
green "✓ 20 customers + 40 upload samples + database ready"

# ---- 6. Redis (optional) ---------------------------------------------------
if command -v docker >/dev/null 2>&1; then
  if ! docker ps --format '{{.Names}}' 2>/dev/null | grep -q '^frisk-redis$'; then
    cyan "→ starting Redis (review queue + agent scratchpad)"
    docker run -d --name frisk-redis -p 6379:6379 redis:7-alpine >/dev/null 2>&1 \
      || docker start frisk-redis >/dev/null 2>&1 \
      || warn "! could not start Redis — falling back to in-memory (app still works)"
  fi
  green "✓ Redis running"
else
  warn "! Docker not found — using the in-memory fallback (app still works)"
fi

# ---- 7. Verify -------------------------------------------------------------
cyan "→ running test suite"
FRISK_PROVIDER=mock "$VPY" -m pytest -q || die "Tests failed — setup is not clean."
green "✓ all tests pass"

echo
green "──────────────────────────────────────────────"
green " Setup complete."
green "──────────────────────────────────────────────"
echo
echo "  Start the app:      $VPY -m frisk.cli serve      → http://127.0.0.1:8000"
echo "  Score offline:      $VPY -m frisk.cli score --offline"
echo "  Re-run tests:       FRISK_PROVIDER=mock $VPY -m pytest -q"
echo
echo "  First dashboard load scores all 20 customers live (~1-2 min, shown as a"
echo "  progress bar). With no API key it uses the mock provider and is instant."
echo

if [ "${1:-}" = "--run" ]; then
  cyan "→ starting server"
  exec "$VPY" -m frisk.cli serve
fi
