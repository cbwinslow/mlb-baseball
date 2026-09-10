#!/usr/bin/env bash
# Runs `mlb ingest fangraphs --mode update` on a 6-hourly cron cadence.
#
# The daily `scripts/mlb_daily_update.sh` (via `mlb update`) already refreshes
# the FanGraphs season leaderboards / Guts! / park factors / prospects / splits
# once a day and is the freshness guarantee (see fangraphs.py's
# FRESHNESS_THRESHOLD_MINUTES / DAILY_FRESHNESS_THRESHOLD_MINUTES). This job
# exists for one extra reason: FanGraphs projections update more than once a
# day, and `raw.fangraphs_projection` is an append-only, change-detected
# snapshot history (ADR-288 / ADR-048 pattern) — running `update()` every 6h
# captures projection movement that a once-daily run would miss, while the
# `_row_hash` de-dupe keeps an unchanged projection from adding a row.
#
# Same flock + logging shape as `scripts/mlb_api_update.sh`, deliberately.
# flock prevents an overlapping run (a slow/retried run stacking with the next
# scheduled tick). cd's to the repo root so config.py's load_dotenv() finds
# .env regardless of cron's minimal environment.
#
# Suggested crontab line (00:00, 06:00, 12:00, 18:00):
#   0 */6 * * *  /path/to/repo/scripts/fangraphs_update.sh
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# Overridable so tests (and a second checkout) don't contend on one global
# lock/log. Production cron uses the defaults. Same pattern as
# scripts/mlb_daily_update.sh.
LOCK_FILE="${MLB_FANGRAPHS_LOCK_FILE:-/tmp/fangraphs_update.lock}"
LOG_FILE="${MLB_FANGRAPHS_LOG_FILE:-$REPO_DIR/logs/fangraphs_update.log}"

mkdir -p "$REPO_DIR/logs"

exec 200>"$LOCK_FILE"
if ! flock -n 200; then
    echo "$(date -u +%FT%TZ) fangraphs update already running, skipping this tick" >> "$LOG_FILE"
    exit 0
fi

cd "$REPO_DIR"
{
    echo "$(date -u +%FT%TZ) starting fangraphs update"
    "$REPO_DIR/.venv/bin/mlb" ingest fangraphs --mode update
    echo "$(date -u +%FT%TZ) finished fangraphs update"
} >> "$LOG_FILE" 2>&1
