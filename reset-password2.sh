#!/bin/bash
/opt/health-manager/backend/.venv/bin/python -c "
import sqlite3
with open('/tmp/newhash.txt') as f:
    h = f.read().strip()
conn = sqlite3.connect('/opt/health-manager/backend/data/health.db')
conn.execute('UPDATE users SET password_hash = ?', (h,))
conn.commit()
conn.close()
print('Done. Hash set to:', h[:20] + '...')
"
