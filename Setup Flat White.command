#!/bin/bash
# Double-click this to set up Flat White (first time only).
cd "$(dirname "$0")"
set -e

echo ""
echo "  Setting up Flat White..."
echo ""

# Install Python if missing
if ! command -v python3 &>/dev/null; then
    echo "  Installing Python via Homebrew..."
    /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
    brew install python@3.11
fi

python3 -m venv .venv
source .venv/bin/activate
pip install -e . --quiet
playwright install chromium
python -c "from flatwhite.db import init_db; init_db()"

chmod +x "Start Flat White.command"

echo ""
echo "  Done! Now double-click 'Start Flat White' each week."
echo "  Press any key to close."
read -n 1
