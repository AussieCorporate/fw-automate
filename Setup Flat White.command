#!/bin/bash
# Double-click this to set up Flat White (first time only).
cd "$(dirname "$0")"
set -e

echo ""
echo "  Setting up Flat White..."
echo ""

# Require Python 3.11+ (macOS /usr/bin/python3 is 3.9 — must use framework Python)
PYTHON3=$(command -v python3.12 || command -v python3.11 || echo "")
if [ -z "$PYTHON3" ]; then
    # Fallback: check if default python3 is new enough
    PY_MINOR=$( python3 -c "import sys; print(sys.version_info.minor)" 2>/dev/null || echo "0" )
    PY_MAJOR=$( python3 -c "import sys; print(sys.version_info.major)" 2>/dev/null || echo "0" )
    if [ "$PY_MAJOR" -lt 3 ] || [ "$PY_MINOR" -lt 11 ]; then
        echo "  Python 3.11+ required. Installing via Homebrew..."
        /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
        brew install python@3.12
        PYTHON3=$(command -v python3.12)
    else
        PYTHON3=$(command -v python3)
    fi
fi

echo "  Using $PYTHON3 ($("$PYTHON3" --version))"
"$PYTHON3" -m venv .venv
.venv/bin/pip install -e . --quiet
.venv/bin/playwright install chromium
.venv/bin/python -c "from flatwhite.db import init_db; init_db()"

chmod +x "Start Flat White.command"

echo ""
echo "  Done! Now double-click 'Start Flat White' each week."
echo "  Press any key to close."
read -n 1
