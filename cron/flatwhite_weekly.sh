#!/usr/bin/env bash
# Flat White — Weekly Pipeline Cron Wrapper
#
# This script is called by cron to run the full pipeline.
# It activates the virtualenv if present, runs the pipeline,
# and logs output with timestamps.
#
# Install via: flatwhite schedule (prints crontab entry)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

# Create log directory if needed
mkdir -p "$PROJECT_DIR/data/logs"

# Timestamp
echo ""
echo "=========================================="
echo "Flat White Pipeline Run: $(date -u '+%Y-%m-%d %H:%M:%S UTC')"
echo "=========================================="

# Activate virtualenv if it exists
if [ -f "$PROJECT_DIR/.venv/bin/activate" ]; then
    source "$PROJECT_DIR/.venv/bin/activate"
fi

# Change to project directory
cd "$PROJECT_DIR"

# Run the pipeline (steps 1-5: ingest through angles)
# Stops before assembly so the editor can review in Streamlit.
# After review, the editor runs: flatwhite assemble --hook 'text'
python -m flatwhite.cli run

# Notify editor that items are ready for review
python -m flatwhite.cli notify

echo ""
echo "Pipeline complete: $(date -u '+%Y-%m-%d %H:%M:%S UTC')"
echo "=========================================="
