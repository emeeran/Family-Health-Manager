#!/bin/bash
# Copy missing subdirectories from dev to prod
for dir in \
  app/services/ai \
  app/services/ai/providers \
  app/routers \
  app/core \
  app/models \
  app/prompts; do
  echo "Copying $dir..."
  sudo cp -r "/home/em/code/finished/health-manager/backend/$dir" "/opt/health-manager/backend/$dir"
done
# Also copy any standalone files
sudo cp /home/em/code/finished/health-manager/backend/app/main.py /opt/health-manager/backend/app/main.py
sudo find /opt/health-manager/backend -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null
sudo systemctl restart health-manager
sleep 3
curl -s http://localhost:8000/health
