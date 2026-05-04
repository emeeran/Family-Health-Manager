#!/usr/bin/env bash
# Database restore script for Family Health Manager
# Usage: ./scripts/restore-db.sh [backup_file.sql.gz]
#
# If no file specified, lists available backups for selection.
# For S3: ./scripts/restore-db.sh s3://bucket/filename.sql.gz
set -euo pipefail

DB_HOST="${DB_HOST:-localhost}"
DB_PORT="${DB_PORT:-5432}"
DB_NAME="${DB_NAME:-healthmanager}"
DB_USER="${DB_USER:-healthmanager}"
BACKUP_DIR="${BACKUP_DIR:-./backups}"

BACKUP_FILE="${1:-}"

# If no file specified, list available backups
if [ -z "${BACKUP_FILE}" ]; then
    echo "Available backups in ${BACKUP_DIR}:"
    if [ -d "${BACKUP_DIR}" ]; then
        ls -lht "${BACKUP_DIR}"/*.sql.gz 2>/dev/null || echo "  No backups found"
    else
        echo "  Backup directory does not exist"
    fi
    echo ""
    echo "Usage: $0 <backup_file.sql.gz>"
    exit 0
fi

# Download from S3 if needed
if [[ "${BACKUP_FILE}" == s3://* ]]; then
    S3_PATH="${BACKUP_FILE}"
    BACKUP_FILE=$(basename "${S3_PATH}")
    LOCAL_PATH="${BACKUP_DIR}/${BACKUP_FILE}"
    echo "Downloading from S3: ${S3_PATH}"
    aws s3 cp "${S3_PATH}" "${LOCAL_PATH}"
    BACKUP_FILE="${LOCAL_PATH}"
fi

# Verify file exists
if [ ! -f "${BACKUP_FILE}" ]; then
    echo "ERROR: File not found: ${BACKUP_FILE}"
    exit 1
fi

echo "WARNING: This will REPLACE the database ${DB_NAME}!"
read -p "Type 'yes' to continue: " CONFIRM
if [ "${CONFIRM}" != "yes" ]; then
    echo "Aborted."
    exit 0
fi

echo "[$(date)] Restoring ${BACKUP_FILE} to ${DB_NAME}..."

# Check if running inside Docker
if command -v docker &>/dev/null && docker ps --format '{{.Names}}' | grep -q "db\|postgres"; then
    CONTAINER=$(docker ps --format '{{.Names}}' | grep -E 'db|postgres' | head -1)
    echo "Restoring to Docker container: ${CONTAINER}"
    gunzip -c "${BACKUP_FILE}" | docker exec -i "${CONTAINER}" psql -U "${DB_USER}" "${DB_NAME}"
else
    gunzip -c "${BACKUP_FILE}" | PGPASSWORD="${DB_PASSWORD:-}" psql \
        -h "${DB_HOST}" \
        -p "${DB_PORT}" \
        -U "${DB_USER}" \
        "${DB_NAME}"
fi

echo "[$(date)] Restore complete"
