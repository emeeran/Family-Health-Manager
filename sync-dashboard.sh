#!/bin/bash
sudo cp /home/em/code/finished/health-manager/backend/app/services/dashboard_service.py /opt/health-manager/backend/app/services/dashboard_service.py
sudo cp /home/em/code/finished/health-manager/backend/app/routers/dashboard.py /opt/health-manager/backend/app/routers/dashboard.py
sudo rm -rf /opt/health-manager/backend/app/services/__pycache__ /opt/health-manager/backend/app/routers/__pycache__
sudo systemctl restart health-manager
sleep 3
systemctl is-active health-manager
