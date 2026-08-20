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
MIN_BIP = 8

# Plausible-range bounds for health_check() (see its own docstring for the
# rationale behind each). Named params passed into team_rate_health_check.sql
# and used to build the Check message below, rather than separate literals
# in the SQL and the message string -- issue #32's follow-up finding: if one
# changed without the other, the reported message would silently lie about
# the actual enforced bound.
RATE_MIN, RATE_MAX = 0, 1  # OBP/BABIP/BB%/K%
SLG_MIN, SLG_MAX = 0, 4
ISO_MIN, ISO_MAX = 0, 3
RUNS_MIN, RUNS_MAX = 0, 30


def compute_run_environment(conn: psycopg.Connection) -> int:
    with conn.cursor() as cur:
        cur.execute(read_sql("team_run_environment_update.sql"))
        return cur.rowcount


def compute(conn: psycopg.Connection) -> int:
    with conn.cursor() as cur:
        # Two-table dependency, two-table gate (issue #9 item 2): the SQL
        # below also joins raw.retrosheet_gameinfo. retrosheet_event and
        # retrosheet_gameinfo are landed by two different connectors
        # (retrosheet_event.py, retrosheet.py) -- a fresh clone that's only
        # bootstrapped one of them would otherwise hit an UndefinedTable
        # error here instead of the same clean "not ready yet, return 0"
        # every sibling module gives for its own single-table gate.
        cur.execute("SELECT to_regclass('raw.retrosheet_event')")
        (event_exists,) = fetch_one(cur)
        cur.execute("SELECT to_regclass('raw.retrosheet_gameinfo')")
        (gameinfo_exists,) = fetch_one(cur)
        if not event_exists or not gameinfo_exists:
            return 0
        cur.execute(
            read_sql("team_rate_retrosheet_update.sql"),
            {"min_pa": MIN_PA, "min_ab": MIN_AB, "min_bip": MIN_BIP},
        )
        return cur.rowcount


