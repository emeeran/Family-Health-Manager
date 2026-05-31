#!/bin/bash
sudo /opt/health-manager/caddy start --config /etc/health-manager/Caddyfile
sleep 2
curl -s http://localhost:8080/health
