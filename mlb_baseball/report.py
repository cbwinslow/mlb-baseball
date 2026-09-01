"""Builds the gold-layer reporting surface (ADR-057) -- gold.player_season,
gold.team_season, gold.division_standing -- from already-conformed `core`
tables plus a handful of `raw` tables `core` never bridged (raw.bref_batting/
pitching, raw.lahman_teams, raw.mlb_standing). Not a connector (no network
calls, no bootstrap()/update() split) and not part of conform.py or
model/__init__.py's own run() sequencing -- this is a separate, later stage:
"take what conform.py and model/ have already built and shape it for direct
per-entity lookup," the same relationship conform.py itself has to the
connectors underneath it. See ADR-057 for the full reasoning (materialized
vs. view, grain choices, why nothing here gets a real FK to core.player/
core.team).

`mlb report` runs this module explicitly. It is deliberately not folded into
`mlb conform` or `mlb predict`: a researcher can rebuild these final-season
aggregates without making a core rebuild or prediction run do unrelated work.
`mlb doctor` includes this stage's health checks.

Full truncate-and-rebuild every run, not incremental -- same reasoning as
conform.py itself: at this row count (tens of thousands of player-seasons,
low thousands of team-seasons/division-standings), a full rebuild is fast
and there's no meaningful "what changed" for a cross-source join to diff
against. Run this after `mlb conform` and `mlb predict` (needs `core.player`/
`core.team`/`core.player_war`/`core.standing` already populated, and
`gold.team_season`'s own park_factor pass must run before its woba/wrc_plus
pass -- see run()'s own ordering comment).
"""

import psycopg

from mlb_baseball.db import fetch_one, get_connection
from mlb_baseball.health import Check, check_join_coverage, check_table_has_rows
from mlb_baseball.ingest import track_run
from mlb_baseball.model.offense import W_1B, W_2B, W_3B, W_HBP, W_HR, W_UBB, WOBA_SCALE
from mlb_baseball.model.war import _BREF_TO_RETRO
from mlb_baseball.sql import read_sql

SOURCE = "report"

PARK_FACTOR_TRAILING_SEASONS = 3


def _check_prerequisites(conn: psycopg.Connection) -> None:
    """Same "fail loud with an actionable message, not a confusing mid-join
    error" contract as conform.py's own _check_prerequisites -- core.player/
    core.team/core.standing are always core migration output (never empty on
    a real, conformed database), so an empty one here means `mlb conform`
    genuinely hasn't run yet, not a real data gap."""
    with conn.cursor() as cur:
        for table in ("core.player", "core.team", "core.standing"):
            cur.execute(f"SELECT count(*) FROM {table}")
            (count,) = fetch_one(cur)
            if count == 0:
                raise RuntimeError(
                    f"report: {table} is empty -- run `mlb conform` before `mlb report`"
                )


# ---------------------------------------------------------------------------
# gold.player_season
# ---------------------------------------------------------------------------

# raw.bref_batting/raw.bref_pitching are text-typed (see mlb_baseball/
# connectors/bref.py) -- NULLIF(..., '') guards blank cells (e.g. a
# relief pitcher with no decisions has blank w/l/sv), same pattern
# conform.py uses throughout.
_BUILD_BATTING_SQL = """
WITH war_sum AS (
    SELECT player_id, season, sum(war) AS war, sum(waa) AS waa
    FROM core.player_war
    WHERE is_pitcher = false
    GROUP BY player_id, season
)
INSERT INTO gold.player_season (
    player_id, season, is_pitcher, player_name, team, games,
    pa, ab, doubles, triples, rbi, hbp, sb, cs, avg, obp, slg, ops,
    r, h, bb, so, hr, war, waa
)
SELECT
    p.id, b._season::integer, false, b.name, b.tm,
    NULLIF(b.g, '')::numeric::integer,
    NULLIF(b.pa, '')::numeric::integer, NULLIF(b.ab, '')::numeric::integer,
    NULLIF(b.n2b, '')::numeric::integer, NULLIF(b.n3b, '')::numeric::integer,
    NULLIF(b.rbi, '')::numeric::integer, NULLIF(b.hbp, '')::numeric::integer,
    NULLIF(b.sb, '')::numeric::integer, NULLIF(b.cs, '')::numeric::integer,
    NULLIF(b.ba, '')::numeric, NULLIF(b.obp, '')::numeric,
    NULLIF(b.slg, '')::numeric, NULLIF(b.ops, '')::numeric,
    NULLIF(b.r, '')::numeric::integer, NULLIF(b.h, '')::numeric::integer,
    NULLIF(b.bb, '')::numeric::integer, NULLIF(b.so, '')::numeric::integer,
    NULLIF(b.hr, '')::numeric::integer,
    ws.war, ws.waa
FROM raw.bref_batting b
JOIN core.player p ON p.mlbam_id = b.mlbid
LEFT JOIN war_sum ws ON ws.player_id = p.id AND ws.season = b._season::integer
"""

