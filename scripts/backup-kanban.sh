#!/usr/bin/env bash
# Kanban backup script — works with both Docker and native/systemd deployments.
#
# Usage:
#   ./scripts/backup-kanban.sh                          # backups to ./backups/, keep 30 days
#   ./scripts/backup-kanban.sh --dir /mnt/backups       # custom directory
#   ./scripts/backup-kanban.sh --keep 90                # keep 90 days
#   ./scripts/backup-kanban.sh --dir /mnt/backups --keep 90
#
# Automated with systemd:
#   sudo cp kanban-backup.service /etc/systemd/system/
#   sudo cp kanban-backup.timer   /etc/systemd/system/
#   sudo systemctl daemon-reload
#   sudo systemctl enable --now kanban-backup.timer
#
# Automated with cron (alternative):
#   # Daily at 3am
#   0 3 * * * /opt/kanban/scripts/backup-kanban.sh --dir /mnt/backups

set -euo pipefail

# ── Defaults ──────────────────────────────────────────────────────────────

BACKUP_DIR="${BACKUP_DIR:-./backups}"
KEEP_DAYS="${KEEP_DAYS:-30}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

# ── Argument parsing ──────────────────────────────────────────────────────

while [[ $# -gt 0 ]]; do
    case "$1" in
        --dir)   BACKUP_DIR="$2"; shift 2 ;;
        --keep)  KEEP_DAYS="$2";  shift 2 ;;
        --help)  head -20 "$0";   exit 0   ;;
        *)       echo "Error: Unknown option: $1"; exit 1 ;;
    esac
done

# ── Main ───────────────────────────────────────────────────────────────────

mkdir -p "$BACKUP_DIR"
TIMESTAMP=$(date +%Y%m%d-%H%M%S)
BACKUP_FILE="${BACKUP_DIR}/kanban-${TIMESTAMP}.db"

# Try Docker mode first
if docker compose ps -q kanban 2>/dev/null | grep -q . || \
   docker container inspect kanban-web 2>/dev/null | grep -q '"Status": "running"'; then
    echo "[Docker mode] Extracting database from kanban-web container..."
    docker cp kanban-web:/app/data/kanban.db "$BACKUP_FILE"

# Fall back to native (systemd / manual)
elif [ -f "$PROJECT_DIR/kanban/kanban.db" ]; then
    echo "[Native mode] Copying database from $PROJECT_DIR/kanban/kanban.db..."
    cp "$PROJECT_DIR/kanban/kanban.db" "$BACKUP_FILE"

else
    echo "Error: Kanban database not found. Is the server running?" >&2
    echo "  Tried: docker container kanban-web" >&2
    echo "  Tried: $PROJECT_DIR/kanban/kanban.db" >&2
    exit 1
fi

echo "Backup saved: $BACKUP_FILE ($(du -h "$BACKUP_FILE" | cut -f1))"

# Prune backups older than KEEP_DAYS
find "$BACKUP_DIR" -name 'kanban-*.db' -mtime +"$KEEP_DAYS" -delete
PRUNED=$(find "$BACKUP_DIR" -name 'kanban-*.db' | wc -l)
echo "Backups retained: $PRUNED (keeping $KEEP_DAYS days)"
