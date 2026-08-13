"""Team prior offense/defense (ADR-061, Plan 03G admission queue
OFF-01 OBP, OFF-02 SLG/ISO, OFF-03 BB%/K%, OFF-08/DEF-01 run
environment). Same point-in-time-safe, no-leakage shape as team wOBA
(mlb_baseball/model/offense.py, ADR-036): every rate is a rolling,
within-season value computed only from games strictly before the one
it's attached to.

compute() reconstructs OBP/SLG/ISO/BB%/K% from raw.retrosheet_event's
per-play data using the same event_cd mapping already confirmed and
used elsewhere in this codebase (3=K, 14/15=UBB/IBB, 16=HBP, 20/21/22/23
=1B/2B/3B/HR -- see mlb_baseball/model/starter.py and offense.py module
docstrings). PA = AB+BB+HBP+SF; this excludes sacrifice bunts and
catcher's interference, which raw.retrosheet_event's ab_fl/sf_fl flags
don't separately expose here -- a real, documented gap, not a silent
approximation, same posture as offense.py's own wOBA denominator note.

compute_run_environment() needs no raw.retrosheet_event dependency at
all: home_runs_for/home_runs_allowed/home_wins/home_losses are already
entering-value sums set by features.build() (mlb_baseball/sql/
game_feature_rebuild.sql), so the per-game average is a pure derived
UPDATE off gold.game_feature's own already-computed columns -- the same
"read a prior step's output, don't recompute it" shape as
offense.py::compute_wrc_plus reading home_woba/park_factor.

Scope: the rate-stat half covers 1910-2025 only (raw.retrosheet_event's
known range); no 2026+ raw.mlb_playbyplay equivalent is built in this
package -- an honest, documented gap, same as starter.py/offense.py
before their own compute_live() follow-ups landed.

Verified against real data, not just the synthetic fixtures (same
discipline as starter.py's deGrom reconciliation, ADR-034): reconstructed
Ronald Acuna Jr.'s full real 2023 regular season directly from
raw.retrosheet_event (bat_id='acunr001', _season='2023', gametype
filtered to regular via raw.retrosheet_gameinfo) using this exact
event_cd/bat_event_fl/ab_fl/sf_fl formula, and compared against his
official MLB Stats API season line. Every value matched exactly: AB=643,
H=217 (35 2B, 4 3B, 41 HR), BB=80 (77 UBB + 3 IBB), HBP=9, SF=3, SO=84,
PA=735, OBP=.416, SLG=.596. This is the same per-plate-appearance
counting logic team_game_stats/rolling apply per (team, game) instead of
per player, so this also confirms the team-level aggregation is sound,
not just the event-code mapping in isolation.
"""

import psycopg

from mlb_baseball.db import fetch_one, get_connection
from mlb_baseball.health import Check
from mlb_baseball.sql import read_sql

# Min-sample gate (ADR-062): below these thresholds, OBP/SLG/ISO/BB%/K%
# are one bad-luck game away from a wildly misleading ratio (e.g. 1-for-1
# reads as a 1.000 OBP). No such gate existed anywhere in this codebase
# before this -- offense.py's wOBA documents the identical small-sample-
# noise risk in its health_check() docstring but deliberately does not
# filter it; this is new precedent, not a copy of an existing pattern.
# MIN_PA=10 (gates OBP/BB%/K%) and MIN_AB=8 (gates SLG/ISO) are scaled for
# this module's entering-value, point-in-time context -- an early-season
# team can easily have single-digit PA/AB entering its second or third
# game -- not a season-total batting-title qualification threshold (e.g.
# 3.1 PA/team-game), which would leave most of a season NULL. See
# mlb_baseball/sql/team_rate_retrosheet_update.sql for the gate's SQL and
# the PA/AB independence this implies (a team can clear one threshold
# while still below the other).
MIN_PA = 10
MIN_AB = 8


