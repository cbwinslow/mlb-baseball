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
from psycopg import sql

from mlb_baseball.db import fetch_one, get_connection
from mlb_baseball.health import (
    Check,
    check_join_coverage,
    check_no_rows,
    check_table_has_rows,
)
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
    for table, build_sql in (
        ("raw.bref_batting", _BUILD_BATTING_SQL),
        ("raw.bref_pitching", _BUILD_PITCHING_SQL),
    ):
        try:
            with conn.transaction(), conn.cursor() as cur:
                cur.execute(build_sql)
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
# gold.batting_game / gold.pitching_game  (grain-complete backbone, Plan 03B)
# ---------------------------------------------------------------------------

_BATTING_GAME_SQL = read_sql("batting_game_build.sql")
_PITCHING_GAME_SQL = read_sql("pitching_game_build.sql")
# 2026-onward game grain, from MLB's official per-game box score
# (raw.mlb_boxscore_batting / _pitching) -- Retrosheet publishes no event file
# for the in-progress season (backbone-2026-source). Wired alongside the
# Retrosheet builders as a two-source list in run(); the g.season <= 2025 /
# g.season >= 2026 bounds keep the two from ever writing the same key.
_BATTING_GAME_MLB_SQL = read_sql("batting_game_mlb_build.sql")
_PITCHING_GAME_MLB_SQL = read_sql("pitching_game_mlb_build.sql")
_BATTING_SEASON_SQL = read_sql("batting_season_build.sql")
_BATTING_TEAM_SQL = read_sql("batting_team_build.sql")
_PITCHING_SEASON_SQL = read_sql("pitching_season_build.sql")
_PITCHING_TEAM_SQL = read_sql("pitching_team_build.sql")
_BATTING_CAREER_SQL = read_sql("batting_career_build.sql")
_PITCHING_CAREER_SQL = read_sql("pitching_career_build.sql")
# Postseason relations (separate-postseason-stats / ADR-282) -- built from
# Lahman's own BattingPost / PitchingPost, kept entirely apart from the
# regular-season backbone above.
_BATTING_POSTSEASON_SQL = read_sql("batting_postseason_build.sql")
_PITCHING_POSTSEASON_SQL = read_sql("pitching_postseason_build.sql")
# FanGraphs reference lookups (fangraphs-conform Beat 1, ADR-290) -- two
# local_research-only lookups conformed from the raw.fangraphs_* landing tables
# (#173). Both skip cleanly on a database that never ingested FanGraphs.
_GOLD_FANGRAPHS_GUTS_SQL = read_sql("gold_fangraphs_guts.sql")
_GOLD_FANGRAPHS_PARK_FACTORS_SQL = read_sql("gold_fangraphs_park_factors.sql")
# Recognised Lahman postseason `round` codes: WS / NWS (Negro WS), CS / NNC /
# NSC (Negro championship), and the league-prefixed rounds -- [AN] league,
# optional [EWL] sub-division, then C(S) / DS<n> / WC<n> / DIV / P<n>.
_PS_ROUND_RE = r"^(WS|NWS|CS|NNC|NSC|[AN][EWL]?(C|CS|DS[0-9]|WC[0-9]?|DIV|P[0-9]))$"


def _build_backbone_relation(
    conn: psycopg.Connection,
    table: str,
    build_sql: str,
    *,
    source: str = "raw.retrosheet_event",
) -> int:
    """Truncate-and-rebuild one grain-backbone `gold` relation.

    Pre-checks that `source` exists and skips gracefully if it does not (same
    posture as `_build_player_season` with `raw.bref_*`) -- checking first,
    rather than TRUNCATE-then-catch, so a missing *source* table skips
    cleanly while a missing *target* table (migrations not run) still fails
    loudly. The game relations read `raw.retrosheet_event`; the season / team
    roll-ups read `gold.{batting,pitching}_game`; the career roll-ups read
    the season tables (all always present once migrated, so the pre-check is
    a no-op for them -- but keeps the one code path). The game / season /
    team builders take an optional `%(season)s` scope; the career builders
    don't (a career is every season). `{"season": None}` is passed
    unconditionally -- psycopg ignores an unused mapping key, so the career
    builders (which contain no placeholder) are unaffected. `table` and
    `source` are internal constants, not user input; `table` is still passed
    through `sql.Identifier` so the query is not built by string
    formatting."""
    schema, name = table.split(".", 1)
    ident = sql.Identifier(schema, name)
    with conn.cursor() as cur:
        cur.execute("SELECT to_regclass(%s)", (source,))
        (present,) = fetch_one(cur)
    if present is None:
        print(f"report: {source} not present yet -- skipping {table}")
        return 0
    # Savepoint so any failure in this builder can't roll back the other
    # builders' work in run()'s shared transaction, matching _build_player_season.
    with conn.transaction(), conn.cursor() as cur:
        cur.execute(sql.SQL("TRUNCATE {}").format(ident))
        cur.execute(build_sql, {"season": None})
        cur.execute(sql.SQL("SELECT count(*) FROM {}").format(ident))
        (count,) = fetch_one(cur)
    return count


