#!/usr/bin/env bash
# start.sh — Unix/Mac equivalent of start.bat
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
WORKSPACE="$HERE/workspace"
GATEWAY_DIR="$WORKSPACE/gateway"
LOGS_DIR="$HERE/logs"
GATEWAY_LOG="$LOGS_DIR/gateway.log"

echo ""
echo "================================================================"
echo "  S8-Assignment  START"
echo "================================================================"
echo ""

# ── Key rotation ─────────────────────────────────────────────────────────────
KEY_SLOT=$(grep -i "^GEMINI_KEY_SLOT=" "$HERE/.env" 2>/dev/null | cut -d= -f2 | tr -d '[:space:]' || echo "1")
KEY_SLOT="${KEY_SLOT:-1}"
echo "[start] Using Gemini key slot: $KEY_SLOT"

case "$KEY_SLOT" in
  1) GEMINI_API_KEY=$(grep -i "^GEMINI_API_KEY=" "$HERE/.env" 2>/dev/null | cut -d= -f2) ;;
  2) GEMINI_API_KEY=$(grep -i "^GEMINI_API_KEY_2=" "$HERE/.env" 2>/dev/null | cut -d= -f2) ;;
  3) GEMINI_API_KEY=$(grep -i "^GEMINI_API_KEY_3=" "$HERE/.env" 2>/dev/null | cut -d= -f2) ;;
  4) GEMINI_API_KEY=$(grep -i "^GEMINI_API_KEY_4=" "$HERE/.env" 2>/dev/null | cut -d= -f2) ;;
  5) GEMINI_API_KEY=$(grep -i "^GEMINI_API_KEY_5=" "$HERE/.env" 2>/dev/null | cut -d= -f2) ;;
  *) GEMINI_API_KEY="" ;;
esac
export GEMINI_API_KEY

# ── Setup ─────────────────────────────────────────────────────────────────────
if [ ! -f "$GATEWAY_DIR/main.py" ]; then
    echo "[start] Running first-time setup..."
    python "$HERE/setup.py"
fi

# Copy .env to workspace and inject selected key
cp "$HERE/.env" "$WORKSPACE/.env"
if [ -n "$GEMINI_API_KEY" ]; then
    sed -i.bak "s|^GEMINI_API_KEY=.*|GEMINI_API_KEY=$GEMINI_API_KEY|" "$WORKSPACE/.env"
    rm -f "$WORKSPACE/.env.bak"
    echo "[start] GEMINI_API_KEY set from slot $KEY_SLOT"
else
    echo "[start] WARNING: GEMINI_API_KEY_${KEY_SLOT} is empty in .env"
fi

# ── Ollama check ──────────────────────────────────────────────────────────────
if curl -s http://localhost:11434/api/tags >/dev/null 2>&1; then
    echo "[start] Ollama OK"
else
    echo "[start] WARNING: Ollama not running. Start with: ollama serve"
fi

# ── Kill existing gateway ─────────────────────────────────────────────────────
PID=$(lsof -ti:8108 2>/dev/null || true)
if [ -n "$PID" ]; then
    echo "[start] Killing existing gateway PID $PID"
    kill -9 "$PID" 2>/dev/null || true
fi

# ── Start gateway ─────────────────────────────────────────────────────────────
mkdir -p "$LOGS_DIR"
echo "[start] Starting LLM Gateway V8..."
(cd "$GATEWAY_DIR" && uv run main.py >"$GATEWAY_LOG" 2>&1) &
GATEWAY_PID=$!
echo $GATEWAY_PID > "$HERE/.gateway_pid"

# Wait for gateway
for i in $(seq 1 45); do
    sleep 1
    if curl -s http://localhost:8108/v1/routers >/dev/null 2>&1; then
        echo "[start] Gateway ready at http://localhost:8108 (PID $GATEWAY_PID)"
        break
    fi
    if [ $i -eq 45 ]; then
        echo "ERROR: Gateway did not start within 45s. Check $GATEWAY_LOG"
        exit 1
    fi
    echo "[start] Waiting... ${i}s"
done

echo ""
echo "================================================================"
echo "  Gateway is UP.  Starting query runner..."
echo "================================================================"
echo ""

# ── Run queries ───────────────────────────────────────────────────────────────
PART="${1:-}"
if [ -z "$PART" ]; then
    python "$HERE/run_all.py"
else
    python "$HERE/run_all.py" --part "$PART"
fi

echo ""
echo "================================================================"
echo "  Done. Results in: logs/results/"
echo "================================================================"
