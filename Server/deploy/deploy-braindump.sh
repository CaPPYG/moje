#!/bin/bash
# ─────────────────────────────────────────────────────────────
#  BrainDump — Deploy Script
#  Spusti na serveri ako: bash deploy/deploy-braindump.sh
# ─────────────────────────────────────────────────────────────

set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SERVER_DIR="$(dirname "$SCRIPT_DIR")"
BRAINDUMP_DIR="$SERVER_DIR/BrainDump"
BACKEND_DIR="$BRAINDUMP_DIR/backend"
VENV_DIR="$BRAINDUMP_DIR/venv"
SERVICE_NAME="braindump"

echo "🧠 BrainDump Deploy Script"
echo "═══════════════════════════"

# 1. Python venv + dependencies
echo "📦 Inštalujem Python dependencies…"
if [ ! -d "$VENV_DIR" ]; then
    python3 -m venv "$VENV_DIR"
fi
"$VENV_DIR/bin/pip" install --quiet --upgrade pip
"$VENV_DIR/bin/pip" install --quiet -r "$BACKEND_DIR/requirements.txt"
echo "   ✅ Dependencies nainštalované"

# 2. .env file
if [ ! -f "$BACKEND_DIR/.env" ]; then
    cp "$BACKEND_DIR/.env.example" "$BACKEND_DIR/.env"
    echo "   ⚠️  Vytvorený .env súbor — VYPLŇ GROQ_API_KEY!"
    echo "   Edituj: nano $BACKEND_DIR/.env"
else
    echo "   ✅ .env existuje"
fi

# 3. DB directory
DB_DIR=$(dirname "$(grep DB_PATH "$BACKEND_DIR/.env" | cut -d= -f2 2>/dev/null || echo "$BRAINDUMP_DIR/braindump.db")")
mkdir -p "$DB_DIR"
echo "   ✅ DB adresár: $DB_DIR"

# 4. systemd service
echo "⚙️  Inštalujem systemd service…"
sudo cp "$SCRIPT_DIR/braindump.service" /etc/systemd/system/braindump.service
# Update WorkingDirectory and ExecStart paths in the service file
sudo sed -i "s|/home/patrik/server/BrainDump|$BRAINDUMP_DIR|g" /etc/systemd/system/braindump.service
sudo systemctl daemon-reload
sudo systemctl enable "$SERVICE_NAME"
sudo systemctl restart "$SERVICE_NAME"
sleep 2
if sudo systemctl is-active --quiet "$SERVICE_NAME"; then
    echo "   ✅ Service beží (port 5090)"
else
    echo "   ❌ Service zlyhala! Skontroluj: journalctl -u $SERVICE_NAME -n 30"
    exit 1
fi

# 5. Nginx config
echo "🌐 Aktualizujem Nginx config…"
sudo cp "$SCRIPT_DIR/nginx-hub.conf" /etc/nginx/sites-available/hub
sudo ln -sf /etc/nginx/sites-available/hub /etc/nginx/sites-enabled/hub
sudo nginx -t && sudo systemctl reload nginx
echo "   ✅ Nginx reloadnutý"

echo ""
echo "✨ BrainDump nasadený!"
echo "   URL: https://garcarzp.online/braindump/"
echo "   API: https://garcarzp.online/braindump/api/docs"
echo "   PWA: Otvor URL v Chrome → Inštalovať aplikáciu"
echo ""
echo "   Nezabudni vyplniť GROQ_API_KEY v:"
echo "   $BACKEND_DIR/.env"