_BUILD_PITCHING_SQL = """
WITH war_sum AS (
    SELECT player_id, season, sum(war) AS war, sum(waa) AS waa
    FROM core.player_war
    WHERE is_pitcher = true
    GROUP BY player_id, season
)
INSERT INTO gold.player_season (
    player_id, season, is_pitcher, player_name, team, games,
    gs, w, l, sv, ip, er, era, whip, so9,
    r, h, bb, so, hr, war, waa
)
SELECT
    p.id, b._season::integer, true, b.name, b.tm,
    NULLIF(b.g, '')::numeric::integer,
    NULLIF(b.gs, '')::numeric::integer, NULLIF(b.w, '')::numeric::integer,
    NULLIF(b.l, '')::numeric::integer,
    NULLIF(b.sv, '')::numeric::integer, NULLIF(b.ip, '')::numeric,
    NULLIF(b.er, '')::numeric::integer,
    NULLIF(b.era, '')::numeric, NULLIF(b.whip, '')::numeric, NULLIF(b.so9, '')::numeric,
    NULLIF(b.r, '')::numeric::integer, NULLIF(b.h, '')::numeric::integer,
    NULLIF(b.bb, '')::numeric::integer, NULLIF(b.so, '')::numeric::integer,
    NULLIF(b.hr, '')::numeric::integer,
    ws.war, ws.waa
FROM raw.bref_pitching b
JOIN core.player p ON p.mlbam_id = b.mlbid
LEFT JOIN war_sum ws ON ws.player_id = p.id AND ws.season = b._season::integer
"""


def _build_player_season(conn: psycopg.Connection) -> int:
    total = 0
    for table, sql in (
        ("raw.bref_batting", _BUILD_BATTING_SQL),
        ("raw.bref_pitching", _BUILD_PITCHING_SQL),
    ):
        try:
            with conn.transaction(), conn.cursor() as cur:
                cur.execute(sql)
                total += cur.rowcount
        except psycopg.errors.UndefinedTable:
            print(f"report: {table} not present yet -- skipping gold.player_season")
    return total


# ---------------------------------------------------------------------------
# gold.team_season
# ---------------------------------------------------------------------------

# raw.lahman_teams.teamidretro matches core.team.retro_team_id exactly for
# every current team except the Athletics' 2025 relocation ('ATH', bare,
# same gap conform.py's own _TEAM_ALIAS_SEED documents for Kalshi/
# Polymarket) -- remapped inline here rather than touching the shared seed
# list, the same "small, local, cheap fix" call oaa.py's own 3-name remap
# already made for a different source's team-name quirk.
_BUILD_TEAM_SEASON_BASE_SQL = """
INSERT INTO gold.team_season (
    team_id, season, team_city, team_nickname, league,
    wins, losses, win_pct, runs, runs_allowed, hr, era
)
SELECT
    t.id, lt.yearid::integer, t.city, t.nickname, NULLIF(lt.lgid, ''),
    NULLIF(lt.w, '')::numeric::integer, NULLIF(lt.l, '')::numeric::integer,
    CASE WHEN NULLIF(lt.w, '')::numeric + NULLIF(lt.l, '')::numeric > 0
        THEN round(
            NULLIF(lt.w, '')::numeric / (NULLIF(lt.w, '')::numeric + NULLIF(lt.l, '')::numeric), 3
        )
    END,
    NULLIF(lt.r, '')::numeric::integer, NULLIF(lt.ra, '')::numeric::integer,
    NULLIF(lt.hr, '')::numeric::integer, NULLIF(lt.era, '')::numeric
FROM raw.lahman_teams lt
JOIN core.team t
    ON t.retro_team_id = (CASE WHEN lt.teamidretro = 'ATH' THEN 'OAK' ELSE lt.teamidretro END)
    AND lt.yearid::integer BETWEEN t.first_year AND t.last_year
WHERE lt.teamidretro IS NOT NULL AND lt.teamidretro != ''
  -- A handful of Negro League teams (e.g. Toledo Crawfords, 1939) appear
  -- twice for the same (teamidretro, yearid) under two different league
  -- affiliations (NAL/NN2) -- a genuine mid-season league-switch case, not
  -- a data error. Combining the two rows' W/L/R/RA/HR/ERA would guess at
  -- a merge this project has no source authority for, so this leaves both
  -- ambiguous rows out entirely -- same "leave it out, don't guess"
  -- precedent as core.game.game_pk's own backfill.
  AND (
      SELECT count(*) FROM raw.lahman_teams dup
      WHERE dup.teamidretro = lt.teamidretro AND dup.yearid = lt.yearid
  ) = 1
"""


