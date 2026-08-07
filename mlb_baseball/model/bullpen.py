"""Bullpen quality and fatigue (ADR-039, docs/RESEARCH.md's
feature-engineering backlog item 7). Research consensus (InsidethePen
usage-tracking analysis) is direct: relievers now handle 40%+ of
innings, WHIP/K%/BB% predict bullpen betting value better than ERA, and
recent workload measurably reduces effectiveness independent of quality.

Team-level, not pitcher-level -- deliberately: which specific relievers
a manager uses today is an in-game decision made after the point this
feature is computed for (before first pitch), so a per-pitcher bullpen
composition feature would leak the very information it's trying to
predict around. Instead this rolls up every relief appearance (any
pitcher credited on a team's plays who wasn't that game's starter, via
resp_pit_id/resp_pit_start_fl -- same fields starter.py already
verified against Chadwick's docs) into a team aggregate, the same
point-in-time rolling shape as starter.py's k_pct/bb_pct: season-to-date,
strictly excluding the current game (ROWS BETWEEN UNBOUNDED PRECEDING
AND 1 PRECEDING).

Fatigue is a second, separate signal from quality: a trailing 3-calendar
-day count of outs recorded by the team's bullpen, a workload proxy for
how taxed the pen is entering today's game. 3 days chosen to match the
"pitches thrown in the last 5 days, back-to-back appearances" workload
window the research above describes, narrowed to what's cheaply and
unambiguously derivable at team grain from event data (a precise
per-pitcher pitch-count/back-to-back signal would need roster-level
appearance tracking this project doesn't have yet). Computed as a
window RANGE frame over one row per (team, calendar day) -- ADR-042
replaced an earlier lateral-join version (correct, but O(n^2): a fresh
scan of a team's whole history per team-game, 20+ minutes against full
production data) with this collapse-to-day-grain-first version, which
sidesteps the "RANGE frames treat doubleheaders' same-date peer rows
ambiguously" problem by construction -- collapsing to one row per
team-day first means there are no peer rows left to be ambiguous about.

Scope: raw.retrosheet_event covers 1910-2025 only, so compute() above
leaves quality/fatigue NULL for the live 2026 season on its own --
compute_live() (completed 2026 games) and compute_upcoming() (games that
haven't been played yet) close that gap from raw.mlb_playbyplay instead,
the same raw.mlb_playbyplay substitution starter.py/offense.py's own
compute_live() already made (ADR-046/051). FIP_CONSTANT reuses starter.py's
3.10 for the same reason (see that module's docstring) -- kept as its
own module-level constant here rather than importing starter's, since
a divergence in the two constants would be a deliberate future decision,
not an accident two modules should be forced to share.
"""

import psycopg

from mlb_baseball.db import fetch_one
from mlb_baseball.health import Check, check_join_coverage, check_totals_reconcile
from mlb_baseball.sql import read_sql

FIP_CONSTANT = 3.10
FATIGUE_WINDOW_DAYS = 3


def compute(conn: psycopg.Connection) -> int:
    with conn.cursor() as cur:
        cur.execute("SELECT to_regclass('raw.retrosheet_event')")
        (exists,) = fetch_one(cur)
        if not exists:
            return 0
        cur.execute(
            read_sql("team_bullpen_retrosheet_update.sql"),
            {"fip_constant": FIP_CONSTANT, "fatigue_days": FATIGUE_WINDOW_DAYS},
        )
        return cur.rowcount


def compute_live(conn: psycopg.Connection) -> int:
    with conn.cursor() as cur:
        cur.execute("SELECT to_regclass('raw.mlb_playbyplay')")
        (exists,) = fetch_one(cur)
        if not exists:
            return 0
        cur.execute(
            read_sql("team_bullpen_live_update.sql"),
            {"fip_constant": FIP_CONSTANT, "fatigue_days": FATIGUE_WINDOW_DAYS},
        )
        return cur.rowcount


