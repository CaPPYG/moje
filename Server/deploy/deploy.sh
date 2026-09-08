#!/usr/bin/env bash
set -euo pipefail

# GarcArzP HUB deployment script (Ubuntu 24.04, run as patrik with sudo).
# Nainstaluje HUB dashboard + zjednotenu Nginx konfiguraciu (/, /solar, /cappytools).
APP=/home/patrik/server
SRC="$(cd "$(dirname "$0")/.." && pwd)"

echo "==> Pripravujem adresar $APP"
sudo mkdir -p "$APP"
sudo chown -R patrik:patrik "$APP"

if [ "$SRC" != "$APP" ]; then
    echo "==> Kopirujem HUB subory"
    cp "$SRC/index.html" "$APP/index.html"
    mkdir -p "$APP/deploy"
    cp "$SRC/deploy/nginx-hub.conf" "$APP/deploy/"
fi

echo "==> Nginx (zjednotena konfiguracia)"
sudo cp "$SRC/deploy/nginx-hub.conf" /etc/nginx/sites-available/hub
sudo ln -sf /etc/nginx/sites-available/hub /etc/nginx/sites-enabled/hub

# Odstran stare konfiguracie, aby nevznikol konflikt (default_server / server_name)
sudo rm -f /etc/nginx/sites-enabled/default
sudo rm -f /etc/nginx/sites-enabled/solar

echo "==> Testujem a reload Nginx"
sudo nginx -t
sudo systemctl reload nginx

echo
echo "DONE. Otestuj:"
echo "  curl -I https://garcarzp.online/"
echo "  curl -I https://garcarzp.online/solar/"
echo "  curl -I https://garcarzp.online/cappytools/"
echo "  curl -I https://garcarzp.online/drive/"
echo "  curl -I https://garcarzp.online/paste/"
echo "  curl -I https://garcarzp.online/ig/"
echo "  curl -s https://garcarzp.online/api/system-status"
echo "  curl -I http://127.0.0.1:8000/api/health"
