#!/usr/bin/env bash
set -euo pipefail

# Solar monitor deployment script (Ubuntu 24.04, run as patrik with sudo).
APP=/home/patrik/solar
SRC="$(cd "$(dirname "$0")/.." && pwd)"

echo "==> Pripravujem adresar $APP"
sudo mkdir -p "$APP/static" "$APP/templates" "$APP/data"
sudo chown -R patrik:patrik "$APP"

echo "==> Kopirujem subory"
cp "$SRC/app.py" "$SRC/collector.py" "$SRC/config.py" "$SRC/db.py" \
   "$SRC/requirements.txt" "$SRC/config.yaml" "$APP/"
cp -r "$SRC/templates/index.html" "$APP/templates/"
cp -r "$SRC/static/app.js" "$SRC/static/style.css" "$APP/static/"
mkdir -p "$APP/deploy"
cp "$SRC/deploy/nginx-solar.conf" "$APP/deploy/"
cp "$SRC/deploy/solar.service" "$APP/deploy/"

echo "==> Instalujem systemove baliky"
sudo apt-get update -y
sudo apt-get install -y python3-venv python3-pip nginx

echo "==> Virtualne prostredie + requirements"
cd "$APP"
if [ ! -d ".venv" ]; then
  python3 -m venv .venv
fi
./.venv/bin/pip install --upgrade pip -q
./.venv/bin/pip install -r requirements.txt -q

echo "==> .env (tajne hodnoty)"
if [ ! -f "$APP/.env" ]; then
  cat > "$APP/.env" <<EOF
SOLAR_ESP_KEY=3bad083106fa164908f918b768a58124
SOLAR_VENDOR_PASSWORD=
EOF
  chmod 600 "$APP/.env"
  echo "   Vytvoreny .env (SOLAR_ESP_KEY nastaveny; SOLAR_VENDOR_PASSWORD prazdne)"
else
  echo "   .env uz existuje - preskakujem"
fi

echo "==> Systemd sluzba"
sudo cp "$APP/deploy/solar.service" /etc/systemd/system/solar.service
sudo systemctl daemon-reload
sudo systemctl enable solar.service
sudo systemctl restart solar.service

echo "==> Nginx"
sudo cp "$APP/deploy/nginx-solar.conf" /etc/nginx/sites-available/solar
sudo ln -sf /etc/nginx/sites-available/solar /etc/nginx/sites-enabled/solar
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t
sudo systemctl reload nginx

echo "==> Stav sluzby"
sleep 1
sudo systemctl status solar.service --no-pager -l || true
echo
echo "DONE. Otestuj: curl http://127.0.0.1:8000/api/health"