def _build_team_season_base(conn: psycopg.Connection) -> int:
    try:
        with conn.transaction(), conn.cursor() as cur:
            cur.execute(_BUILD_TEAM_SEASON_BASE_SQL)
            return cur.rowcount
    except psycopg.errors.UndefinedTable:
        print("report: raw.lahman_teams not present yet -- skipping gold.team_season")
        return 0


# Trailing 3-year park factor, same methodology as mlb_baseball/model/
# park.py (see that module's own docstring for the sabermetric definition)
# but keyed directly off core.game/gold.team_season's own (team, season)
# universe rather than gold.game_feature's -- this reporting table has no
# dependency on the predictive feature store at all. Must run before
# _compute_woba (below), which reads park_factor back off gold.team_season
# to finish wrc_plus.
_COMPUTE_PARK_FACTOR_SQL = """
WITH home_splits AS (
    SELECT home_team_id AS team_id, season, venue_id,
        count(*) AS games, sum(home_score + away_score) AS runs
    FROM core.game
    WHERE game_type = 'regular' AND home_score IS NOT NULL
        AND away_score IS NOT NULL AND venue_id IS NOT NULL
    GROUP BY home_team_id, season, venue_id
),
road_splits AS (
    SELECT away_team_id AS team_id, season,
        count(*) AS games, sum(home_score + away_score) AS runs
    FROM core.game
    WHERE game_type = 'regular' AND home_score IS NOT NULL AND away_score IS NOT NULL
    GROUP BY away_team_id, season
),
team_season_pf AS (
    SELECT h.team_id, h.season,
        (h.runs::numeric / NULLIF(h.games, 0)) AS home_rate,
        (r.runs::numeric / NULLIF(r.games, 0)) AS road_rate
    FROM home_splits h
    JOIN road_splits r ON r.team_id = h.team_id AND r.season = h.season
),
team_trailing AS (
    SELECT gts.team_id, gts.season AS target_season,
        avg(100.0 * b.home_rate / NULLIF(b.road_rate, 0)) AS park_factor
    FROM gold.team_season gts
    JOIN team_season_pf b ON b.team_id = gts.team_id
        AND b.season BETWEEN gts.season - %(trailing_seasons)s AND gts.season - 1
    GROUP BY gts.team_id, gts.season
)
UPDATE gold.team_season ts
SET park_factor = tt.park_factor
FROM team_trailing tt
WHERE ts.team_id = tt.team_id AND ts.season = tt.target_season
"""


def _compute_park_factor(conn: psycopg.Connection) -> int:
    with conn.cursor() as cur:
        cur.execute(_COMPUTE_PARK_FACTOR_SQL, {"trailing_seasons": PARK_FACTOR_TRAILING_SEASONS})
        return cur.rowcount


