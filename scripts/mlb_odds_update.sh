#!/usr/bin/env bash
# Runs `mlb ingest kalshi --mode update` and `mlb ingest polymarket --mode
# update` on a cron cadence so raw.kalshi_snapshot / raw.polymarket_snapshot
# (ADR-049 forward-looking price capture) accrue several pre-game snapshots a
# day instead of the single one the 06:00 daily job takes. `_build_market`'s
# `_latest_before(first_pitch)` pick (ADR-052 / ADR-267) then has a richer set
# to choose the leak-free pre-game price from.
#
# core.market itself only rebuilds on the full `mlb conform` (daily) -- this
# script deliberately does NOT run conform. It just keeps raw fresh.
#
# Same cron + flock rationale as mlb_api_update.sh (ADR-016). Two extra
# wrinkles vs that script:
#   * runs two connectors; a failure in one must not stop the other.
#   * mlb's own cross-workflow lock (ingest.py `_acquire_workflow_lock`)
#     rejects a run while the */5 mlb_api tick or the 06:00 conform/predict
#     holds it. That is expected contention, not an error -- treat it as a
#     skipped tick (exit 0), same as flock's own -n skip.
set -uo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOCK_FILE="/tmp/mlb_odds_update.lock"
LOG_FILE="$REPO_DIR/logs/mlb_odds_update.log"
MLB="$REPO_DIR/.venv/bin/mlb"
WORKFLOW_BUSY_RE='another ingestion or derived-data stage is active'

mkdir -p "$REPO_DIR/logs"

exec 200>"$LOCK_FILE"
if ! flock -n 200; then
    echo "$(date -u +%FT%TZ) odds update already running, skipping this tick" >> "$LOG_FILE"
    exit 0
fi

cd "$REPO_DIR"

run_source() {
    local source="$1" out rc
    out="$("$MLB" ingest "$source" --mode update 2>&1)"
    rc=$?
    if [ "$rc" -eq 0 ]; then
        echo "$(date -u +%FT%TZ) $source update: ok" >> "$LOG_FILE"
    elif echo "$out" | grep -q "$WORKFLOW_BUSY_RE"; then
        echo "$(date -u +%FT%TZ) $source update: skipped (mlb workflow lock held)" >> "$LOG_FILE"
    else
        echo "$(date -u +%FT%TZ) $source update: FAILED rc=$rc" >> "$LOG_FILE"
        echo "$out" | tail -20 >> "$LOG_FILE"
        return "$rc"
    fi
}

overall=0
echo "$(date -u +%FT%TZ) starting odds update" >> "$LOG_FILE"
run_source kalshi     || overall=1
run_source polymarket || overall=1
echo "$(date -u +%FT%TZ) finished odds update (rc=$overall)" >> "$LOG_FILE"
exit "$overall"
