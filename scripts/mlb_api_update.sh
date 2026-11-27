#!/usr/bin/env bash
# Runs `mlb ingest mlb_api --mode update` on a cron cadence to keep the
# current season's schedule/standings and live-game state fresh. See
# docs/DECISIONS.md ADR-016 for why cron + flock instead of systemd/a
# workflow tool, and mlb_api.py's FRESHNESS_THRESHOLD_MINUTES for how
# `mlb doctor` detects this having silently stopped running.
#
# flock prevents overlapping runs (a slow/retried run stacking with the
# next scheduled tick) rather than assuming every run finishes well within
# the cron interval. cd's to the repo root before running so config.py's
# load_dotenv() finds .env regardless of cron's minimal environment.
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# Overridable so tests don't contend on one global lock.
LOCK_FILE="${MLB_API_LOCK_FILE:-/tmp/mlb_api_update.lock}"
LOG_FILE="$REPO_DIR/logs/mlb_api_update.log"
FAIL_FILE="$REPO_DIR/logs/mlb_api_update.failures" # failures in a row
ALERT_AFTER=3
# Runs stopped because conform/predict hold the database are expected nightly (under an
# hour), so they are counted apart and alert only if the block lasts two hours.
BLOCKED_FILE="$REPO_DIR/logs/mlb_api_update.blocked"
ALERT_BLOCKED_AFTER=24
BUSY="workflow: another ingestion or derived-data stage is active"

mkdir -p "$REPO_DIR/logs"

exec 200>"$LOCK_FILE"
if ! flock -n 200; then
    echo "$(date -u +%FT%TZ) mlb_api update already running, skipping this tick" >> "$LOG_FILE"
    exit 0
fi

# count_run FILE THRESHOLD WHAT: add one to the count; alert when it reaches the threshold
# (equality, so once per outage).
count_run() {
    local count
    count=$(($(cat "$1" 2>/dev/null || echo 0) + 1))
    echo "$count" > "$1"
    if [[ $count -eq $2 ]]; then
        "$REPO_DIR/scripts/mlb_alert.sh" \
            "mlb_api update has $3 $count times in a row; see $LOG_FILE" ||
            echo "alert could not be sent"
    fi
}

cd "$REPO_DIR"
{
    start=$(stat -c %s "$LOG_FILE") # where this run's output begins
    echo "$(date -u +%FT%TZ) starting mlb_api update"
    rc=0
    "$REPO_DIR/.venv/bin/mlb" ingest mlb_api --mode update || rc=$?
    echo "$(date -u +%FT%TZ) finished mlb_api update (rc=$rc)"
    if [[ $rc -eq 0 ]]; then
        rm -f "$FAIL_FILE" "$BLOCKED_FILE"
    elif grep -qF "$BUSY" <(tail -c "+$((start + 1))" "$LOG_FILE"); then
        count_run "$BLOCKED_FILE" "$ALERT_BLOCKED_AFTER" "been blocked"
    else
        rm -f "$BLOCKED_FILE" # no longer blocked "in a row"
        count_run "$FAIL_FILE" "$ALERT_AFTER" "failed"
    fi
} >> "$LOG_FILE" 2>&1
exit "$rc"