# True season-final team wOBA/wRC+ -- NOT a read of gold.game_feature's own
# home_woba/away_woba (deliberately leakage-free, point-in-time-entering-
# each-game values that never include that game's own contribution -- see
# mlb_baseball/model/offense.py's module docstring). This recomputes the
# same formula/constants (imported, not copied, so the two can never drift
# independently) over an entire season's worth of raw.retrosheet_event
# rows at once -- a genuine "what did the team actually do that season"
# aggregate. Same 1910-2025 raw.retrosheet_event coverage gap as
# offense.py itself; no live 2026 equivalent built here (offense.py's own
# compute_live() exists for the predictive feature, but wiring an
# analogous version for this reporting table is real, separate follow-up
# work -- see ADR-057's "Revisit if").
_COMPUTE_WOBA_SQL = """
WITH regular_games AS (
    SELECT g.id AS game_id, g.season, g.retro_game_id, g.home_team_id, g.away_team_id
    FROM core.game g WHERE g.game_type = 'regular'
),
team_game_stats AS (
    SELECT
        rg.game_id, rg.season,
        CASE WHEN re.bat_home_id = '1' THEN rg.home_team_id ELSE rg.away_team_id END AS team_id,
        count(*) FILTER (WHERE re.event_cd = '14') AS ubb,
        count(*) FILTER (WHERE re.event_cd = '16') AS hbp,
        count(*) FILTER (WHERE re.event_cd = '20') AS b1,
        count(*) FILTER (WHERE re.event_cd = '21') AS b2,
        count(*) FILTER (WHERE re.event_cd = '22') AS b3,
        count(*) FILTER (WHERE re.event_cd = '23') AS hr,
        count(*) FILTER (WHERE re.ab_fl = 'T') AS ab,
        count(*) FILTER (WHERE re.sf_fl = 'T') AS sf
    FROM regular_games rg
    JOIN raw.retrosheet_gameinfo gi ON gi.gid = rg.retro_game_id AND lower(gi.gametype) = 'regular'
    JOIN raw.retrosheet_event re ON re.game_id = rg.retro_game_id
    GROUP BY rg.game_id, rg.season,
        CASE WHEN re.bat_home_id = '1' THEN rg.home_team_id ELSE rg.away_team_id END
),
team_season_totals AS (
    SELECT team_id, season,
        sum(ubb) AS ubb, sum(hbp) AS hbp, sum(b1) AS b1, sum(b2) AS b2, sum(b3) AS b3,
        sum(hr) AS hr, sum(ab) AS ab, sum(sf) AS sf
    FROM team_game_stats
    GROUP BY team_id, season
),
team_woba AS (
    SELECT team_id, season,
        CASE WHEN (ab + ubb + sf + hbp) > 0 THEN
            (%(w_ubb)s * ubb + %(w_hbp)s * hbp + %(w_1b)s * b1
                + %(w_2b)s * b2 + %(w_3b)s * b3 + %(w_hr)s * hr)
            / (ab + ubb + sf + hbp)
        END AS woba
    FROM team_season_totals
),
league_woba AS (
    SELECT season,
        CASE WHEN sum(ab + ubb + sf + hbp) > 0 THEN
            (%(w_ubb)s * sum(ubb) + %(w_hbp)s * sum(hbp) + %(w_1b)s * sum(b1)
                + %(w_2b)s * sum(b2) + %(w_3b)s * sum(b3) + %(w_hr)s * sum(hr))
            / sum(ab + ubb + sf + hbp)
        END AS woba
    FROM team_season_totals
    GROUP BY season
)
UPDATE gold.team_season ts
SET
    woba = tw.woba,
    wrc_plus = CASE
        WHEN tw.woba IS NOT NULL AND lw.woba IS NOT NULL AND ts.park_factor IS NOT NULL
        THEN (((tw.woba - lw.woba) / %(woba_scale)s) + 1) / (ts.park_factor / 100.0) * 100
    END
FROM team_woba tw
JOIN league_woba lw ON lw.season = tw.season
WHERE ts.team_id = tw.team_id AND ts.season = tw.season
"""


def _compute_woba(conn: psycopg.Connection) -> int:
    with conn.cursor() as cur:
        cur.execute("SELECT to_regclass('raw.retrosheet_event')")
        (exists,) = fetch_one(cur)
        if not exists:
            return 0
        cur.execute(
            _COMPUTE_WOBA_SQL,
            {
                "w_ubb": W_UBB,
                "w_hbp": W_HBP,
                "w_1b": W_1B,
                "w_2b": W_2B,
                "w_3b": W_3B,
                "w_hr": W_HR,
                "woba_scale": WOBA_SCALE,
            },
        )
        return cur.rowcount


# Team WAR, summed across every core.player_war row for that team-season
# (both batting and pitching stints) -- reuses mlb_baseball.model.war's own
# _BREF_TO_RETRO crosswalk (imported, not duplicated -- see that module's
# docstring for why bref's team codes and Retrosheet's genuinely differ).
# Same "current 30 teams only" limitation war.py itself already documents.
_COMPUTE_WAR_SQL = """
WITH team_war AS (
    SELECT team_code, season, sum(war) AS total_war
    FROM core.player_war
    WHERE team_code IS NOT NULL
    GROUP BY team_code, season
),
bref_map (bref_code, retro_code) AS (VALUES {values_clause}),
team_war_resolved AS (
    SELECT t.id AS team_id, tw.season, tw.total_war
    FROM team_war tw
    JOIN bref_map bm ON bm.bref_code = tw.team_code
    JOIN core.team t ON t.retro_team_id = bm.retro_code
        AND tw.season BETWEEN t.first_year AND t.last_year
)
UPDATE gold.team_season ts
SET war = twr.total_war
FROM team_war_resolved twr
WHERE ts.team_id = twr.team_id AND ts.season = twr.season
"""