def _build_backbone_relation_multi(
    conn: psycopg.Connection,
    table: str,
    builds: list[tuple[str, str]],
) -> int:
    """Truncate-and-rebuild one grain-backbone `gold` relation from more than
    one source.

    `builds` is an ordered list of `(build_sql, source_table)` pairs. Each
    source is pre-checked (same posture as `_build_backbone_relation`); the
    target is TRUNCATEd exactly once, then every build whose source table is
    present runs in order, appending its rows. Returns the final row count of
    `table` (the sum across the builds that ran).

    Used for `gold.batting_game` / `gold.pitching_game`, which are built from
    `raw.retrosheet_event` (<= 2025) and `raw.mlb_boxscore_*` (>= 2026). The
    season bound in each builder is the partition line, so the two never write
    the same `(game, player, team)` key. If a configured source is absent: on
    an empty target the rebuild proceeds from whatever's present (a fresh
    bootstrap that has one source but not the other); on a non-empty target
    the rebuild is skipped and the current count returned, so a source table
    that disappears can't TRUNCATE away rows only it produced. If every source
    is absent the target is left untouched and 0 is returned. `table` is an
    internal constant, passed through `sql.Identifier` all the same."""
    schema, name = table.split(".", 1)
    ident = sql.Identifier(schema, name)
    present: list[str] = []
    missing: list[str] = []
    for build_sql, source in builds:
        with conn.cursor() as cur:
            cur.execute("SELECT to_regclass(%s)", (source,))
            (regclass,) = fetch_one(cur)
        if regclass is None:
            missing.append(source)
        else:
            present.append(build_sql)
    if not present:
        return 0
    if missing:
        # A configured source table is gone. Rebuilding from only what's left
        # would TRUNCATE the target and silently drop the missing source's
        # rows (e.g. the 2026+ box-score rows if raw.mlb_boxscore_* vanished).
        # Only safe to proceed when the target is still empty -- a fresh
        # bootstrap that has ingested one source but not the other yet.
        with conn.cursor() as cur:
            cur.execute(sql.SQL("SELECT count(*) FROM {}").format(ident))
            (existing,) = fetch_one(cur)
        if existing:
            print(
                f"report: {', '.join(missing)} missing but {table} has {existing} rows "
                f"from it -- skipping rebuild rather than truncate away those rows"
            )
            return existing
        print(f"report: {', '.join(missing)} not present yet -- building {table} without it")
    with conn.transaction(), conn.cursor() as cur:
        cur.execute(sql.SQL("TRUNCATE {}").format(ident))
        for build_sql in present:
            cur.execute(build_sql, {"season": None})
        cur.execute(sql.SQL("SELECT count(*) FROM {}").format(ident))
        (count,) = fetch_one(cur)
    return count


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
        counts["gold.batting_game"] = _build_backbone_relation_multi(
            conn,
            "gold.batting_game",
            [
                (_BATTING_GAME_SQL, "raw.retrosheet_event"),
                (_BATTING_GAME_MLB_SQL, "raw.mlb_boxscore_batting"),
            ],
        )
        counts["gold.pitching_game"] = _build_backbone_relation_multi(
            conn,
            "gold.pitching_game",
            [
                (_PITCHING_GAME_SQL, "raw.retrosheet_event"),
                (_PITCHING_GAME_MLB_SQL, "raw.mlb_boxscore_pitching"),
            ],
        )
        # Season / team roll-ups read the game relations just built above.
        counts["gold.batting_season"] = _build_backbone_relation(
            conn, "gold.batting_season", _BATTING_SEASON_SQL, source="gold.batting_game"
        )
        counts["gold.batting_team"] = _build_backbone_relation(
            conn, "gold.batting_team", _BATTING_TEAM_SQL, source="gold.batting_game"
        )
        counts["gold.pitching_season"] = _build_backbone_relation(
            conn, "gold.pitching_season", _PITCHING_SEASON_SQL, source="gold.pitching_game"
        )
        counts["gold.pitching_team"] = _build_backbone_relation(
            conn, "gold.pitching_team", _PITCHING_TEAM_SQL, source="gold.pitching_game"
        )
        # Career roll-ups read the season tables built just above.
        counts["gold.batting_career"] = _build_backbone_relation(
            conn, "gold.batting_career", _BATTING_CAREER_SQL, source="gold.batting_season"
        )
        counts["gold.pitching_career"] = _build_backbone_relation(
            conn, "gold.pitching_career", _PITCHING_CAREER_SQL, source="gold.pitching_season"
        )
        # Postseason relations -- Lahman BattingPost / PitchingPost lineage,
        # never the event backbone; skip cleanly if Lahman postseason isn't
        # ingested yet.
        counts["gold.batting_postseason"] = _build_backbone_relation(
            conn,
            "gold.batting_postseason",
            _BATTING_POSTSEASON_SQL,
            source="raw.lahman_batting_post",
        )
        counts["gold.pitching_postseason"] = _build_backbone_relation(
            conn,
            "gold.pitching_postseason",
            _PITCHING_POSTSEASON_SQL,
            source="raw.lahman_pitching_post",
        )
        # FanGraphs reference lookups (fangraphs-conform Beat 1, ADR-290) --
        # local_research only; skip cleanly if FanGraphs was never ingested.
        counts["gold.fangraphs_guts"] = _build_backbone_relation(
            conn,
            "gold.fangraphs_guts",
            _GOLD_FANGRAPHS_GUTS_SQL,
            source="raw.fangraphs_guts",
        )
        counts["gold.fangraphs_park_factors"] = _build_backbone_relation(
            conn,
            "gold.fangraphs_park_factors",
            _GOLD_FANGRAPHS_PARK_FACTORS_SQL,
            source="raw.fangraphs_park_factors",
        )
        conn.commit()
        result["rows"] = sum(counts.values())
    return counts


