#!/bin/bash
# Flat White — one-time setup. Run this after cloning.
set -e

python3 -m venv .venv
source .venv/bin/activate
pip install -e . --quiet
playwright install chromium
python -c "from flatwhite.db import init_db; init_db()"

echo ""
echo "Done! Drop the .env file in this folder, then each week run:"
echo "  source .venv/bin/activate && flatwhite review"
echo "  Then do everything from the dashboard at localhost:8500"
echo ""
