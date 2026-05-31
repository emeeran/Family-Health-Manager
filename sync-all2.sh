#!/bin/bash
# Full sync including prompts, excluding data/venv/env/alembic
sudo rsync -av --delete \
  --exclude='__pycache__' \
  --exclude='*.pyc' \
  --exclude='data/' \
  --exclude='.env' \
  --exclude='.venv' \
  --exclude='alembic/' \
  --exclude='alembic.ini' \
  --exclude='db-setup.py' \
  /home/em/code/finished/health-manager/backend/ \
  /opt/health-manager/backend/ \
  --exclude='tests/'
sudo find /opt/health-manager/backend/app -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null
sudo systemctl restart health-manager
sleep 3
curl -s http://localhost:8000/health
