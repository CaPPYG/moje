#!/usr/bin/env bash
set -e

echo "=== Copying deployed files ==="
sudo cp -r /home/patrikgntb/ig_deploy/* /home/patrik/server/IGTracker/
sudo chown -R patrik:patrik /home/patrik/server/IGTracker

echo "=== Initializing database schema migrations ==="
cd /home/patrik/server/IGTracker
sudo -u patrik python3 -c "import db; db.init_db(); print('DB schema initialized successfully!')"

echo "=== Restarting igtracker service ==="
sudo systemctl restart igtracker
sleep 1
sudo systemctl is-active igtracker

echo "=== igtracker is running! ==="
