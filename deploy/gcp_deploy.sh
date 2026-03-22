#!/usr/bin/env bash
# ============================================================
# Flat White — GCP Deployment Script
# Run this once from your Mac to provision and configure
# everything on a new Google Cloud e2-micro (always-free) VM.
#
# Usage:
#   cd "/Users/TAC/Desktop/AntiGravity/FW Automate/flatwhite"
#   bash deploy/gcp_deploy.sh
#
# Prerequisites:
#   - gcloud CLI installed (brew install google-cloud-sdk)
#   - gcloud auth login already run
#   - .env file filled in (GEMINI_API_KEY + NOTIFY_SMTP_* settings)
# ============================================================

set -euo pipefail

# ── Point gcloud at Python 3.11 (system Python 3.9 crashes gcloud) ───────────
SCRIPT_DIR_EARLY="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR_EARLY="$(dirname "$SCRIPT_DIR_EARLY")"
if [ -f "$PROJECT_DIR_EARLY/.venv/bin/python3.11" ]; then
    export CLOUDSDK_PYTHON="$PROJECT_DIR_EARLY/.venv/bin/python3.11"
fi

# ── Configuration ─────────────────────────────────────────────────────────────
# Edit these if you want a different project/region/name.
INSTANCE_NAME="flatwhite"
ZONE="us-central1-a"
REGION="us-central1"
MACHINE_TYPE="e2-micro"
IMAGE_FAMILY="ubuntu-2204-lts"
IMAGE_PROJECT="ubuntu-os-cloud"
DISK_SIZE="30GB"
DASHBOARD_PORT="8500"
FIREWALL_RULE_NAME="flatwhite-dashboard"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

# ── Helpers ────────────────────────────────────────────────────────────────────
log()  { echo ""; echo "▶ $*"; }
ok()   { echo "  ✓ $*"; }
warn() { echo "  ⚠ $*"; }

# ── Ensure gcloud is on PATH ──────────────────────────────────────────────────
if ! command -v gcloud &>/dev/null; then
    set +u
    if [ -f "$HOME/google-cloud-sdk/path.bash.inc" ]; then
        source "$HOME/google-cloud-sdk/path.bash.inc"
    fi
    set -u
fi

# ── Preflight checks ──────────────────────────────────────────────────────────
log "Preflight checks"

if ! command -v gcloud &>/dev/null; then
    echo ""
    echo "ERROR: gcloud CLI not found."
    echo "Install it with: brew install google-cloud-sdk"
    echo "Then run: gcloud auth login"
    exit 1
fi
ok "gcloud found"

# Resolve project
GCP_PROJECT="$(gcloud config get-value project 2>/dev/null || true)"
if [ -z "$GCP_PROJECT" ]; then
    echo ""
    echo "ERROR: No GCP project set. Run: gcloud config set project YOUR_PROJECT_ID"
    exit 1
fi
ok "GCP project: $GCP_PROJECT"

# Check .env exists and has Gemini key
if [ ! -f "$PROJECT_DIR/.env" ]; then
    echo ""
    echo "ERROR: .env not found at $PROJECT_DIR/.env"
    echo "Copy .env.example and fill in your keys first."
    exit 1
fi
if ! grep -q "^GEMINI_API_KEY=." "$PROJECT_DIR/.env"; then
    warn "GEMINI_API_KEY looks empty in .env — pipeline LLM calls will fail"
fi
if ! grep -q "^NOTIFY_SMTP_HOST=." "$PROJECT_DIR/.env"; then
    warn "NOTIFY_SMTP_HOST not set in .env — email notifications will be skipped"
fi
ok ".env found"

# ── Create VM ─────────────────────────────────────────────────────────────────
log "Creating VM: $INSTANCE_NAME ($MACHINE_TYPE in $ZONE)"

if gcloud compute instances describe "$INSTANCE_NAME" --zone="$ZONE" &>/dev/null; then
    ok "VM already exists — skipping creation"
else
    gcloud compute instances create "$INSTANCE_NAME" \
        --zone="$ZONE" \
        --machine-type="$MACHINE_TYPE" \
        --image-family="$IMAGE_FAMILY" \
        --image-project="$IMAGE_PROJECT" \
        --boot-disk-size="$DISK_SIZE" \
        --boot-disk-type="pd-standard" \
        --tags="flatwhite-dashboard" \
        --metadata="enable-oslogin=TRUE" \
        --quiet
    ok "VM created"