# ADR-051: closes compute_live()'s own remaining gap -- it only ever
# backfills *completed* 2026 games (keyed off core.game, which never holds
# an unplayed game), same limitation ADR-046 documented for starter.py's
# own compute_live() before ADR-048 closed it with compute_probable().
#
# Deliberately NOT a reuse of starter.py's compute_probable() shape,
# despite both closing "the same kind of gap": bullpen quality/fatigue is
# team-level by design (see this module's own docstring on why -- which
# reliever pitches today is an in-game decision made after this feature is
# computed), so unlike an individual starting pitcher it never depends on
# any announcement at all. gold.game_feature.home_team_id/away_team_id are
# already resolved (core.team.id) by features.py for every upcoming row
# straight from raw.mlb_schedule -- no raw.mlb_probable, no core.player
# crosswalk, no "identity resolves but the rate might not" split the way
# starter.py's probable pitcher has. Every upcoming game gets a shot at
# resolving, gated only on whether the team has any qualifying prior 2026
# relief history to roll up.
#
# No team_game backbone here (unlike _LIVE_BUILD_SQL/_BUILD_SQL above): a
# correlated SUM() over relief_only naturally treats a qualifying game
# with zero relief outs as contributing 0, the same as an explicit
# backbone row would -- the only real difference is a team with *zero*
# qualifying games in a window (no relief_only rows at all) resolves NULL
# here instead of an explicit 0. Deliberately accepted as the "leave it
# NULL, don't guess" precedent already used throughout this project,
# rather than building a backbone this small, one-season query doesn't
# need for performance (unlike ADR-042's fix, which existed specifically
# for the 434K-team-game full-historical-scale problem).
def compute_upcoming(conn: psycopg.Connection) -> int:
    with conn.cursor() as cur:
        cur.execute("SELECT to_regclass('raw.mlb_playbyplay')")
        (exists,) = fetch_one(cur)
        if not exists:
            return 0
        cur.execute(
            read_sql("team_bullpen_upcoming_update.sql"),
            {"fip_constant": FIP_CONSTANT, "fatigue_days": FATIGUE_WINDOW_DAYS},
        )
        return cur.rowcount


# Shared by health_check()'s upcoming-coverage check below (ADR-051) --
# one row per (upcoming game, side), with the feature table's own
# resolved home/away_bullpen_fip attached per side. No core.player
# crosswalk involved anywhere here (unlike starter.py's own analogous
# check, see issue #5) -- bullpen identity is team_id straight from
# gold.game_feature, so that whole bug class doesn't apply to this check.
_UPCOMING_COVERAGE_CTE = """
WITH sided AS (
    SELECT f.id, f.game_date, f.home_team_id AS team_id, f.home_bullpen_fip AS resolved_fip
    FROM gold.game_feature f
    WHERE f.home_win IS NULL AND f.mlb_game_pk IS NOT NULL
    UNION ALL
    SELECT f.id, f.game_date, f.away_team_id, f.away_bullpen_fip
    FROM gold.game_feature f
    WHERE f.home_win IS NULL AND f.mlb_game_pk IS NOT NULL
)
"""

_UPCOMING_ACTUAL_SQL = (
    _UPCOMING_COVERAGE_CTE + "SELECT count(*) FROM sided WHERE resolved_fip IS NOT NULL"
)

# "Expected" here means "this team has at least one qualifying prior 2026
# relief appearance to roll up" -- same tolerance reasoning as starter.py's
# own probable-coverage check (ADR-048): a team's only qualifying prior
# game(s) can legitimately have zero relief outs recorded (e.g. a
# complete-game shutout), which correctly leaves fip NULL despite "having
# a game" by this check's own EXISTS test -- a real, understood edge case,
# not a bug to chase to zero.
_UPCOMING_EXPECTED_SQL = (
    _UPCOMING_COVERAGE_CTE
    + """
    SELECT count(*) FROM sided s
    WHERE EXISTS (
        SELECT 1 FROM core.game g
        JOIN raw.mlb_playbyplay pbp ON pbp.game_pk = g.game_pk
        WHERE g.game_type = 'regular' AND g.game_pk IS NOT NULL
            AND g.game_date < s.game_date
            AND (g.home_team_id = s.team_id OR g.away_team_id = s.team_id)
    )
    """
)


