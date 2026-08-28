#!/usr/bin/env bash
# Daily pipeline: `mlb update` -> `mlb conform` -> `mlb predict`, run once a
# day to keep current-season aggregate data, core/gold, and
# gold.game_feature/gold.prediction fresh. See docs/ARCHITECTURE.md
# "Scheduling" and docs/DECISIONS.md ADR-023/ADR-032.
#
# Design (spec docs/superpowers/specs/2026-08-28-pipeline-performance-design.md,
# Phase 0): the three steps are ordered but INDEPENDENTLY tracked. A partial
# failure in `update` (e.g. one connector's network hiccup) must not silently
# skip `conform`/`predict` -- gold is still worth rebuilding from whatever
# raw data did land. Each step gets its own timestamped log lines and its
# own exit code; the script's overall exit code is non-zero if any step
# failed, but every step is attempted.
#
#   - `update` runs with `--skip mlb_api`: the every-5-minute
#     scripts/mlb_api_update.sh cron already keeps mlb_api fresh, and it
#     almost always holds the mlb_api ingestion lock at 06:00, so the daily
#     run's own mlb_api step failed with "another ingestion run is already
#     active" every single day (confirmed in logs/mlb_daily_update.log,
#     2026-08-21 onward).
#
# Same flock + logging shape as mlb_api_update.sh, deliberately.
set -uo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# Overridable so tests (and a second checkout) don't contend on one global
# lock/log. Production cron uses the defaults.
LOCK_FILE="${MLB_DAILY_LOCK_FILE:-/tmp/mlb_daily_update.lock}"
LOG_FILE="${MLB_DAILY_LOG_FILE:-$REPO_DIR/logs/mlb_daily_update.log}"
MLB="$REPO_DIR/.venv/bin/mlb"

mkdir -p "$REPO_DIR/logs"

exec 200>"$LOCK_FILE"
if ! flock -n 200; then
    echo "$(date -u +%FT%TZ) daily update already running, skipping this tick" >> "$LOG_FILE"
    exit 0
fi

cd "$REPO_DIR"

overall_rc=0

run_step() {
    # run_step <name> <command...>
    local name="$1"
    shift
    local start end rc
    start=$(date -u +%FT%TZ)
    echo "$start step $name: starting" >> "$LOG_FILE"
    "$@" >> "$LOG_FILE" 2>&1
    rc=$?
    end=$(date -u +%FT%TZ)
    if [ "$rc" -eq 0 ]; then
        echo "$end step $name: ok (started $start)" >> "$LOG_FILE"
    else
        echo "$end step $name: FAILED rc=$rc (started $start)" >> "$LOG_FILE"
        overall_rc=1
    fi
    return "$rc"
}

echo "$(date -u +%FT%TZ) starting daily update" >> "$LOG_FILE"

run_step update "$MLB" update --skip mlb_api
run_step conform "$MLB" conform
run_step predict "$MLB" predict

echo "$(date -u +%FT%TZ) finished daily update (overall rc=$overall_rc)" >> "$LOG_FILE"
exit "$overall_rc"