fi

# ── Get external IP ───────────────────────────────────────────────────────────
log "Resolving external IP"
EXTERNAL_IP="$(gcloud compute instances describe "$INSTANCE_NAME" \
    --zone="$ZONE" \
    --format="get(networkInterfaces[0].accessConfigs[0].natIP)")"
ok "External IP: $EXTERNAL_IP"

# ── Open firewall for dashboard ───────────────────────────────────────────────
log "Configuring firewall rule: $FIREWALL_RULE_NAME"

if gcloud compute firewall-rules describe "$FIREWALL_RULE_NAME" &>/dev/null; then
    ok "Firewall rule already exists — skipping"
else
    gcloud compute firewall-rules create "$FIREWALL_RULE_NAME" \
        --direction=INGRESS \
        --priority=1000 \
        --network=default \
        --action=ALLOW \
        --rules="tcp:$DASHBOARD_PORT" \
        --source-ranges="0.0.0.0/0" \
        --target-tags="flatwhite-dashboard" \
        --quiet
    ok "Firewall rule created (port $DASHBOARD_PORT open)"
fi

# ── Wait for SSH to be ready ──────────────────────────────────────────────────
log "Waiting for SSH to be ready (up to 90s)"
for i in $(seq 1 18); do
    if gcloud compute ssh "$INSTANCE_NAME" --zone="$ZONE" \
        --command="echo ready" --quiet 2>/dev/null; then
        ok "SSH ready"
        break
    fi
    if [ "$i" -eq 18 ]; then
        echo "ERROR: SSH not ready after 90s. Check the GCP console."
        exit 1
    fi
    echo "  ... waiting (${i}/18)"
    sleep 5
done

# ── Patch .env with server's dashboard URL ────────────────────────────────────
log "Patching .env with server URL"
PATCHED_ENV="$(mktemp)"
sed "s|^NOTIFY_DASHBOARD_URL=.*|NOTIFY_DASHBOARD_URL=http://${EXTERNAL_IP}:${DASHBOARD_PORT}|" \
    "$PROJECT_DIR/.env" > "$PATCHED_ENV"
ok "NOTIFY_DASHBOARD_URL → http://${EXTERNAL_IP}:${DASHBOARD_PORT}"

# ── Copy project files ────────────────────────────────────────────────────────
log "Copying project files to VM"

# Create remote directories
gcloud compute ssh "$INSTANCE_NAME" --zone="$ZONE" --quiet \
    --command="mkdir -p ~/flatwhite/data/logs ~/flatwhite/deploy"

# Copy source (exclude venv, cache, local data)
gcloud compute scp --recurse --zone="$ZONE" --quiet \
    "$PROJECT_DIR/flatwhite" \
    "$PROJECT_DIR/pyproject.toml" \
    "$PROJECT_DIR/config.yaml" \
    "$PROJECT_DIR/cron" \
    "$INSTANCE_NAME:~/flatwhite/"

# Copy patched .env
gcloud compute scp --zone="$ZONE" --quiet \
    "$PATCHED_ENV" \
    "$INSTANCE_NAME:~/flatwhite/.env"
rm -f "$PATCHED_ENV"

# Copy remote setup script
gcloud compute scp --zone="$ZONE" --quiet \
    "$SCRIPT_DIR/gcp_setup_remote.sh" \
    "$INSTANCE_NAME:~/flatwhite/deploy/gcp_setup_remote.sh"

ok "Files copied"

# ── Run remote setup ──────────────────────────────────────────────────────────
log "Running remote setup (this takes ~2 minutes)"

gcloud compute ssh "$INSTANCE_NAME" --zone="$ZONE" --quiet \
    --command="bash ~/flatwhite/deploy/gcp_setup_remote.sh"

# ── Done ──────────────────────────────────────────────────────────────────────
echo ""
echo "=============================================="
echo "  Flat White is live on Google Cloud!"
echo ""
echo "  Dashboard:  http://${EXTERNAL_IP}:${DASHBOARD_PORT}"
echo "  SSH:        gcloud compute ssh ${INSTANCE_NAME} --zone=${ZONE}"
echo ""
echo "  Cron runs every Wednesday 06:00 AEST (Tue 20:00 UTC)."
echo "  Email notifications go to flatwhite@theaussiecorporate.com"
echo ""
echo "  To redeploy after code changes:"
echo "    bash deploy/gcp_deploy.sh"
echo "=============================================="