def compute_run_environment(conn: psycopg.Connection) -> int:
    with conn.cursor() as cur:
        cur.execute(read_sql("team_run_environment_update.sql"))
        return cur.rowcount


def compute(conn: psycopg.Connection) -> int:
    with conn.cursor() as cur:
        cur.execute("SELECT to_regclass('raw.retrosheet_event')")
        (exists,) = fetch_one(cur)
        if not exists:
            return 0
        cur.execute(
            read_sql("team_rate_retrosheet_update.sql"),
            {"min_pa": MIN_PA, "min_ab": MIN_AB},
        )
        return cur.rowcount


def health_check() -> list[Check]:
    """Bounds are mathematical ceilings (OBP/BB%/K% in [0,1]; SLG in [0,4],
    four total bases per at-bat; ISO in [0,3], since TB-H is always >= 0 and
    bounded by 3 total bases of extra credit per at-bat) except runs-for/
    allowed averages, which use a generous [0,30] to tolerate real
    early-season small-sample swings (same posture as offense.py's
    home_woba bound, which documents the identical tradeoff). The last two
    checks prove the min-sample gate's own contract (ADR-062: a populated
    OBP always had >= MIN_PA=10 prior PA) against real production data,
    not just the hand-built fixtures in tests/integration/
    test_model_team_rate.py -- this would catch the gate silently ceasing
    to apply (e.g. a future refactor reintroducing a bare `> 0` guard)."""
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT "
            "count(*) FILTER ("
            "  WHERE home_obp IS NOT NULL AND (home_obp < 0 OR home_obp > 1)"
            "), "
            "count(*) FILTER ("
            "  WHERE home_slg IS NOT NULL AND (home_slg < 0 OR home_slg > 4)"
            "), "
            "count(*) FILTER ("
            "  WHERE home_iso IS NOT NULL AND (home_iso < 0 OR home_iso > 3)"
            "), "
            "count(*) FILTER ("
            "  WHERE home_bb_pct IS NOT NULL AND (home_bb_pct < 0 OR home_bb_pct > 1)"
            "), "
            "count(*) FILTER ("
            "  WHERE home_k_pct IS NOT NULL AND (home_k_pct < 0 OR home_k_pct > 1)"
            "), "
            "count(*) FILTER ("
            "  WHERE home_runs_for_avg IS NOT NULL "
            "  AND (home_runs_for_avg < 0 OR home_runs_for_avg > 30)"
            "), "
            "count(*) FILTER ("
            "  WHERE home_runs_allowed_avg IS NOT NULL "
            "  AND (home_runs_allowed_avg < 0 OR home_runs_allowed_avg > 30)"
            "), "
            "count(*) FILTER ("
            "  WHERE home_obp IS NOT NULL AND (home_pa IS NULL OR home_pa < 10)"
            "), "
            "count(*) FILTER ("
            "  WHERE home_pa IS NOT NULL AND home_pa < 0"
            ") "
            "FROM gold.game_feature"
        )
        bad_obp, bad_slg, bad_iso, bad_bb, bad_k, bad_rf, bad_ra, bad_gate, bad_pa = fetch_one(cur)

    def _check(name: str, bad: int, bounds: str) -> Check:
        if bad:
            return Check(name, False, f"{bad} rows outside {bounds}")
        return Check(name, True, f"all computed values within {bounds}")

    return [
        _check("home_obp plausible range", bad_obp, "0-1"),
        _check("home_slg plausible range", bad_slg, "0-4"),
        _check("home_iso plausible range", bad_iso, "0-3"),
        _check("home_bb_pct plausible range", bad_bb, "0-1"),
        _check("home_k_pct plausible range", bad_k, "0-1"),
        _check("home_runs_for_avg plausible range", bad_rf, "0-30"),
        _check("home_runs_allowed_avg plausible range", bad_ra, "0-30"),
        _check("home_obp min-sample gate holds", bad_gate, "home_pa >= 10"),
        _check("home_pa plausible range", bad_pa, "0+"),
    ]
