#!/bin/bash
# restore-archive.sh — privileged disaster-recovery restore.
#
# Runs as ROOT (via health-manager-restore.service), triggered by
# health-manager-restore.path when the app writes an archive name to
# /var/lib/health-manager/data/.restore-request (the app itself runs as the
# unprivileged health-manager user and cannot restart its own service).
#
# Strictly re-validates the archive name, makes a safety backup of the current
# state, stops the app, swaps health.db + attachments/ from the archive, fixes
# ownership, and restarts the app. Always writes a JSON result marker and
# removes the flag file.
set -euo pipefail

# Paths + service identity are env-overridable so the script can be exercised
# end-to-end against a throwaway layout in tests (set DATA_DIR to a temp dir and
# APP_SVC="" to skip systemctl). Production defaults are unchanged.
DATA_DIR="${DATA_DIR:-/var/lib/health-manager/data}"
BACKUPS_DIR="$DATA_DIR/backups"
HEALTH_DB="$DATA_DIR/health.db"
ATTACH_DIR="$DATA_DIR/attachments"
# NOTE: ${APP_SVC-...} (no colon) so that an EMPTY value means "skip service
# control" — tests set APP_SVC="" to avoid touching a real systemd unit. An unset
# value (production) still defaults to the real unit name. (DATA_DIR/APP_USER use
# :- because an empty value would be invalid for them.)
APP_SVC="${APP_SVC-health-manager.service}"
APP_USER="${APP_USER:-health-manager}"
FLAG="$DATA_DIR/.restore-request"
RESULT="$DATA_DIR/.restore-result"

# Strict: only backup_YYYYMMDD_HHMMSS.tar.gz. No path separators, no traversal.
NAME_RE='^backup_[0-9]{8}_[0-9]{6}\.tar\.gz$'

write_result() {
    # write_result <status> <archive> [key value]...
    local status="$1" archive="$2"; shift 2
    local ts; ts="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    {
        printf '{"status":"%s","archive":"%s","ts":"%s"' "$status" "$archive" "$ts"
        while [ "$#" -gt 0 ]; do
            printf ',"%s":"%s"' "$1" "$2"
            shift 2
        done
        printf '}\n'
    } > "$RESULT.tmp"
    mv -f "$RESULT.tmp" "$RESULT"
    chown "$APP_USER:$APP_USER" "$RESULT" 2>/dev/null || true
}

stop_app() {
    [ -z "$APP_SVC" ] && return 0
    systemctl stop "$APP_SVC" 2>/dev/null || true
}

restart_app() {
    [ -z "$APP_SVC" ] && return 0
    systemctl restart "$APP_SVC" 2>/dev/null || true
}

start_app() {
    # Intentionally NOT best-effort in prod: if the app can't come back up after
    # a restore the operator needs to know (service stays down + no "ok" result
    # marker is written). Tests pass APP_SVC="" to skip service control entirely.
    [ -z "$APP_SVC" ] && return 0
    systemctl start "$APP_SVC"
}

# ── Read + strictly re-validate the requested archive name ───────────────────
archive=""
if [ -f "$FLAG" ]; then
    archive="$(tr -d '\r\n' < "$FLAG")"
fi

if [[ ! "$archive" =~ $NAME_RE ]]; then
    echo "restore-archive: invalid archive name in flag file: '$archive'" >&2
    write_result "error" "${archive:-none}" "reason" "invalid archive name"
    rm -f "$FLAG"
    exit 1
fi

archive_path="$BACKUPS_DIR/$archive"
if [ ! -f "$archive_path" ]; then
    echo "restore-archive: archive not found: $archive_path" >&2
    write_result "error" "$archive" "reason" "archive not found"
    rm -f "$FLAG"
    exit 1
fi

# Must be a readable tar.gz containing a SQLite snapshot (pg dumps unsupported here).
if ! tar -tzf "$archive_path" >/dev/null 2>&1; then
    write_result "error" "$archive" "reason" "not a readable tar.gz"
    rm -f "$FLAG"
    exit 1
fi
if ! tar -tzf "$archive_path" | grep -qx "health.db"; then
    write_result "error" "$archive" "reason" "no health.db (PostgreSQL unsupported)"
    rm -f "$FLAG"
    exit 1
fi

# ── Stop the app so the DB is quiescent before we touch it ───────────────────
stop_app

# ── Safety backup of the CURRENT state (the undo path) ───────────────────────
pre_archive="$BACKUPS_DIR/backup_prerestore_$(date -u +%Y%m%d_%H%M%S).tar.gz"
pre_tmp="$(mktemp -d)"
cp "$HEALTH_DB" "$pre_tmp/health.db"
if [ -d "$ATTACH_DIR" ]; then
    cp -a "$ATTACH_DIR" "$pre_tmp/attachments"
fi
pre_args=(health.db)
[ -d "$pre_tmp/attachments" ] && pre_args+=(attachments)
tar -czf "$pre_archive" -C "$pre_tmp" "${pre_args[@]}" 2>/dev/null || true
rm -rf "$pre_tmp"
chown "$APP_USER:$APP_USER" "$pre_archive" 2>/dev/null || true

# ── Extract the target archive; restart the app on any failure ───────────────
work="$(mktemp -d)"
cleanup() {
    rm -rf "$work"
    restart_app
}
trap cleanup EXIT

if ! tar -xzf "$archive_path" -C "$work"; then
    write_result "error" "$archive" "reason" "extraction failed"
    rm -f "$FLAG"
    exit 1
fi
if [ ! -f "$work/health.db" ]; then
    write_result "error" "$archive" "reason" "no health.db after extract"
    rm -f "$FLAG"
    exit 1
fi

# ── Swap DB (drop stale WAL/shm) + attachments ───────────────────────────────
rm -f "$HEALTH_DB" "$HEALTH_DB-wal" "$HEALTH_DB-shm"
mv -f "$work/health.db" "$HEALTH_DB"

rm -rf "$ATTACH_DIR"
if [ -d "$work/attachments" ]; then
    mv "$work/attachments" "$ATTACH_DIR"
else
    mkdir -p "$ATTACH_DIR"
fi

chown -R "$APP_USER:$APP_USER" "$DATA_DIR"

# ── Restart (ExecStartPre db-setup runs alembic upgrade head) ────────────────
start_app

write_result "ok" "$archive" "pre_restore_backup" "$(basename "$pre_archive")"
rm -f "$FLAG"
trap - EXIT
rm -rf "$work"
exit 0
