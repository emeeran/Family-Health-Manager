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
# Remove __pycache__ dirs only. (The previous `rm -rf app/**/**/` was a bug:
# without globstar, `**` collapses to `*`, so the glob matched `app/*/*/` and
# deleted EVERY directory two levels deep — including app/services/ai/.)
sudo find /opt/health-manager/backend/app -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null
sudo systemctl restart health-manager
sleep 3
echo "Backend status:"
curl -s http://localhost:8000/health