def health_check() -> list[Check]:
    """Internal consistency, not an external reconciliation: raw.
    bref_pitching has no team-season total rows to compare against (it's
    strictly per-player, and doesn't split a swingman's starts from
    their relief outings within a season), so unlike starter.py this
    can't validate against an independent source. Instead it checks the
    one thing that actually could be wrong here and would matter: that
    "relief" (every pitcher who wasn't that game's starter) and "starter"
    together are exhaustive and non-overlapping -- i.e. relief outs
    recorded per team-game plus that team's starter's own outs (both
    computed fresh here, not reused from gold.game_feature's stored
    rates) must exactly equal the team's total outs pitched that game,
    tolerance=0. A mismatch would mean a pitcher got mis-classified or
    double-counted, e.g. a bat_home_id or resp_pit_start_fl assumption
    breaking on some real row this wasn't checked against."""
    return [
        check_totals_reconcile(
            "bullpen/starter split: relief + starter outs vs team's total outs pitched",
            """
            WITH regular_games AS (
                SELECT g.id AS game_id, g.retro_game_id, g.home_team_id, g.away_team_id
                FROM core.game g WHERE g.game_type = 'regular'
            ),
            starters AS (
                SELECT rg.game_id,
                    max(re.resp_pit_id) FILTER (WHERE re.bat_home_id = '0') AS home_sp,
                    max(re.resp_pit_id) FILTER (WHERE re.bat_home_id = '1') AS away_sp
                FROM regular_games rg
                JOIN raw.retrosheet_gameinfo gi
                    ON gi.gid = rg.retro_game_id AND lower(gi.gametype) = 'regular'
                JOIN raw.retrosheet_event re ON re.game_id = rg.retro_game_id
                WHERE re.resp_pit_start_fl = 'T'
                GROUP BY rg.game_id
            ),
            team_pitcher_outs AS (
                SELECT rg.game_id,
                    CASE WHEN re.bat_home_id = '0'
                        THEN rg.home_team_id ELSE rg.away_team_id END AS team_id,
                    re.resp_pit_id AS pitcher_retro_id,
                    sum(re.event_outs_ct::numeric) AS outs
                FROM regular_games rg
                JOIN raw.retrosheet_gameinfo gi
                    ON gi.gid = rg.retro_game_id AND lower(gi.gametype) = 'regular'
                JOIN raw.retrosheet_event re ON re.game_id = rg.retro_game_id
                GROUP BY rg.game_id, rg.home_team_id, rg.away_team_id,
                    re.bat_home_id, re.resp_pit_id
            ),
            per_team_game AS (
                SELECT tpo.game_id, tpo.team_id, sum(tpo.outs) AS total_outs,
                    sum(tpo.outs) FILTER (WHERE tpo.pitcher_retro_id = CASE
                        WHEN tpo.team_id = rg.home_team_id THEN s.home_sp ELSE s.away_sp END
                    ) AS starter_outs,
                    sum(tpo.outs) FILTER (WHERE tpo.pitcher_retro_id IS DISTINCT FROM CASE
                        WHEN tpo.team_id = rg.home_team_id THEN s.home_sp ELSE s.away_sp END
                    ) AS relief_outs
                FROM team_pitcher_outs tpo
                JOIN regular_games rg ON rg.game_id = tpo.game_id
                JOIN starters s ON s.game_id = tpo.game_id
                GROUP BY tpo.game_id, tpo.team_id
            )
            SELECT game_id || '-' || team_id, total_outs,
                COALESCE(starter_outs, 0) + COALESCE(relief_outs, 0)
            FROM per_team_game
            """,
            tolerance=0,
        ),
        check_join_coverage(
            "upcoming games get a resolved bullpen feature",
            _UPCOMING_ACTUAL_SQL,
            _UPCOMING_EXPECTED_SQL,
            tolerance=5,
        ),
    ]
