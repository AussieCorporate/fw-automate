#!/usr/bin/env bash
# ============================================================
# Flat White — Remote Server Setup
# Runs ON the GCP VM (called automatically by gcp_deploy.sh).
# Safe to re-run — all steps are idempotent.
# ============================================================

set -euo pipefail

PROJECT_DIR="$HOME/flatwhite"
VENV="$PROJECT_DIR/.venv"
DASHBOARD_PORT="8500"
USERNAME="$(whoami)"

log()  { echo ""; echo "  ▶ $*"; }
ok()   { echo "    ✓ $*"; }

# ── System packages ───────────────────────────────────────────────────────────
log "Installing system packages"
sudo apt-get update -qq
sudo apt-get install -y -qq python3.11 python3.11-venv python3-pip
ok "Python 3.11 ready"

# ── Python virtualenv ─────────────────────────────────────────────────────────
log "Setting up Python virtualenv"
if [ ! -d "$VENV" ]; then
    python3.11 -m venv "$VENV"
    ok "Virtualenv created"
else
    ok "Virtualenv already exists"
fi

source "$VENV/bin/activate"
pip install --quiet --upgrade pip
pip install --quiet -e "$PROJECT_DIR"
ok "Dependencies installed"

# ── Database ──────────────────────────────────────────────────────────────────
log "Initialising database"
mkdir -p "$PROJECT_DIR/data/logs"
python -m flatwhite.cli init
ok "Database initialised"

# ── Cron job ──────────────────────────────────────────────────────────────────
log "Installing cron job"
chmod +x "$PROJECT_DIR/cron/flatwhite_weekly.sh"

CRON_ENTRY="0 20 * * 2 $PROJECT_DIR/cron/flatwhite_weekly.sh >> $PROJECT_DIR/data/logs/cron.log 2>&1"
CRON_MARKER="flatwhite_weekly"

# Only add if not already present
if ! crontab -l 2>/dev/null | grep -q "$CRON_MARKER"; then
    (crontab -l 2>/dev/null; echo "$CRON_ENTRY") | crontab -
    ok "Cron job installed (Wed 20:00 UTC = Thu 06:00 AEST)"
else
    # Update existing entry
    (crontab -l 2>/dev/null | grep -v "$CRON_MARKER"; echo "$CRON_ENTRY") | crontab -
    ok "Cron job updated"
fi

# ── Systemd service for dashboard ────────────────────────────────────────────
log "Installing systemd service (flatwhite-dashboard)"

sudo tee /etc/systemd/system/flatwhite-dashboard.service > /dev/null <<EOF
[Unit]
Description=Flat White Editor Dashboard
After=network.target

[Service]
Type=simple
User=${USERNAME}
WorkingDirectory=${PROJECT_DIR}
ExecStart=${VENV}/bin/python -m uvicorn flatwhite.dashboard.api:app --host 0.0.0.0 --port ${DASHBOARD_PORT}
Restart=on-failure
RestartSec=10
Environment=PATH=${VENV}/bin:/usr/local/bin:/usr/bin:/bin

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable flatwhite-dashboard --quiet
sudo systemctl restart flatwhite-dashboard
ok "Dashboard service started"

# ── Verify dashboard is up ────────────────────────────────────────────────────
log "Checking dashboard is responding"
sleep 3
if curl -sf "http://localhost:${DASHBOARD_PORT}/" > /dev/null; then
    ok "Dashboard is up on port ${DASHBOARD_PORT}"
else
    echo "    ⚠ Dashboard did not respond — check: sudo systemctl status flatwhite-dashboard"
fi

# ── Done ──────────────────────────────────────────────────────────────────────
echo ""
echo "    Remote setup complete."
