#!/bin/bash
# Flat White — HF Spaces entrypoint
# Ensures persistent storage is used for the database, then starts the dashboard.

export FLATWHITE_DB_DIR="${FLATWHITE_DB_DIR:-/data}"
mkdir -p "$FLATWHITE_DB_DIR"

echo "Flat White starting — DB at $FLATWHITE_DB_DIR/flatwhite.db"

# Initialise DB if it doesn't exist yet
python -c "from flatwhite.db import init_db; init_db()"

exec python -m uvicorn flatwhite.dashboard.api:app --host 0.0.0.0 --port 7860
