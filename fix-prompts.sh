#!/bin/bash
sudo cp -r /home/em/code/finished/health-manager/backend/app/prompts /opt/health-manager/backend/app/prompts
sudo find /opt/health-manager/backend -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null
sudo systemctl restart health-manager
sleep 3
curl -s http://localhost:8000/health
