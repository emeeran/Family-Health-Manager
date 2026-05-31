#!/bin/bash
# Override systemd to skip db-setup, start backend directly
sudo systemctl stop health-manager 2>/dev/null
cd /opt/health-manager/backend
sudo -u health-manager .venv/bin/python3 -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --workers 2 &
sleep 2
echo "Backend started on port 8000"
