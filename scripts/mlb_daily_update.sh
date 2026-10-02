#!/usr/bin/env bash
# Daily pipeline cron entry: flock + log + `mlb nightly`.
#
# The step logic (migrate -> update -> conform -> report -> predict -> populated
# check), the gates, retries and failure alerts live in mlb_baseball/nightly.py
# (openspec/changes/job-retries-alerts/, docs/ARCHITECTURE.md "Scheduling"). This
# shim only keeps what suits cron: one run at a time, and the log file name
# (logs/mlb_daily_update.log) that existing monitoring reads.
set -uo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# Overridable so tests (and a second checkout) don't contend on one global
# lock/log. Production cron uses the defaults.
LOCK_FILE="${MLB_DAILY_LOCK_FILE:-/tmp/mlb_daily_update.lock}"
LOG_FILE="${MLB_DAILY_LOG_FILE:-$REPO_DIR/logs/mlb_daily_update.log}"
MLB="$REPO_DIR/.venv/bin/mlb"

mkdir -p "$(dirname "$LOG_FILE")"

exec 200>"$LOCK_FILE"
if ! flock -n 200; then
    echo "$(date -u +%FT%TZ) daily update already running, skipping this tick" >> "$LOG_FILE"
    exit 0
fi

cd "$REPO_DIR"
exec "$MLB" nightly >> "$LOG_FILE" 2>&1
