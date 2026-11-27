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

mkdir -p "$REPO_DIR/logs"

exec 200>"$LOCK_FILE"
if ! flock -n 200; then
    echo "$(date -u +%FT%TZ) mlb_api update already running, skipping this tick" >> "$LOG_FILE"
    exit 0
fi

cd "$REPO_DIR"
{
    echo "$(date -u +%FT%TZ) starting mlb_api update"
    rc=0
    "$REPO_DIR/.venv/bin/mlb" ingest mlb_api --mode update || rc=$?
    echo "$(date -u +%FT%TZ) finished mlb_api update (rc=$rc)"
    if [[ $rc -eq 0 ]]; then
        rm -f "$FAIL_FILE"
    else
        failures=$(($(cat "$FAIL_FILE" 2>/dev/null || echo 0) + 1))
        echo "$failures" > "$FAIL_FILE"
        # Once per outage: the count only equals the threshold one time.
        if [[ $failures -eq $ALERT_AFTER ]]; then
            "$REPO_DIR/scripts/mlb_alert.sh" \
                "mlb_api update has failed $failures times in a row; see $LOG_FILE" ||
                echo "alert could not be sent"
        fi
    fi
} >> "$LOG_FILE" 2>&1
exit "$rc"
