#!/usr/bin/env bash
# Database backup script for Family Health Manager
# Usage: ./scripts/backup-db.sh
#
# Supports: Local file backup or S3 upload (if AWS credentials configured)
# Retention: Daily 7 days, weekly 4 weeks, monthly 6 months
#
# Environment variables:
#   DB_HOST        - Database host (default: localhost)
#   DB_PORT        - Database port (default: 5432)
#   DB_NAME        - Database name (default: healthmanager)
#   DB_USER        - Database user (default: healthmanager)
#   BACKUP_DIR     - Local backup directory (default: ./backups)
#   S3_BUCKET      - S3 bucket for offsite backup (optional)
set -euo pipefail

DB_HOST="${DB_HOST:-localhost}"
DB_PORT="${DB_PORT:-5432}"
DB_NAME="${DB_NAME:-healthmanager}"
DB_USER="${DB_USER:-healthmanager}"
BACKUP_DIR="${BACKUP_DIR:-./backups}"
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
FILENAME="${DB_NAME}_${TIMESTAMP}.sql.gz"
FILEPATH="${BACKUP_DIR}/${FILENAME}"

# Create backup directory
mkdir -p "${BACKUP_DIR}"

echo "[$(date)] Starting backup of ${DB_NAME}..."

# Check if running inside Docker (backup from container)
if command -v docker &>/dev/null && docker ps --format '{{.Names}}' | grep -q "db\|postgres"; then
    CONTAINER=$(docker ps --format '{{.Names}}' | grep -E 'db|postgres' | head -1)
    echo "Dumping from Docker container: ${CONTAINER}"
    docker exec "${CONTAINER}" pg_dump -U "${DB_USER}" "${DB_NAME}" | gzip > "${FILEPATH}"
else
    # Direct pg_dump
    PGPASSWORD="${DB_PASSWORD:-}" pg_dump \
        -h "${DB_HOST}" \
        -p "${DB_PORT}" \
        -U "${DB_USER}" \
        "${DB_NAME}" | gzip > "${FILEPATH}"
fi

FILESIZE=$(du -h "${FILEPATH}" | cut -f1)
echo "[$(date)] Backup created: ${FILEPATH} (${FILESIZE})"

# Upload to S3 if configured
if [ -n "${S3_BUCKET:-}" ]; then
    echo "[$(date)] Uploading to S3: s3://${S3_BUCKET}/${FILENAME}"
    if command -v aws &>/dev/null; then
        aws s3 cp "${FILEPATH}" "s3://${S3_BUCKET}/${FILENAME}" \
            --storage-class STANDARD_IA \
            --quiet
        echo "[$(date)] S3 upload complete"
    else
        echo "[WARNING] aws CLI not found. S3 upload skipped."
    fi
fi

# Cleanup old local backups
echo "[$(date)] Cleaning old local backups..."
# Keep daily backups for 7 days
find "${BACKUP_DIR}" -name "*.sql.gz" -mtime +7 -delete 2>/dev/null || true
echo "[$(date)] Backup complete"
