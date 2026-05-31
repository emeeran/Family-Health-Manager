#!/bin/bash
# Full sync of dev backend code to production, keeping prod DB and .env
sudo rsync -av --delete \
  --exclude='__pycache__' \
  --exclude='*.pyc' \
  --exclude='data/' \
  --exclude='.env' \
  --exclude='.venv' \
  --exclude='alembic/' \
  --exclude='alembic.ini' \
  --exclude='db-setup.py' \
  --exclude='prompts/' \
  /home/em/code/finished/health-manager/backend/app/ \
  /opt/health-manager/backend/app/
sudo rm -rf /opt/health-manager/backend/app/**/**/ __pycache__
sudo systemctl restart health-manager
sleep 3
echo "Backend status:"
curl -s http://localhost:8000/health
