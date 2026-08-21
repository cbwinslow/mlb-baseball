#!/usr/bin/env bash
# Nightly full backup of whatever database DATABASE_URL points to in this
# environment (production `mlb` on the deployed host -- never mlb_test, see
# CLAUDE.md's database-naming golden rule), then rotates old backups so
# disk doesn't fill up. `mlb backup` records the run in meta.ingestion_run
# (backup.py), which is what lets `mlb doctor` flag a stale backup instead
# of this silently going stale the way the pre-automation manual dump did.
#
# Same flock + logging shape as mlb_daily_update.sh / mlb_api_update.sh --
# one pattern for every scheduled job in this project, not a new one per
# script.
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOCK_FILE="/tmp/mlb_backup.lock"
LOG_FILE="$REPO_DIR/logs/mlb_backup.log"

# One week of nightly full backups. At ~38GB/backup (current production
# size) that's ~266GB -- comfortable against typical local disk headroom;
# raise or lower to match actual available space.
KEEP=7

# A minimum, not a precise forecast: current production size (~38GB) plus
# real headroom, so a genuinely full disk fails loudly here instead of
# pg_dump failing partway through with a truncated, useless dump file.
MIN_FREE_GB=50

mkdir -p "$REPO_DIR/logs"

if ! command -v flock >/dev/null 2>&1; then
    echo "$(date -u +%FT%TZ) flock not found on PATH -- cannot safely run" >> "$LOG_FILE"
    exit 1
fi

exec 200>"$LOCK_FILE"
if ! flock -n 200; then
    echo "$(date -u +%FT%TZ) backup already running, skipping this tick" >> "$LOG_FILE"
    exit 0
fi

cd "$REPO_DIR"
{
    echo "$(date -u +%FT%TZ) starting nightly backup"
    free_kb=$(df --output=avail -k "$REPO_DIR" | tail -1)
    free_gb=$((free_kb / 1024 / 1024))
    if [ "$free_gb" -lt "$MIN_FREE_GB" ]; then
        echo "$(date -u +%FT%TZ) only ${free_gb}GB free (need >= ${MIN_FREE_GB}GB) -- skipping"
        exit 1
    fi
    "$REPO_DIR/.venv/bin/mlb" backup --keep "$KEEP"
    echo "$(date -u +%FT%TZ) finished nightly backup"
} >> "$LOG_FILE" 2>&1
