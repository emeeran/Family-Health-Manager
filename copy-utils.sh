#!/bin/bash
sudo cp /home/em/code/finished/health-manager/backend/app/core/utils.py /opt/health-manager/backend/app/core/utils.py
sudo rm -rf /opt/health-manager/backend/app/core/__pycache__
sudo systemctl restart health-manager
sleep 3
curl -s http://localhost:8000/health
