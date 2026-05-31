#!/bin/bash
# Patch db-setup.py to skip alembic on existing DB, then restart
cd /opt/health-manager/backend
sudo -u health-manager .venv/bin/python3 -c "
import re
with open('db-setup.py', 'r') as f:
    content = f.read()
# Replace the alembic upgrade call with a no-op
content = content.replace('_alembic_upgrade_head()', 'print(\"Skipping alembic migrations\")')
with open('db-setup.py', 'w') as f:
    f.write(content)
print('Patched')
"
sudo systemctl start health-manager
sleep 3
systemctl is-active health-manager