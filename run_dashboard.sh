#!/bin/bash
# Hyrox Weekly Dashboard launcher.
#
# Starts Streamlit bound to 0.0.0.0 so it's reachable over Tailscale
# from your iPhone (or any other device on your tailnet), and keeps the
# Mac awake while running. Ctrl-C to stop — caffeinate is killed on exit.
#
# Usage:  ./run_dashboard.sh

set -e

cd "$(dirname "$0")"

if [ ! -d "venv" ]; then
  echo "venv/ not found — create it first: python3 -m venv venv && venv/bin/pip install -r requirements.txt"
  exit 1
fi

# Prevent Mac from sleeping while the dashboard is running.
# -d = display, -i = idle, -s = system (won't sleep on AC power)
caffeinate -d -i -s &
CAFFEINATE_PID=$!
trap "echo; echo 'Stopping caffeinate ('$CAFFEINATE_PID')'; kill $CAFFEINATE_PID 2>/dev/null || true" EXIT

# Show the tailnet hostname(s) so it's easy to copy to the phone.
if command -v tailscale >/dev/null 2>&1; then
  HOSTNAME=$(tailscale status --json 2>/dev/null | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('Self',{}).get('DNSName','').rstrip('.'))" 2>/dev/null || echo "")
  if [ -n "$HOSTNAME" ]; then
    echo "=============================================="
    echo "  Open on any device in your tailnet:"
    echo "  http://${HOSTNAME}:8501"
    echo "=============================================="
  fi
else
  echo "(tailscale CLI not found — install Tailscale to get a stable hostname)"
fi

# shellcheck disable=SC1091
source venv/bin/activate

exec streamlit run hyrox_dashboard.py \
  --server.address=0.0.0.0 \
  --server.port=8501 \
  --server.headless=true \
  --browser.gatherUsageStats=false
