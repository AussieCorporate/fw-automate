#!/usr/bin/env bash
# ─── Nitter Self-Hosted Setup (Twitter/X RSS Proxy) ──────────────────────────
#
# This script sets up a self-hosted Nitter instance using the sekai-soft fork,
# which provides reliable Twitter/X RSS feeds for the Flat White pipeline.
#
# Prerequisites:
#   - Docker installed and running
#   - A burner Twitter/X account (2FA disabled)
#
# After setup:
#   - RSS feeds available at: http://localhost:8080/{handle}/rss?key=<PASSWORD>
#   - Update flatwhite/config.yaml:
#       twitter:
#         enabled: true
#         rss_proxy_base: "http://localhost:8080"
#
# Reference: https://github.com/sekai-soft/guide-nitter-self-hosting
# ──────────────────────────────────────────────────────────────────────────────

set -euo pipefail

echo "=== Nitter Self-Hosted Setup ==="
echo ""
echo "This will set up a local Nitter instance for Twitter/X RSS feeds."
echo ""

# Check Docker
if ! command -v docker &> /dev/null; then
    echo "ERROR: Docker is not installed. Install Docker Desktop first:"
    echo "  https://docs.docker.com/desktop/install/mac-install/"
    exit 1
fi

echo "Docker found: $(docker --version)"
echo ""

# Create nitter directory
NITTER_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/nitter"
mkdir -p "$NITTER_DIR"
cd "$NITTER_DIR"

echo "Setting up in: $NITTER_DIR"
echo ""

# Prompt for Twitter credentials
echo "You need a burner Twitter/X account (2FA must be disabled)."
echo ""
read -p "Twitter username: " TWITTER_USER
read -sp "Twitter password: " TWITTER_PASS
echo ""
read -p "RSS access password (for securing feeds): " RSS_PASSWORD
echo ""

# Create docker-compose.yml
cat > docker-compose.yml << YAML
version: "3"
services:
  nitter:
    image: ghcr.io/sekai-soft/nitter-self-contained:latest
    container_name: flatwhite-nitter
    ports:
      - "8080:8080"
    environment:
      - INSTANCE_RSS_PASSWORD=${RSS_PASSWORD}
      - NITTER_ACCOUNTS_FILE=/accounts.txt
    volumes:
      - ./accounts.txt:/accounts.txt:ro
      - nitter_data:/nitter-data
    restart: unless-stopped

volumes:
  nitter_data:
YAML

# Create accounts file
echo "${TWITTER_USER}:${TWITTER_PASS}" > accounts.txt
chmod 600 accounts.txt

echo ""
echo "Starting Nitter..."
docker compose up -d

echo ""
echo "Waiting for Nitter to start..."
sleep 10

# Test
echo "Testing RSS feed..."
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" "http://localhost:8080/BBCBusiness/rss?key=${RSS_PASSWORD}" 2>/dev/null || echo "000")

if [ "$HTTP_CODE" = "200" ]; then
    echo ""
    echo "=== SUCCESS ==="
    echo ""
    echo "Nitter is running at http://localhost:8080"
    echo "RSS feeds: http://localhost:8080/{handle}/rss?key=${RSS_PASSWORD}"
    echo ""
    echo "Next steps — update flatwhite/config.yaml:"
    echo ""
    echo "  twitter:"
    echo "    enabled: true"
    echo "    rss_proxy_base: \"http://localhost:8080\""
    echo "    rss_key: \"${RSS_PASSWORD}\""
    echo ""
    echo "Then update flatwhite/editorial/twitter_rss.py to append"
    echo "?key={rss_key} to the RSS URL."
else
    echo ""
    echo "=== SETUP COMPLETE (verification pending) ==="
    echo ""
    echo "Nitter container is starting. It may take 1-2 minutes to initialize."
    echo "Check status:  docker logs flatwhite-nitter"
    echo "Test manually: curl http://localhost:8080/BBCBusiness/rss?key=${RSS_PASSWORD}"
    echo ""
    echo "If it fails, check:"
    echo "  1. Twitter credentials are correct"
    echo "  2. 2FA is disabled on the account"
    echo "  3. The account hasn't been locked"
fi

echo ""
echo "Manage:"
echo "  Start:   cd $NITTER_DIR && docker compose up -d"
echo "  Stop:    cd $NITTER_DIR && docker compose down"
echo "  Logs:    docker logs flatwhite-nitter"
echo "  Restart: cd $NITTER_DIR && docker compose restart"