def _fangraphs_health_checks() -> list[Check]:
    """Coverage / identity checks for the fangraphs-conform Beat 1 lookups
    (ADR-290). Each is appended only when its `raw.fangraphs_*` source is
    present, so `mlb doctor` on a database that never ingested FanGraphs is
    unchanged (no red, no noise)."""
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute("SELECT to_regclass('raw.fangraphs_guts')")
        (guts_present,) = fetch_one(cur)
        cur.execute("SELECT to_regclass('raw.fangraphs_park_factors')")
        (pf_present,) = fetch_one(cur)

    checks: list[Check] = []
    if guts_present is not None:
        checks.append(check_table_has_rows("gold.fangraphs_guts"))
        # Every modern batting season should have a FanGraphs Guts! constant
        # row. season >= 2003 mirrors the park-factor scope; FanGraphs' Guts!
        # table itself runs 1871+, so a gap here is a build/ingest problem,
        # not a coverage limit of the source.
        checks.append(
            check_no_rows(
                "every gold.batting_season season >= 2003 has a gold.fangraphs_guts row",
                """
                SELECT count(DISTINCT bs.season)
                FROM gold.batting_season bs
                LEFT JOIN gold.fangraphs_guts fg ON fg.season = bs.season
                WHERE bs.season >= 2003 AND fg.season IS NULL
                """,
            )
        )
    if pf_present is not None:
        # actual < expected => a raw.fangraphs_park_factors row (season >= 2003)
        # did not conform, i.e. its FanGraphs nickname has no 'fangraphs'
        # core.team_alias entry (add it to conform.py::_TEAM_ALIAS_SEED). The
        # 2003+ franchise set is fully covered by the 34-alias seed, so the
        # expected side is every 2003+ raw row -- a shortfall is an unresolved
        # code, never a silent drop. actual > expected => alias fan-out.
        checks.append(
            check_join_coverage(
                "gold.fangraphs_park_factors resolves every raw.fangraphs_park_factors "
                "team for season >= 2003",
                "SELECT count(*) FROM gold.fangraphs_park_factors",
                """
                SELECT count(*)
                FROM raw.fangraphs_park_factors pf
                WHERE NULLIF(pf.season, '')::integer >= 2003
                """,
                tolerance=0,
            )
        )
    return checks


