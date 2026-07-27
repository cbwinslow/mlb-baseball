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
LOCK_FILE="/tmp/mlb_api_update.lock"
LOG_FILE="$REPO_DIR/logs/mlb_api_update.log"

mkdir -p "$REPO_DIR/logs"

exec 200>"$LOCK_FILE"
if ! flock -n 200; then
    echo "$(date -u +%FT%TZ) mlb_api update already running, skipping this tick" >> "$LOG_FILE"
    exit 0
fi

cd "$REPO_DIR"
{
    echo "$(date -u +%FT%TZ) starting mlb_api update"
    "$REPO_DIR/.venv/bin/mlb" ingest mlb_api --mode update
    echo "$(date -u +%FT%TZ) finished mlb_api update"
} >> "$LOG_FILE" 2>&1