def health_check() -> list[Check]:
    """Bounds are mathematical ceilings (OBP/BB%/K%/BABIP in [0,1]; SLG in [0,4],
    four total bases per at-bat; ISO in [0,3], since TB-H is always >= 0 and
    bounded by 3 total bases of extra credit per at-bat) except runs-for/
    allowed averages, which use a generous [0,30] to tolerate real
    early-season small-sample swings (same posture as offense.py's
    home_woba bound, which documents the identical tradeoff). The gate
    checks (home/away "min-sample gate holds" and "pa plausible range")
    prove the min-sample gate's own contract (ADR-062/ADR-063: a populated
    OBP always had >= MIN_PA=10 prior PA) against real production data,
    not just the hand-built fixtures in tests/integration/
    test_model_team_rate.py -- this would catch the gate silently ceasing
    to apply (e.g. a future refactor reintroducing a bare `> 0` guard).
    Checked on both home and away sides (issue #9 item 3): the two go
    through the same formula but two different join legs, so an away-only
    join bug is a real, if unlikely, failure mode a home-only check can't
    surface. Every home_* check below (obp/slg/iso/babip/bb_pct/k_pct/
    runs_for_avg/runs_allowed_avg/min-sample gate/pa) has an away_*
    twin using the identical bound.

    The range checks above can only ever catch a value that's present but
    out of range -- a total join failure (e.g. a mismatched team_id) makes
    the columns NULL for every row instead, which IS NOT NULL excludes from
    the count. The coverage checks below close that gap (issue #32):
    home_pa/away_pa are the right target -- ungated (always populated
    whenever the join succeeds, unlike obp/slg/etc which can be legitimately
    NULL below MIN_PA/MIN_AB/MIN_BIP) and every other rate stat here rides
    on the same join, so once a team is "eligible" (reconstructed the same
    way team_rate_retrosheet_update.sql itself defines it -- at least one
    prior game that season with real Retrosheet event coverage), home_pa/
    away_pa must not be NULL."""
    with get_connection() as conn, conn.cursor() as cur:
        # REPEATABLE READ so the range query and the coverage query below
        # see one consistent snapshot of gold.game_feature -- otherwise a
        # concurrent feature rebuild committing between the two (default
        # READ COMMITTED gives each statement its own fresh snapshot) could
        # make them describe two different versions of the table, producing
        # a transient contradictory or false-clean result (PR #54 review).
        conn.isolation_level = psycopg.IsolationLevel.REPEATABLE_READ
        cur.execute(
            read_sql("team_rate_health_check.sql"),
            {
                "min_pa": MIN_PA,
                "rate_min": RATE_MIN,
                "rate_max": RATE_MAX,
                "slg_min": SLG_MIN,
                "slg_max": SLG_MAX,
                "iso_min": ISO_MIN,
                "iso_max": ISO_MAX,
                "runs_min": RUNS_MIN,
                "runs_max": RUNS_MAX,
            },
        )
        (
            bad_obp,
            bad_slg,
            bad_iso,
            bad_babip,
            bad_bb,
            bad_k,
            bad_rf,
            bad_ra,
            bad_gate,
            bad_pa,
            bad_away_obp,
            bad_away_slg,
            bad_away_iso,
            bad_away_babip,
            bad_away_bb,
            bad_away_k,
            bad_away_rf,
            bad_away_ra,
            bad_away_gate,
            bad_away_pa,
        ) = fetch_one(cur)

        # Coverage check needs raw.retrosheet_event/retrosheet_gameinfo to
        # exist (same two-table gate as compute() above) -- before either
        # table is bootstrapped, there's no eligible population to check
        # against, so 0 bad rows is the honest answer.
        cur.execute("SELECT to_regclass('raw.retrosheet_event')")
        (event_exists,) = fetch_one(cur)
        cur.execute("SELECT to_regclass('raw.retrosheet_gameinfo')")
        (gameinfo_exists,) = fetch_one(cur)
        if event_exists and gameinfo_exists:
            cur.execute(read_sql("team_rate_coverage_health_check.sql"))
            bad_home_pa_coverage, bad_away_pa_coverage = fetch_one(cur)
        else:
            bad_home_pa_coverage = bad_away_pa_coverage = 0

    def _check(name: str, bad: int, bounds: str) -> Check:
        if bad:
            return Check(name, False, f"{bad} rows outside {bounds}")
        return Check(name, True, f"all computed values within {bounds}")

    def _coverage_check(name: str, bad: int) -> Check:
        if bad:
            return Check(name, False, f"{bad} eligible rows have no computed value")
        return Check(name, True, "every eligible row has a computed value")

    rate_bounds = f"{RATE_MIN}-{RATE_MAX}"
    slg_bounds = f"{SLG_MIN}-{SLG_MAX}"
    iso_bounds = f"{ISO_MIN}-{ISO_MAX}"
    runs_bounds = f"{RUNS_MIN}-{RUNS_MAX}"

    return [
        _check("home_obp plausible range", bad_obp, rate_bounds),
        _check("home_slg plausible range", bad_slg, slg_bounds),
        _check("home_iso plausible range", bad_iso, iso_bounds),
        _check("home_babip plausible range", bad_babip, rate_bounds),
        _check("home_bb_pct plausible range", bad_bb, rate_bounds),
        _check("home_k_pct plausible range", bad_k, rate_bounds),
        _check("home_runs_for_avg plausible range", bad_rf, runs_bounds),
        _check("home_runs_allowed_avg plausible range", bad_ra, runs_bounds),
        _check("home_obp min-sample gate holds", bad_gate, f"home_pa >= {MIN_PA}"),
        _check("home_pa plausible range", bad_pa, "0+"),
        _check("away_obp plausible range", bad_away_obp, rate_bounds),
        _check("away_slg plausible range", bad_away_slg, slg_bounds),
        _check("away_iso plausible range", bad_away_iso, iso_bounds),
        _check("away_babip plausible range", bad_away_babip, rate_bounds),
        _check("away_bb_pct plausible range", bad_away_bb, rate_bounds),
        _check("away_k_pct plausible range", bad_away_k, rate_bounds),
        _check("away_runs_for_avg plausible range", bad_away_rf, runs_bounds),
        _check("away_runs_allowed_avg plausible range", bad_away_ra, runs_bounds),
        _check("away_obp min-sample gate holds", bad_away_gate, f"away_pa >= {MIN_PA}"),
        _check("away_pa plausible range", bad_away_pa, "0+"),
        _coverage_check("home_pa coverage", bad_home_pa_coverage),
        _coverage_check("away_pa coverage", bad_away_pa_coverage),
    ]
