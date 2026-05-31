#!/bin/bash
# Fix the date calculation bug in production backend
# Replaces buggy month arithmetic with timedelta
cd /opt/health-manager/backend
.venv/bin/python -c "
import re
with open('app/routers/members.py', 'r') as f:
    content = f.read()
old = 'six_months_ago = date.today().replace(month=date.today().month - 6) if date.today().month > 6 else date.today().replace(year=date.today().year - 1, month=date.today().month + 6)'
new = 'six_months_ago = date.today() - __import__(\"datetime\").timedelta(days=182)'
if old in content:
    content = content.replace(old, new)
    with open('app/routers/members.py', 'w') as f:
        f.write(content)
    print('Fixed')
else:
    print('Pattern not found - may already be fixed')
"
