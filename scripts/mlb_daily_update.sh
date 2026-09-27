#!/usr/bin/env bash
# Daily pipeline: `mlb migrate` -> `mlb update` -> `mlb conform` ->
# `mlb report` -> `mlb predict`, then a populated check, run once a day to keep
# current-season aggregate data, core/gold, and gold.game_feature/gold.prediction
# fresh. See docs/ARCHITECTURE.md "Scheduling" and docs/DECISIONS.md
# ADR-023/ADR-032 and openspec/changes/pipeline-freshness/.
#
# Why migrate first and report after conform (2026-09-27 incident): `conform`
# empties the gold backbone (it re-issues every core.game id) and only `report`
# refills it, and the code on disk can need a migration the database does not
# have yet. Without those two steps the backbone sat at 0 rows and `conform`
# crashed daily from 2026-09-24. Two steps gate others: a failed `migrate`
# stops everything after it (they would run against the old schema), and
# `report` runs only when `conform` succeeded.
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
    local start end rc t0 secs
    start=$(date -u +%FT%TZ)
    t0=$SECONDS
    echo "$start step $name: starting" >> "$LOG_FILE"
    "$@" >> "$LOG_FILE" 2>&1
    rc=$?
    end=$(date -u +%FT%TZ)
    secs=$((SECONDS - t0))
    if [ "$rc" -eq 0 ]; then
        echo "$end step $name: ok (started $start, took ${secs}s)" >> "$LOG_FILE"
    else
        echo "$end step $name: FAILED rc=$rc (started $start, took ${secs}s)" >> "$LOG_FILE"
        overall_rc=1
    fi
    return "$rc"
}

echo "$(date -u +%FT%TZ) starting daily update" >> "$LOG_FILE"

# Clear meta.ingestion_run rows left 'running' by a process that was killed
# (crash / host reboot / SIGKILL) before it could record a terminal state.
# `mlb doctor` reports these but is deliberately read-only, and `mlb
# repair-runs` is otherwise a manual step nobody runs -- so a stale row can
# make `check_last_run` look healthy forever. Only touches rows whose PID is
# provably dead (see ingest.reap_stale_runs). Exit code is ignored: a
# repair-runs failure must not skip the actual pipeline. (issue #180)
"$MLB" repair-runs >> "$LOG_FILE" 2>&1 || true

# Gate: later steps assume the current schema.
if ! run_step migrate "$MLB" migrate; then
    echo "$(date -u +%FT%TZ) migrate failed; skipping update, conform, report, predict" >> "$LOG_FILE"
    echo "$(date -u +%FT%TZ) finished daily update (overall rc=1)" >> "$LOG_FILE"
    exit 1
fi

run_step update "$MLB" update --skip mlb_api
# Gate: `report` refills what `conform` emptied; over a failed conform it
# would only rebuild empties.
if run_step conform "$MLB" conform; then
    run_step report "$MLB" report
else
    echo "$(date -u +%FT%TZ) conform failed; skipping report" >> "$LOG_FILE"
fi
run_step predict "$MLB" predict
# Last: every backbone relation must have rows, or the run exits non-zero.
run_step populated "$MLB" doctor --populated

echo "$(date -u +%FT%TZ) finished daily update (overall rc=$overall_rc)" >> "$LOG_FILE"
exit "$overall_rc"
