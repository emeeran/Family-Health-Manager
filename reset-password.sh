#!/bin/bash
cd /opt/health-manager/backend
.venv/bin/python -c "
from passlib.context import CryptContext
import sqlite3
pwd = CryptContext(schemes=['bcrypt'], deprecated='auto')
new_hash = pwd.hash('Password@123')
conn = sqlite3.connect('/opt/health-manager/backend/data/health.db')
conn.execute('UPDATE users SET password_hash = ?', (new_hash,))
conn.commit()
conn.close()
print('Password reset for all users to: Password@123')
"
