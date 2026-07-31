#!/usr/bin/env bash
# Runs `mlb update` (every connector's update(), not just mlb_api) once a
# day to keep current-season aggregate data (Statcast leaderboards,
# Baseball-Reference season stats, Retrosheet's current-decade archive,
# etc.) fresh without re-running full historical bootstraps. See
# docs/ARCHITECTURE.md "Scheduling" and docs/DECISIONS.md ADR-023 for why
# this is a separate, coarser cadence from mlb_api_update.sh's 5-minute
# live-game loop rather than folding into it.
#
# Also runs `mlb conform` and `mlb predict` (ADR-032) after update --
# core/gold were never on any schedule before this (conform was a manual
# step per the README), and gold.game_feature/gold.prediction are only as
# fresh as core.game, so ingestion -> conform -> predict has to run as one
# ordered sequence, not conform/predict added to a separate cron entry
# that could run before ingestion finishes.
#
# Same flock + logging shape as mlb_api_update.sh, deliberately — one
# pattern for every scheduled job in this project, not a new one per script.
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOCK_FILE="/tmp/mlb_daily_update.lock"
LOG_FILE="$REPO_DIR/logs/mlb_daily_update.log"

mkdir -p "$REPO_DIR/logs"

exec 200>"$LOCK_FILE"
if ! flock -n 200; then
    echo "$(date -u +%FT%TZ) daily update already running, skipping this tick" >> "$LOG_FILE"
    exit 0
fi

cd "$REPO_DIR"
{
    echo "$(date -u +%FT%TZ) starting daily update"
    "$REPO_DIR/.venv/bin/mlb" update
    "$REPO_DIR/.venv/bin/mlb" conform
    "$REPO_DIR/.venv/bin/mlb" predict
    echo "$(date -u +%FT%TZ) finished daily update"
} >> "$LOG_FILE" 2>&1
