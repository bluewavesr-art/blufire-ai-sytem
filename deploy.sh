#!/bin/bash
# Blufire AI System — DigitalOcean VPS Deployment Script
# Run this on your VPS at 143.198.139.48

set -e

echo "============================================"
echo "  BLUFIRE AI SYSTEM — Deployment"
echo "============================================"

# System updates
echo "[1/7] Updating system packages..."
apt-get update -qq && apt-get upgrade -y -qq

# Install Node.js 22
echo "[2/7] Installing Node.js 22..."
if ! command -v node &>/dev/null || [[ $(node -v | cut -d. -f1 | tr -d v) -lt 20 ]]; then
    curl -fsSL https://deb.nodesource.com/setup_22.x | bash -
    apt-get install -y nodejs
fi
echo "  Node.js $(node -v)"

# Install Python dependencies
echo "[3/7] Installing Python dependencies..."
apt-get install -y python3 python3-pip python3-venv -qq
pip3 install python-dotenv requests anthropic pyyaml --quiet

# Clone or pull repository
echo "[4/7] Setting up repository..."
REPO_DIR="/opt/blufire-ai-system"
if [ -d "$REPO_DIR" ]; then
    cd "$REPO_DIR"
    git pull origin claude/install-ruflo-agents-lZk1Y
else
    git clone https://github.com/bluewavesr-art/blufire-ai-sytem.git "$REPO_DIR"
    cd "$REPO_DIR"
    git checkout claude/install-ruflo-agents-lZk1Y
fi

# Install npm dependencies
echo "[5/7] Installing npm dependencies..."
cd "$REPO_DIR"
npm install --production

# Set up environment
echo "[6/7] Configuring environment..."
if [ ! -f /root/.env ]; then
    echo "WARNING: /root/.env not found!"
    echo "Create /root/.env with your API keys:"
    echo "  HUBSPOT_API_KEY=pat-na2-..."
    echo "  ANTHROPIC_API_KEY=sk-ant-api03-..."
    echo "  GMAIL_USER=your@gmail.com"
    echo "  GMAIL_APP_PASSWORD=xxxx xxxx xxxx xxxx"
    echo "  APOLLO_API_KEY=..."
fi

# Create systemd service
echo "[7/7] Setting up systemd service..."
cat > /etc/systemd/system/blufire.service << 'SVCEOF'
[Unit]
Description=Blufire AI System - Ruflo Agent Orchestrator
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/opt/blufire-ai-system
ExecStart=/usr/bin/python3 ruflo/orchestrator.py
Restart=always
RestartSec=10
Environment=PYTHONPATH=/opt/blufire-ai-system
EnvironmentFile=/root/.env

[Install]
WantedBy=multi-user.target
SVCEOF

systemctl daemon-reload
systemctl enable blufire
systemctl start blufire

echo ""
echo "============================================"
echo "  DEPLOYMENT COMPLETE"
echo "============================================"
echo ""
echo "  Service: systemctl status blufire"
echo "  Logs:    journalctl -u blufire -f"
echo "  Restart: systemctl restart blufire"
echo ""
