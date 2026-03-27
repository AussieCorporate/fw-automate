#!/bin/bash
# Double-click this file to launch the Flat White dashboard.
cd "$(dirname "$0")"

# Always use the venv Python explicitly — avoids macOS system Python 3.9 on /usr/bin/python3
PYTHON=".venv/bin/python"
if ! "$PYTHON" --version &>/dev/null; then
    echo "  ERROR: .venv not found. Run Setup Flat White first."
    read -n 1
    exit 1
fi
echo "  Python: $("$PYTHON" --version)"

# Start server in background, wait for it to accept connections, then open browser
"$PYTHON" -m uvicorn flatwhite.dashboard.api:app --host 0.0.0.0 --port 8500 &
SERVER_PID=$!

echo "  Starting Flat White..."
for i in $(seq 1 20); do
    sleep 1
    if curl -s http://localhost:8500 > /dev/null 2>&1; then
        break
    fi
done

open "http://localhost:8500"

# Keep terminal open (server blocks here)
wait $SERVER_PID
