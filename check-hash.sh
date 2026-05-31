#!/bin/bash
/opt/health-manager/backend/.venv/bin/python -c "
import sqlite3
conn = sqlite3.connect('/opt/health-manager/backend/data/health.db')
row = conn.execute('SELECT password_hash FROM users LIMIT 1').fetchone()
print(repr(row[0]))
conn.close()
"