def _compute_war(conn: psycopg.Connection) -> int:
    values_clause = ", ".join(f"('{bref}', '{retro}')" for bref, retro in _BREF_TO_RETRO.items())
    with conn.cursor() as cur:
        cur.execute(_COMPUTE_WAR_SQL.format(values_clause=values_clause))
        return cur.rowcount


# ---------------------------------------------------------------------------
# gold.division_standing
# ---------------------------------------------------------------------------

# core.standing (1969+) is the base; raw.mlb_standing (the same underlying
# source core.standing itself was built from -- see conform.py's
# _build_standings) is joined back in only for elim_num/wc_elim_num, the
# two columns that never made it into core.standing's own schema. No
# UndefinedTable guard here, unlike _build_player_season/_build_team_
# season_base: core.standing can only have rows at all if conform.py's own
# _build_standings already read them out of raw.mlb_standing, so a
# populated core.standing structurally guarantees raw.mlb_standing exists
# too -- the same "guaranteed present, no guard needed" reasoning war.py
# itself uses for core.player_war, just one join hop further away.
_BUILD_DIVISION_STANDING_SQL = """
INSERT INTO gold.division_standing (
    team_id, season, team_city, team_nickname, division, div_rank,
    wins, losses, win_pct, games_back, wildcard_rank, wildcard_games_back,
    league_rank, sport_rank, elim_num, wildcard_elim_num
)
SELECT
    s.team_id, s.season, t.city, t.nickname, s.division, s.div_rank,
    s.wins, s.losses,
    CASE WHEN s.wins + s.losses > 0
        THEN round(s.wins::numeric / (s.wins + s.losses), 3)
    END,
    s.games_back, s.wildcard_rank, s.wildcard_games_back, s.league_rank, s.sport_rank,
    ms.elim_num, ms.wc_elim_num
FROM core.standing s
JOIN core.team t ON t.id = s.team_id
LEFT JOIN raw.mlb_standing ms
    ON ms.team_id::integer = t.mlb_team_id AND ms._season::integer = s.season
"""


# ---------------------------------------------------------------------------
# gold.batting_game  (grain-complete statistic backbone, Plan 03B)
# ---------------------------------------------------------------------------

_BATTING_GAME_SQL = read_sql("batting_game_build.sql")


def _build_batting_game(conn: psycopg.Connection) -> int:
    """Rebuild gold.batting_game from raw.retrosheet_event. Degrades
    gracefully when the Retrosheet event table has not been ingested yet --
    same posture as _build_player_season with raw.bref_*. The savepoint
    (`conn.transaction()`) keeps an UndefinedTable here from rolling back the
    other builders' work in the shared run() transaction."""
    try:
        with conn.transaction(), conn.cursor() as cur:
            cur.execute("TRUNCATE gold.batting_game")
            cur.execute(_BATTING_GAME_SQL, {"season": None})
            cur.execute("SELECT count(*) FROM gold.batting_game")
            (count,) = fetch_one(cur)
        return count
    except psycopg.errors.UndefinedTable:
        print("report: raw.retrosheet_event not present yet -- skipping gold.batting_game")
        return 0


def _build_division_standing(conn: psycopg.Connection) -> int:
    with conn.transaction(), conn.cursor() as cur:
        cur.execute(_BUILD_DIVISION_STANDING_SQL)
        return cur.rowcount


def run() -> dict[str, int]:
    with get_connection() as conn, track_run(conn, SOURCE, "bootstrap") as result:
        _check_prerequisites(conn)
        # No cross-table FK graph to worry about here (see migration
        # 0030's own comment on why these tables carry no FK at all), so a
        # plain per-table TRUNCATE is enough -- no consolidated multi-table
        # statement needed the way conform.py's run() requires for core's
        # own FK-linked tables.
        with conn.cursor() as cur:
            cur.execute("TRUNCATE gold.player_season, gold.team_season, gold.division_standing")
        counts = {"gold.player_season": _build_player_season(conn)}
        counts["gold.team_season"] = _build_team_season_base(conn)
        # Ordering matters: park_factor must be set before _compute_woba
        # runs (wrc_plus reads ts.park_factor back off the row _compute_
        # park_factor just wrote), and both need the base INSERT above to
        # have already established the (team, season) row universe.
        _compute_park_factor(conn)
        _compute_woba(conn)
        _compute_war(conn)
        counts["gold.division_standing"] = _build_division_standing(conn)
        counts["gold.batting_game"] = _build_batting_game(conn)
        conn.commit()
        result["rows"] = sum(counts.values())
    return counts


