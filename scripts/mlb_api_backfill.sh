#!/usr/bin/env bash
# Rebuild the complete MLB Stats API raw layer in its safe dependency order.
#
# This is an owner-triggered historical operation, not the five-minute live
# update job.  It is deliberately resumable: the analytics stage uses its
# item ledger/artifacts, and bootstrap's remaining endpoint families replace
# their natural season or catalog scopes.  The one lock covers both commands
# so a person or agent never overlaps this with a second full API backfill.
#
# Optional environment settings:
#   MLB_API_START_YEAR=1950 MLB_API_END_YEAR=2026 MLB_API_WORKERS=24
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOCK_FILE="/tmp/mlb_api_backfill.lock"
LOG_FILE="$REPO_DIR/logs/mlb_api_backfill.log"
START_YEAR="${MLB_API_START_YEAR:-1950}"
END_YEAR="${MLB_API_END_YEAR:-$(date +%Y)}"
WORKERS="${MLB_API_WORKERS:-24}"

mkdir -p "$REPO_DIR/logs"
exec 200>"$LOCK_FILE"
if ! flock -n 200; then
    echo "$(date -u +%FT%TZ) MLB API historical backfill already running; refusing overlap" \
        >> "$LOG_FILE"
    exit 1
fi

cd "$REPO_DIR"
{
    echo "$(date -u +%FT%TZ) starting MLB API backfill years=$START_YEAR-$END_YEAR workers=$WORKERS"
    "$REPO_DIR/.venv/bin/mlb" migrate
    "$REPO_DIR/.venv/bin/mlb" ingest mlb_api --stage analytics \
        --start-year "$START_YEAR" --end-year "$END_YEAR" --workers "$WORKERS"
    "$REPO_DIR/.venv/bin/mlb" ingest mlb_api --mode bootstrap
    "$REPO_DIR/.venv/bin/python" - <<'PY'
from mlb_baseball.db import get_connection

with get_connection() as conn:
    conn.autocommit = True
    with conn.cursor() as cur:
        for table in (
            "raw.mlb_win_prob",
            "raw.mlb_game_context",
            "raw.mlb_linescore",
            "raw.mlb_schedule",
        ):
            cur.execute(f"VACUUM (ANALYZE) {table}")
            print(f"vacuumed {table}")
PY
    "$REPO_DIR/.venv/bin/mlb" metrics --source mlb_api --window-minutes 60
    echo "$(date -u +%FT%TZ) finished MLB API backfill; run 'mlb doctor' before conformance"
} >> "$LOG_FILE" 2>&1
