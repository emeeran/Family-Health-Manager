#!/bin/bash
SRC="/home/em/code/finished/health-manager/backend/data/health.db"
DST="/opt/health-manager/backend/data/health.db"
echo "Source size: $(stat -c '%s' $SRC) bytes"
echo "Dest size: $(stat -c '%s' $DST) bytes"
sudo systemctl stop health-manager
sudo cp "$SRC" "$DST"
echo "New dest size: $(stat -c '%s' $DST) bytes"
sudo systemctl start health-manager
echo "Done"
