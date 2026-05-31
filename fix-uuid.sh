#!/bin/bash
# Replace Mapped[UUID] with Mapped[str] in all production models
cd /opt/health-manager/backend/app/models
for f in *.py; do
    sudo -u health-manager sed -i 's/Mapped\[UUID\]/Mapped[str]/g' "$f"
    # Also fix Mapped[UUID | None]
    sudo -u health-manager sed -i 's/Mapped\[str | None\]/Mapped[str | None]/g' "$f"
done
echo "Patched all models"
# Clear pycache
sudo rm -rf /opt/health-manager/backend/app/models/__pycache__
sudo systemctl restart health-manager
sleep 3
systemctl is-active health-manager