def health_check() -> list[Check]:
    return [
        *_fangraphs_health_checks(),
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
        # tolerance=0: every (game, batter, team) triple with a completed
        # plate appearance and a resolvable core.player should produce
        # exactly one gold.batting_game row. The "expected" side mirrors the
        # build's own inner JOIN to core.player, its HAVING pa > 0 filter,
        # and its (game, player, team) grain -- the team CASE matches
        # batting_game_build.sql exactly -- so this is not a stricter bar
        # than the builder can clear, and it does not false-alarm on the
        # rare player-for-both-clubs-in-one-game case.
        check_join_coverage(
            "raw.retrosheet_event (game, batter, team) triples with a PA and a resolvable "
            "player get a gold.batting_game row",
            # source-scoped: the 2026+ mlb_boxscore rows are covered by their
            # own check below (backbone-2026-source).
            "SELECT count(*) FROM gold.batting_game WHERE source = 'retrosheet_event'",
            """
            SELECT count(*) FROM (
                SELECT re.game_id, re.bat_id,
                    CASE WHEN re.bat_home_id = '1' THEN g.home_team_id ELSE g.away_team_id END
                FROM raw.retrosheet_event re
                JOIN core.game g ON g.retro_game_id = re.game_id AND lower(g.game_type) = 'regular'
                JOIN raw.retrosheet_gameinfo gi ON gi.gid = g.retro_game_id
                JOIN core.player p ON p.retro_id = re.bat_id
                WHERE re.bat_id IS NOT NULL AND re.bat_id <> ''
                GROUP BY re.game_id, re.bat_id,
                    CASE WHEN re.bat_home_id = '1' THEN g.home_team_id ELSE g.away_team_id END
                HAVING count(*) FILTER (WHERE re.bat_event_fl = 'T') > 0
            ) s
            """,
            tolerance=0,
        ),
        check_table_has_rows("gold.pitching_game"),
        # Same shape as the batting_game check: one row per (game, charged
        # pitcher, team) with a batter faced and a resolvable core.player.
        # The team CASE is inverted from batting (the pitching team is the
        # one not batting), matching pitching_game_build.sql.
        check_join_coverage(
            "raw.retrosheet_event (game, pitcher, team) triples with a batter faced and a "
            "resolvable player get a gold.pitching_game row",
            "SELECT count(*) FROM gold.pitching_game WHERE source = 'retrosheet_event'",
            """
            SELECT count(*) FROM (
                SELECT re.game_id, re.resp_pit_id,
                    CASE WHEN re.bat_home_id = '1' THEN g.away_team_id ELSE g.home_team_id END
                FROM raw.retrosheet_event re
                JOIN core.game g ON g.retro_game_id = re.game_id AND lower(g.game_type) = 'regular'
                JOIN raw.retrosheet_gameinfo gi ON gi.gid = g.retro_game_id
                JOIN core.player p ON p.retro_id = re.resp_pit_id
                WHERE re.resp_pit_id IS NOT NULL AND re.resp_pit_id <> ''
                GROUP BY re.game_id, re.resp_pit_id,
                    CASE WHEN re.bat_home_id = '1' THEN g.away_team_id ELSE g.home_team_id END
                HAVING count(*) FILTER (WHERE re.bat_event_fl = 'T') > 0
            ) s
            """,
            tolerance=0,
        ),
        # --- 2026-onward MLB box-score game rows (backbone-2026-source) ---
        # Join coverage for the source = 'mlb_boxscore' rows only: every
        # raw.mlb_boxscore_batting line for a 2026+ regular-season game with a
        # real PA and a resolvable player/team should produce exactly one
        # gold.batting_game row. The "expected" side mirrors
        # batting_game_mlb_build.sql's own joins and pa > 0 filter, so a
        # shortfall means unresolved identity (a real regression), not a
        # stricter bar than the builder clears. FAILs cleanly if
        # raw.mlb_boxscore_batting was never ingested, same as the
        # Retrosheet coverage checks above.
        check_join_coverage(
            "raw.mlb_boxscore_batting 2026+ lines with a resolvable player/team "
            "get an mlb_boxscore-sourced gold.batting_game row",
            "SELECT count(*) FROM gold.batting_game WHERE source = 'mlb_boxscore'",
            """
            SELECT count(*) FROM raw.mlb_boxscore_batting mb
            JOIN core.game g ON g.game_pk = mb.game_pk
                AND g.season >= 2026 AND lower(g.game_type) = 'regular'
            JOIN core.team tm ON tm.mlb_team_id = NULLIF(mb.team_id, '')::integer
                AND tm.id IN (g.home_team_id, g.away_team_id)
            JOIN core.player p ON p.mlbam_id = mb.person_id
            WHERE NULLIF(mb.plate_appearances, '')::integer > 0
            """,
            tolerance=0,
        ),
        check_join_coverage(
            "raw.mlb_boxscore_pitching 2026+ lines with a resolvable player/team "
            "get an mlb_boxscore-sourced gold.pitching_game row",
            "SELECT count(*) FROM gold.pitching_game WHERE source = 'mlb_boxscore'",
            """
            SELECT count(*) FROM raw.mlb_boxscore_pitching mp
            JOIN core.game g ON g.game_pk = mp.game_pk
                AND g.season >= 2026 AND lower(g.game_type) = 'regular'
            JOIN core.team tm ON tm.mlb_team_id = NULLIF(mp.team_id, '')::integer
                AND tm.id IN (g.home_team_id, g.away_team_id)
            JOIN core.player p ON p.mlbam_id = mp.person_id
            WHERE NULLIF(mp.batters_faced, '')::integer > 0
               OR NULLIF(mp.outs, '')::integer > 0
            """,
            tolerance=0,
        ),
        # No-double-write guard (backbone-2026-source): the Retrosheet builder
        # (<= 2025) and the MLB box-score builder (>= 2026) must never both
        # write the same player-game. Grouped by (game_id, player_id) -- the
        # full (game_id, player_id, team_id) grain is the PRIMARY KEY, so a
        # collision there could not produce a row at all; this level catches a
        # builder season-bound error (e.g. a 2026 row escaping the Retrosheet
        # builder) that would otherwise abort the whole rebuild on the PK.
        check_no_rows(
            "no gold.batting_game / gold.pitching_game player-game is written by both builders",
            """
            SELECT
              (SELECT count(*) FROM (
                  SELECT game_id, player_id FROM gold.batting_game
                  GROUP BY game_id, player_id HAVING count(DISTINCT source) > 1) x)
            + (SELECT count(*) FROM (
                  SELECT game_id, player_id FROM gold.pitching_game
                  GROUP BY game_id, player_id HAVING count(DISTINCT source) > 1) y)
            """,
        ),
        check_table_has_rows("gold.batting_season"),
        # gold.batting_season = one stint row per (player, season, team) plus
        # one combined row per (player, season). The build groups both
        # straight off gold.batting_game, so the expected count is exactly
        # those two distinct-key counts summed -- not a stricter bar than the
        # builder clears.
        check_join_coverage(
            "gold.batting_game (player, season, team) + (player, season) keys "
            "each get a gold.batting_season row",
            "SELECT count(*) FROM gold.batting_season",
            """
            SELECT
                (SELECT count(*) FROM (
                    SELECT DISTINCT player_id, season, team_id FROM gold.batting_game) a)
              + (SELECT count(*) FROM (
                    SELECT DISTINCT player_id, season FROM gold.batting_game) b)
            """,
            tolerance=0,
        ),
        check_table_has_rows("gold.batting_team"),
        check_join_coverage(
            "gold.batting_game (team, season) keys get a gold.batting_team row",
            "SELECT count(*) FROM gold.batting_team",
            "SELECT count(*) FROM (SELECT DISTINCT team_id, season FROM gold.batting_game) s",
            tolerance=0,
        ),
        check_table_has_rows("gold.pitching_season"),
        # Same shape as the batting_season check, off gold.pitching_game:
        # one stint row per (player, season, team) + one combined row per
        # (player, season).
        check_join_coverage(
            "gold.pitching_game (player, season, team) + (player, season) keys "
            "each get a gold.pitching_season row",
            "SELECT count(*) FROM gold.pitching_season",
            """
            SELECT
                (SELECT count(*) FROM (
                    SELECT DISTINCT player_id, season, team_id FROM gold.pitching_game) a)
              + (SELECT count(*) FROM (
                    SELECT DISTINCT player_id, season FROM gold.pitching_game) b)
            """,
            tolerance=0,
        ),
        check_table_has_rows("gold.pitching_team"),
        check_join_coverage(
            "gold.pitching_game (team, season) keys get a gold.pitching_team row",
            "SELECT count(*) FROM gold.pitching_team",
            "SELECT count(*) FROM (SELECT DISTINCT team_id, season FROM gold.pitching_game) s",
            tolerance=0,
        ),
        check_table_has_rows("gold.batting_career"),
        # One career row per player with any batting_season combined row.
        check_join_coverage(
            "every gold.batting_season player gets a gold.batting_career row",
            "SELECT count(*) FROM gold.batting_career",
            "SELECT count(DISTINCT player_id) FROM gold.batting_season WHERE is_combined",
            tolerance=0,
        ),
        check_table_has_rows("gold.pitching_career"),
        check_join_coverage(
            "every gold.pitching_season player gets a gold.pitching_career row",
            "SELECT count(*) FROM gold.pitching_career",
            "SELECT count(DISTINCT player_id) FROM gold.pitching_season WHERE is_combined",
            tolerance=0,
        ),
        # Rate-stat domain checks -- catch a formula or upstream-component
        # change that produces an impossible value before a researcher sees
        # it. AVG/OBP/SLG are bounded [0, 4] (SLG max is 4.000, a homer
        # every AB); rate/9 stats and BABIP/percentages are non-negative;
        # OPS = OBP + SLG so it's bounded too.
        check_no_rows(
            "gold.batting_{season,team,career} rate stats are in range",
            """
            SELECT
              (SELECT count(*) FROM gold.batting_season WHERE avg  < 0 OR avg  > 1
                 OR obp < 0 OR obp > 1 OR slg < 0 OR slg > 4 OR ops < 0 OR ops > 5
                 OR iso < 0 OR babip < 0 OR bb_pct < 0 OR bb_pct > 1
                 OR k_pct < 0 OR k_pct > 1)
            + (SELECT count(*) FROM gold.batting_team WHERE avg  < 0 OR avg  > 1
                 OR obp < 0 OR obp > 1 OR slg < 0 OR slg > 4 OR ops < 0 OR ops > 5)
            + (SELECT count(*) FROM gold.batting_career WHERE avg  < 0 OR avg  > 1
                 OR obp < 0 OR obp > 1 OR slg < 0 OR slg > 4 OR ops < 0 OR ops > 5)
            """,
        ),
        check_no_rows(
            "gold.pitching_{season,team,career} rate stats are non-negative",
            """
            SELECT
              (SELECT count(*) FROM gold.pitching_season
                 WHERE ra9 < 0 OR whip < 0 OR k9 < 0 OR bb9 < 0 OR hr9 < 0 OR k_bb < 0)
            + (SELECT count(*) FROM gold.pitching_team
                 WHERE ra9 < 0 OR whip < 0 OR k9 < 0 OR bb9 < 0 OR hr9 < 0 OR k_bb < 0)
            + (SELECT count(*) FROM gold.pitching_career
                 WHERE ra9 < 0 OR whip < 0 OR k9 < 0 OR bb9 < 0 OR hr9 < 0 OR k_bb < 0)
            """,
        ),
        # --- Postseason contamination guard (separate-postseason-stats / ADR-282) ---
        # Since 1969 a team plays at most 162 regular-season games + one Game 163
        # tiebreaker. Before 1969 a pennant tie was a best-of-three AND in-full
        # tie-game replays counted, so both team and player totals legitimately
        # reach 164-165: 1962 SF (103-62) / LA (102-63) in Lahman Teams, and
        # Billy Williams / Ron Santo 1965 + Cesar Tovar 1967 at 164 G in the
        # event-derived season relations. Allow 165 pre-1969, 163 after; a
        # leaked postseason series adds far more than 2 games so it is still
        # caught. `pa > 800` is a universal ceiling (the season record is ~778).
        check_no_rows(
            "gold.player_season / gold.team_season are within the regular-season envelope",
            """
            SELECT
              (SELECT count(*) FROM gold.player_season
                 WHERE games > CASE WHEN season < 1969 THEN 165 ELSE 163 END OR pa > 800)
            + (SELECT count(*) FROM gold.team_season
                 WHERE wins + losses > CASE WHEN season < 1969 THEN 165 ELSE 163 END)
            """,
        ),
        check_no_rows(
            "gold.batting_season / gold.pitching_season are within the regular-season envelope",
            """
            SELECT
              (SELECT count(*) FROM gold.batting_season
                 WHERE g > CASE WHEN season < 1969 THEN 165 ELSE 163 END OR pa > 800)
            + (SELECT count(*) FROM gold.pitching_season
                 WHERE g > CASE WHEN season < 1969 THEN 165 ELSE 163 END)
            """,
        ),
        # --- Postseason relations (Lahman BattingPost / PitchingPost lineage) ---
        check_table_has_rows("gold.batting_postseason"),
        check_table_has_rows("gold.pitching_postseason"),
        # tolerance: the handful of Lahman postseason rows whose playerid
        # resolves neither via core.player.bbref_id nor via
        # raw.lahman_people.retroid (recent debuts not yet in core.player;
        # ~15 batting / ~2 pitching against production). The "expected" side
        # mirrors the builder's own resolution chain, so this is not a
        # stricter bar than the builder clears -- it exists so a *growth* in
        # unresolved ids (a crosswalk regression) turns doctor red instead of
        # silently shrinking the postseason relation.
        check_join_coverage(
            "resolvable raw.lahman_batting_post rows get a gold.batting_postseason per-round row",
            "SELECT count(*) FROM gold.batting_postseason WHERE NOT is_combined AND NOT is_career",
            """
            SELECT count(*) FROM raw.lahman_batting_post bp
            LEFT JOIN core.player pd ON pd.bbref_id = bp.playerid
            LEFT JOIN raw.lahman_people lp
                ON lp.playerid = bp.playerid AND lp.retroid <> '' AND pd.id IS NULL
            LEFT JOIN core.player pr ON pr.retro_id = lp.retroid
            JOIN raw.lahman_teams lt ON lt.teamid = bp.teamid AND lt.yearid = bp.yearid
            JOIN core.team t ON t.retro_team_id = lt.teamidretro
                AND bp.yearid::integer BETWEEN t.first_year AND t.last_year
            WHERE coalesce(pd.id, pr.id) IS NOT NULL
            """,
            tolerance=0,
        ),
        check_join_coverage(
            "resolvable raw.lahman_pitching_post rows get a gold.pitching_postseason per-round row",
            "SELECT count(*) FROM gold.pitching_postseason WHERE NOT is_combined AND NOT is_career",
            """
            SELECT count(*) FROM raw.lahman_pitching_post pp
            LEFT JOIN core.player pd ON pd.bbref_id = pp.playerid
            LEFT JOIN raw.lahman_people lp
                ON lp.playerid = pp.playerid AND lp.retroid <> '' AND pd.id IS NULL
            LEFT JOIN core.player pr ON pr.retro_id = lp.retroid
            JOIN raw.lahman_teams lt ON lt.teamid = pp.teamid AND lt.yearid = pp.yearid
            JOIN core.team t ON t.retro_team_id = lt.teamidretro
                AND pp.yearid::integer BETWEEN t.first_year AND t.last_year
            WHERE coalesce(pd.id, pr.id) IS NOT NULL
            """,
            tolerance=0,
        ),
        check_join_coverage(
            "gold.batting_postseason: a combined row per player-season, a career row per player",
            """
            SELECT
              (SELECT count(*) FROM gold.batting_postseason WHERE is_combined)
            + (SELECT count(*) FROM gold.batting_postseason WHERE is_career)
            """,
            """
            SELECT
              (SELECT count(*) FROM (SELECT DISTINCT player_id, season
                 FROM gold.batting_postseason WHERE NOT is_combined AND NOT is_career) a)
            + (SELECT count(DISTINCT player_id) FROM gold.batting_postseason
                 WHERE NOT is_combined AND NOT is_career)
            """,
            tolerance=0,
        ),
        # Postseason relations never contain a regular-season game: every
        # `round` must be a recognised postseason round (_PS_ROUND_RE). A new
        # Lahman round code (MLB changes the playoff format) turns this yellow
        # so it gets reviewed and added -- that is the intent, not a false alarm.
        check_no_rows(
            "gold.{batting,pitching}_postseason rounds are all recognised postseason rounds",
            f"""
            SELECT
              (SELECT count(*) FROM gold.batting_postseason
                 WHERE round IS NOT NULL AND round !~ '{_PS_ROUND_RE}')
            + (SELECT count(*) FROM gold.pitching_postseason
                 WHERE round IS NOT NULL AND round !~ '{_PS_ROUND_RE}')
            """,
        ),
    ]
