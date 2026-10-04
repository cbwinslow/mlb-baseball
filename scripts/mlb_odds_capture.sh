#!/usr/bin/env bash
# Odds capture cron entry (every 15 minutes): flock + log + `mlb odds-capture`.
#
# What gets captured, and when it is skipped, lives in mlb_baseball/odds_capture.py
# (openspec/changes/odds-history-capture/). This shim only keeps what suits cron:
# one run at a time (a slow tick must not stack with the next), and a log file.
set -uo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# Overridable so tests don't contend on one global lock/log.
LOCK_FILE="${MLB_ODDS_LOCK_FILE:-/tmp/mlb_odds_capture.lock}"
LOG_FILE="${MLB_ODDS_LOG_FILE:-$REPO_DIR/logs/mlb_odds_capture.log}"
MLB="$REPO_DIR/.venv/bin/mlb"

mkdir -p "$(dirname "$LOG_FILE")"

exec 200>"$LOCK_FILE"
if ! flock -n 200; then
    echo "$(date -u +%FT%TZ) odds capture already running, skipping this tick" >> "$LOG_FILE"
    exit 0
fi

cd "$REPO_DIR"
{
    echo "$(date -u +%FT%TZ) starting odds capture"
    "$MLB" odds-capture
    rc=$?
    echo "$(date -u +%FT%TZ) finished odds capture (rc=$rc)"
} >> "$LOG_FILE" 2>&1
exit "$rc"