def health_check() -> list[Check]:
    return [
        check_table_has_rows("gold.player_season"),
        check_table_has_rows("gold.team_season"),
        check_table_has_rows("gold.division_standing"),
        # tolerance=0: every raw.bref_batting/pitching row with a resolvable
        # mlbid should produce exactly one gold.player_season row -- the
        # inner JOIN in _build_player_season already excludes the ~0.5%
        # unresolved rows (confirmed against production, see ADR-057), so
        # this check's own "expected" side excludes them the same way, not
        # a stricter bar than the build logic itself can actually clear.
        check_join_coverage(
            "raw.bref_batting rows with a resolvable player get a gold.player_season row",
            "SELECT count(*) FROM gold.player_season WHERE is_pitcher = false",
            """
            SELECT count(*) FROM raw.bref_batting b
            JOIN core.player p ON p.mlbam_id = b.mlbid
            """,
            tolerance=0,
        ),
        check_join_coverage(
            "raw.bref_pitching rows with a resolvable player get a gold.player_season row",
            "SELECT count(*) FROM gold.player_season WHERE is_pitcher = true",
            """
            SELECT count(*) FROM raw.bref_pitching b
            JOIN core.player p ON p.mlbam_id = b.mlbid
            """,
            tolerance=0,
        ),
        # tolerance=449: confirmed directly against production, not a round
        # number -- every gap is a pre-1969 Negro League team Lahman's
        # newer release includes (e.g. Cuban X Giants, Brooklyn Royal
        # Giants) that core.team's Retrosheet-sourced universe has no
        # matching row for at all, same class of historical-coverage gap
        # this project already accepts elsewhere (see retrosheet_box's own
        # Negro League scope notes). Modern era (1969+) resolves 1587/1588
        # -- effectively complete.
        check_join_coverage(
            "raw.lahman_teams rows with a resolvable team get a gold.team_season row",
            "SELECT count(*) FROM gold.team_season",
            """
            SELECT count(*) FROM raw.lahman_teams lt
            JOIN core.team t
                ON t.retro_team_id = (
                    CASE WHEN lt.teamidretro = 'ATH' THEN 'OAK' ELSE lt.teamidretro END
                )
                AND lt.yearid::integer BETWEEN t.first_year AND t.last_year
            WHERE lt.teamidretro IS NOT NULL AND lt.teamidretro != ''
            """,
            tolerance=449,
        ),
        check_join_coverage(
            "core.standing rows get a gold.division_standing row",
            "SELECT count(*) FROM gold.division_standing",
            "SELECT count(*) FROM core.standing",
            tolerance=0,
        ),
        check_table_has_rows("gold.batting_game"),
        # tolerance=0: every (game, batter) pair with a completed plate
        # appearance and a resolvable core.player should produce exactly one
        # gold.batting_game row. The "expected" side mirrors the build's own
        # inner JOIN to core.player and its HAVING pa > 0 filter, so this is
        # not a stricter bar than the builder can clear.
        check_join_coverage(
            "raw.retrosheet_event (game, batter) pairs with a PA and a resolvable player "
            "get a gold.batting_game row",
            "SELECT count(*) FROM gold.batting_game",
            """
            SELECT count(*) FROM (
                SELECT re.game_id, re.bat_id
                FROM raw.retrosheet_event re
                JOIN core.game g ON g.retro_game_id = re.game_id AND lower(g.game_type) = 'regular'
                JOIN raw.retrosheet_gameinfo gi ON gi.gid = g.retro_game_id
                JOIN core.player p ON p.retro_id = re.bat_id
                WHERE re.bat_id IS NOT NULL AND re.bat_id <> ''
                GROUP BY re.game_id, re.bat_id
                HAVING count(*) FILTER (WHERE re.bat_event_fl = 'T') > 0
            ) s
            """,
            tolerance=0,
        ),
    ]
