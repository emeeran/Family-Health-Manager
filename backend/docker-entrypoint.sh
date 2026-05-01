#!/usr/bin/env bash
set -e

# Run database migrations before starting the app (PostgreSQL only)
if [[ "${DATABASE_URL}" == postgresql* ]]; then
    echo "Running database migrations..."
    alembic upgrade head
    echo "Migrations complete."
else
    echo "SQLite detected — skipping migrations (auto-created by SQLAlchemy)."
fi

exec "$@"
