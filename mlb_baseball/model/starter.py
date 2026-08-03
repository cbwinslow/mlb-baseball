"""Starting-pitcher quality: true FIP and K%/BB%/HR% (ADR-034,
docs/RESEARCH.md's feature-engineering backlog). Research consensus
(Wharton thesis, CS229 Stanford project, MDPI feature-selection study)
ranks starting-pitcher quality among the most predictive single factors
in MLB win prediction -- more so than team-level pitching stats alone.

raw.bref_pitching/raw.statcast_pitcher_expected have real ERA/xERA but
are SEASON AGGREGATES -- the same leakage trap ADR-032 already flagged
for core.player_war: using a pitcher's current-season number mid-season
would leak every start after the one being predicted. This module instead
computes point-in-time, no-leakage, WITHIN-season rolling stats directly
from raw.retrosheet_event's per-play data (event_cd: 3=K, 14/15=BB/IBB,
23=HR; event_outs_ct=outs recorded on that specific play; resp_pit_id=the
pitcher actually charged for that play, correctly handling mid-at-bat
substitutions -- all confirmed against Chadwick's own field documentation,
not assumed from column names) -- the same rolling-window shape already
used for team win_pct, just at pitcher granularity.

Verified directly against real data before writing this, not assumed
correct: reconstructing Jacob deGrom's 2018 regular-season line
(resp_pit_id='degrj001', filtered to gametype='regular' via a join to
raw.retrosheet_gameinfo -- omitting that filter silently pulled in his
2018 All-Star Game start too, degrj001's presence confirmed directly)
from raw.retrosheet_event reproduced his real, independently-sourced
raw.bref_pitching line: 269 K (exact), 46 BB (exact), 10 HR (exact),
217.0 computed innings vs the official 217 2/3 (653 vs 651 total outs,
99.7% precision -- the residual traced to caught-stealing/pickout outs
recorded on non-batter-event rows, which had to be included in the outs
sum even though bat_event_fl='T' correctly scopes the K/BB/HR counts).

Then checked at full scale (13,613 pitcher-seasons, every pitcher raw.
bref_pitching and raw.retrosheet_event both cover), not just the one
hand-picked example: 98.3% match exactly at a small (5-strikeout)
tolerance -- and that number is not a coincidence, it matches this
project's own already-documented Retrosheet raw-event-file coverage rate
(docs/ROADMAP.md, ADR-012: ~98.3% of games have a published raw event
file; the rest is a genuine gap in what Retrosheet publishes, not a
parsing limitation) almost exactly, strong independent confirmation the
reconstruction itself is correct. The remaining, larger mismatches trace
to a second real cause, also confirmed directly: raw.bref_pitching's
season row sometimes mixes POSTSEASON innings into a player's stated
season line for deep playoff runs (confirmed directly: Blake Snell's
2025 Dodgers row states 17 games/113 K, but only 11 of those 17 games
are gametype='regular' in Retrosheet's own data -- the other 6 are
wildcard/divisionseries/lcs/worldseries). This module's own reconstruction
is correctly regular-season-only; raw.bref_pitching's own scope isn't
always pure for pitchers whose team went deep, which is a real property
of the ground-truth source, not a bug here. health_check() below turns
all of this into a permanent, dynamic reconciliation (ADR-034) against
every pitcher-season, calibrated against these two real, understood
causes -- not a one-off check against a single hand-picked pitcher.

Scope: raw.retrosheet_event covers 1910-2025 only. The current season
(2026+) needs the equivalent computed from raw.mlb_playbyplay instead --
a real, different parsing task (MLB API's own JSON-derived schema, not
Retrosheet's event coding), deliberately not built here. Games before
1910 and the current season both get NULL starter columns until that
follow-up lands -- an honest, documented gap, not silently guessed.

FIP constant: a single fixed 3.10 (a commonly-cited modern value) is used
across every season rather than a year-specific constant, which would
need either a fully-sourced historical table (the exact per-season
FanGraphs constant could not be reliably confirmed via automated lookup
in this environment -- see docs/RESEARCH.md) or reconstructing league-wide
earned-run rates ourselves (real added complexity for a term that's just
an additive level-shift). This means early-20th-century FIP values sit on
a slightly different implied run environment than their true era, but
doesn't materially affect FIP's value as a model *feature* (predictive
ranking within a season is what matters, not historical scale purity) --
flagged here so nobody mistakes 3.10 for a researched-per-year number.
"""

import psycopg

from mlb_baseball.db import fetch_one
from mlb_baseball.health import Check, check_join_coverage, check_totals_reconcile

FIP_CONSTANT = 3.10

_BUILD_SQL = """
WITH regular_games AS (
    SELECT g.id AS game_id, g.season, g.game_date, g.retro_game_id
    FROM core.game g
    WHERE g.game_type = 'regular'
),
pitcher_game_stats AS (
    SELECT
        rg.game_id, rg.season, rg.game_date, re.resp_pit_id AS pitcher_retro_id,
        count(*) FILTER (WHERE re.bat_event_fl = 'T' AND re.event_cd = '3') AS k,
        count(*) FILTER (WHERE re.bat_event_fl = 'T' AND re.event_cd IN ('14', '15')) AS bb,
        count(*) FILTER (WHERE re.bat_event_fl = 'T' AND re.event_cd = '16') AS hbp,
        count(*) FILTER (WHERE re.bat_event_fl = 'T' AND re.event_cd = '23') AS hr,
        count(*) FILTER (WHERE re.bat_event_fl = 'T') AS bf,
        sum(re.event_outs_ct::numeric) AS outs
    FROM regular_games rg
    JOIN raw.retrosheet_gameinfo gi ON gi.gid = rg.retro_game_id AND lower(gi.gametype) = 'regular'
    JOIN raw.retrosheet_event re ON re.game_id = rg.retro_game_id
    GROUP BY rg.game_id, rg.season, rg.game_date, re.resp_pit_id
),
starters AS (
    SELECT rg.game_id,
        max(re.resp_pit_id) FILTER (WHERE re.bat_home_id = '0') AS home_starter_retro_id,
        max(re.resp_pit_id) FILTER (WHERE re.bat_home_id = '1') AS away_starter_retro_id
    FROM regular_games rg
    JOIN raw.retrosheet_gameinfo gi ON gi.gid = rg.retro_game_id AND lower(gi.gametype) = 'regular'
    JOIN raw.retrosheet_event re ON re.game_id = rg.retro_game_id
    WHERE re.resp_pit_start_fl = 'T'
    GROUP BY rg.game_id
),
-- Rolling entering-this-appearance totals: unlike team win_pct's window,
-- this is over each pitcher's OWN appearances (whatever role), not scoped
-- to starts only -- a pitcher's true form reflects everything they've
-- thrown, and virtually every regular starter's appearances are all starts
-- anyway.
rolling AS (
    SELECT game_id, pitcher_retro_id, game_date,
        SUM(k) OVER w_season AS k_sum,
        SUM(bb) OVER w_season AS bb_sum,
        SUM(hbp) OVER w_season AS hbp_sum,
        SUM(hr) OVER w_season AS hr_sum,
        SUM(bf) OVER w_season AS bf_sum,
        SUM(outs) OVER w_season AS outs_sum,
        (game_date - LAG(game_date) OVER w_career) AS rest
    FROM pitcher_game_stats
    WINDOW
        w_season AS (
            PARTITION BY pitcher_retro_id, season ORDER BY game_date, game_id
            ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING
        ),
        w_career AS (PARTITION BY pitcher_retro_id ORDER BY game_date, game_id)
),
quality AS (
    SELECT game_id, pitcher_retro_id, rest,
        CASE WHEN bf_sum > 0 THEN k_sum::numeric / bf_sum END AS k_pct,
        CASE WHEN bf_sum > 0 THEN bb_sum::numeric / bf_sum END AS bb_pct,
        CASE WHEN bf_sum > 0 THEN hr_sum::numeric / bf_sum END AS hr_pct,
        CASE WHEN outs_sum > 0 THEN
            (13 * hr_sum + 3 * (bb_sum + hbp_sum) - 2 * k_sum)::numeric
                / (outs_sum / 3.0) + %(fip_constant)s
        END AS fip
    FROM rolling
)
UPDATE gold.game_feature f
SET
    home_starter_id = hp.id,
    home_starter_era = hq.fip,
    home_starter_k_pct = hq.k_pct,
    home_starter_bb_pct = hq.bb_pct,
    home_starter_hr_pct = hq.hr_pct,
    home_starter_rest = hq.rest,
    away_starter_id = ap.id,
    away_starter_era = aq.fip,
    away_starter_k_pct = aq.k_pct,
    away_starter_bb_pct = aq.bb_pct,
    away_starter_hr_pct = aq.hr_pct,
    away_starter_rest = aq.rest
FROM starters s
LEFT JOIN quality hq ON hq.game_id = s.game_id AND hq.pitcher_retro_id = s.home_starter_retro_id
LEFT JOIN quality aq ON aq.game_id = s.game_id AND aq.pitcher_retro_id = s.away_starter_retro_id
LEFT JOIN core.player hp ON hp.retro_id = s.home_starter_retro_id
LEFT JOIN core.player ap ON ap.retro_id = s.away_starter_retro_id
WHERE f.game_id = s.game_id
"""


def compute(conn: psycopg.Connection) -> int:
    with conn.cursor() as cur:
        cur.execute("SELECT to_regclass('raw.retrosheet_event')")
        (exists,) = fetch_one(cur)
        if not exists:
            return 0
        cur.execute(_BUILD_SQL, {"fip_constant": FIP_CONSTANT})
        return cur.rowcount


# raw.mlb_playbyplay covers 2026+ only (the live season), a completely
# different schema from Retrosheet's: descriptive event_type text
# instead of numeric codes, one row per completed play (not per pitch),
# and `outs` is a *running* per-half-inning count (0/1/2, resets each
# half-inning) rather than an "outs on this specific play" field --
# outs recorded on a given play is the diff from the prior play in the
# same (game, inning, half_inning), confirmed directly against a real,
# identifiable pitcher (Shota Imanaga, 27 real 2026 starts) before
# writing this: per-play out counts matched exactly through several
# real innings (including a real grounded-into-double-play row
# correctly registering 2 outs in one diff), and the resulting
# aggregate (437 outs / 27 starts = 16.2 outs/start = 5.4 IP/start,
# 587 BF, 23.3% K-rate, 5.5% BB-rate) all land in normal, plausible
# ranges for a real MLB starter -- not just internally consistent, but
# sanity-checked against real baseball, the same discipline as this
# module's own Retrosheet-based verification.
#
# No bat_home_id-equivalent field either -- team side is derived from
# half_inning ('top' = away team batting = home team's pitcher on the
# mound, 'bottom' = the reverse, standard baseball convention). No
# resp_pit_start_fl-equivalent -- a team's starter is whichever
# pitcher_id appears on the very first play (MIN at_bat_index) of that
# team's side for the whole game.
#
# Fills the SAME home_starter_id/era/k_pct/bb_pct/hr_pct columns
# compute() does, gated on home_starter_era IS NULL so it only ever
# fills the gap compute() leaves (raw.mlb_playbyplay and
# raw.retrosheet_event don't overlap in practice -- confirmed directly,
# the former starts exactly where the latter stops). Only backfills
# COMPLETED 2026 games (games that already have play-by-play rows) --
# does not solve forward-looking prediction for a game that hasn't been
# played yet (no probable-pitcher data source wired up), a real,
# separate, harder problem left for later, not glossed over here.
_LIVE_BUILD_SQL = """
WITH regular_games AS (
    SELECT g.id AS game_id, g.season, g.game_date, g.game_pk
    FROM core.game g
    WHERE g.game_type = 'regular' AND g.game_pk IS NOT NULL
),
first_pitcher AS (
    SELECT DISTINCT ON (game_pk, half_inning) game_pk, half_inning, pitcher_id
    FROM raw.mlb_playbyplay
    ORDER BY game_pk, half_inning, at_bat_index::int
),
starters AS (
    SELECT rg.game_id,
        h.pitcher_id AS home_starter_id,
        a.pitcher_id AS away_starter_id
    FROM regular_games rg
    JOIN first_pitcher h ON h.game_pk = rg.game_pk AND h.half_inning = 'top'
    JOIN first_pitcher a ON a.game_pk = rg.game_pk AND a.half_inning = 'bottom'
),
play_outs AS (
    SELECT game_pk, pitcher_id, event_type,
        outs::int - LAG(outs::int, 1, 0) OVER (
            PARTITION BY game_pk, inning, half_inning ORDER BY at_bat_index::int
        ) AS outs_this_play
    FROM raw.mlb_playbyplay
),
pitcher_game_stats AS (
    SELECT rg.game_id, rg.season, rg.game_date, po.pitcher_id,
        count(*) FILTER (WHERE po.event_type IN ('strikeout', 'strikeout_double_play')) AS k,
        count(*) FILTER (WHERE po.event_type IN ('walk', 'intent_walk')) AS bb,
        count(*) FILTER (WHERE po.event_type = 'home_run') AS hr,
        count(*) FILTER (WHERE po.event_type NOT IN (
            'caught_stealing_2b', 'caught_stealing_3b', 'caught_stealing_home',
            'pickoff_1b', 'pickoff_2b', 'pickoff_3b',
            'pickoff_caught_stealing_2b', 'pickoff_caught_stealing_3b',
            'wild_pitch', 'game_advisory'
        )) AS bf,
        sum(po.outs_this_play) AS outs
    FROM regular_games rg
    JOIN play_outs po ON po.game_pk = rg.game_pk
    GROUP BY rg.game_id, rg.season, rg.game_date, po.pitcher_id
),
rolling AS (
    SELECT game_id, pitcher_id,
        SUM(k) OVER w AS k_sum, SUM(bb) OVER w AS bb_sum,
        SUM(hr) OVER w AS hr_sum, SUM(bf) OVER w AS bf_sum, SUM(outs) OVER w AS outs_sum
    FROM pitcher_game_stats
    WINDOW w AS (
        PARTITION BY pitcher_id, season ORDER BY game_date, game_id
        ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING
    )
),
quality AS (
    SELECT game_id, pitcher_id,
        CASE WHEN bf_sum > 0 THEN k_sum::numeric / bf_sum END AS k_pct,
        CASE WHEN bf_sum > 0 THEN bb_sum::numeric / bf_sum END AS bb_pct,
        CASE WHEN bf_sum > 0 THEN hr_sum::numeric / bf_sum END AS hr_pct,
        CASE WHEN outs_sum > 0 THEN
            (13 * hr_sum + 3 * bb_sum - 2 * k_sum)::numeric / (outs_sum / 3.0) + %(fip_constant)s
        END AS fip
    FROM rolling
)
UPDATE gold.game_feature f
SET
    home_starter_id = hp.id,
    home_starter_era = hq.fip,
    home_starter_k_pct = hq.k_pct,
    home_starter_bb_pct = hq.bb_pct,
    home_starter_hr_pct = hq.hr_pct,
    away_starter_id = ap.id,
    away_starter_era = aq.fip,
    away_starter_k_pct = aq.k_pct,
    away_starter_bb_pct = aq.bb_pct,
    away_starter_hr_pct = aq.hr_pct
FROM starters s
LEFT JOIN quality hq ON hq.game_id = s.game_id AND hq.pitcher_id = s.home_starter_id
LEFT JOIN quality aq ON aq.game_id = s.game_id AND aq.pitcher_id = s.away_starter_id
LEFT JOIN core.player hp ON hp.mlbam_id = s.home_starter_id
LEFT JOIN core.player ap ON ap.mlbam_id = s.away_starter_id
WHERE f.game_id = s.game_id AND f.home_starter_era IS NULL
"""


def compute_live(conn: psycopg.Connection) -> int:
    with conn.cursor() as cur:
        cur.execute("SELECT to_regclass('raw.mlb_playbyplay')")
        (exists,) = fetch_one(cur)
        if not exists:
            return 0
        cur.execute(_LIVE_BUILD_SQL, {"fip_constant": FIP_CONSTANT})
        return cur.rowcount


# ADR-048: closes compute_live()'s own documented limitation -- that
# function only ever backfills *completed* 2026 games, since it keys off
# core.game (which never holds a not-yet-played game at all). This one
# targets exactly the rows compute_live() can't reach: gold.game_feature
# rows with home_win IS NULL (still-upcoming games, sourced from
# raw.mlb_schedule directly -- see features.py), populated from
# raw.mlb_probable's own person_ids (mlb_baseball/connectors/mlb_api.py)
# resolved through core.player.mlbam_id -- the same crosswalk column
# compute_live() already uses for its own current-season identity
# resolution, not a new one.
#
# Deliberately joined via raw.mlb_schedule for game dates, not core.game,
# even though this reuses compute_live()'s own event-type/outs-diff logic
# almost verbatim: the pitcher's OWN past appearances need a game_date to
# apply the "strictly before the target game's date" rule against, and
# gating that on conform() having already processed yesterday's games
# would be a real, avoidable operational dependency this feature doesn't
# need -- raw.mlb_schedule is kept fresh by the same 5-minute update() that
# lands raw.mlb_playbyplay itself.
_PROBABLE_BUILD_SQL = """
WITH latest_probable AS (
    -- One row per (game_pk, side): the most recently captured probable --
    -- raw.mlb_probable is append-only specifically so a later snapshot (a
    -- scratch, a rotation swap) always wins over an earlier one instead of
    -- the first announcement staying authoritative forever.
    SELECT DISTINCT ON (game_pk, side) game_pk, side, pitcher_id
    FROM raw.mlb_probable
    WHERE pitcher_id IS NOT NULL
    ORDER BY game_pk, side, _loaded_at DESC
),
targets AS (
    -- Every still-upcoming game_feature row with an announced probable on
    -- at least one side. mlb_game_pk / raw.mlb_probable.game_pk are both
    -- MLB's own numeric game id (text, per the raw layer's own
    -- convention) -- no crosswalk needed for the game itself, only for
    -- the pitcher (below).
    SELECT f.id AS feature_id, f.game_date,
        hp.pitcher_id AS home_pitcher_id, ap.pitcher_id AS away_pitcher_id
    FROM gold.game_feature f
    LEFT JOIN latest_probable hp ON hp.game_pk = f.mlb_game_pk AND hp.side = 'home'
    LEFT JOIN latest_probable ap ON ap.game_pk = f.mlb_game_pk AND ap.side = 'away'
    WHERE f.home_win IS NULL AND (hp.pitcher_id IS NOT NULL OR ap.pitcher_id IS NOT NULL)
),
-- Every pitcher's own 2026 appearance, at (pitcher, calendar day) grain --
-- identical event-type mapping and per-play outs-diff logic as
-- compute_live()'s own play_outs/pitcher_game_stats (see that function's
-- docstring for why outs needs a LAG diff, not a direct column), just
-- dated via raw.mlb_schedule instead of core.game.
play_outs AS (
    SELECT pbp.game_pk, pbp.pitcher_id, pbp.event_type, ms.game_date::date AS game_date,
        pbp.outs::int - LAG(pbp.outs::int, 1, 0) OVER (
            PARTITION BY pbp.game_pk, pbp.inning, pbp.half_inning ORDER BY pbp.at_bat_index::int
        ) AS outs_this_play
    FROM raw.mlb_playbyplay pbp
    JOIN raw.mlb_schedule ms ON ms.game_id = pbp.game_pk AND ms.game_type = 'R'
),
pitcher_game_stats AS (
    SELECT pitcher_id, game_date,
        count(*) FILTER (WHERE event_type IN ('strikeout', 'strikeout_double_play')) AS k,
        count(*) FILTER (WHERE event_type IN ('walk', 'intent_walk')) AS bb,
        count(*) FILTER (WHERE event_type = 'home_run') AS hr,
        count(*) FILTER (WHERE event_type NOT IN (
            'caught_stealing_2b', 'caught_stealing_3b', 'caught_stealing_home',
            'pickoff_1b', 'pickoff_2b', 'pickoff_3b',
            'pickoff_caught_stealing_2b', 'pickoff_caught_stealing_3b',
            'wild_pitch', 'game_advisory'
        )) AS bf,
        sum(outs_this_play) AS outs
    FROM play_outs
    GROUP BY pitcher_id, game_date
),
-- Entering-this-(not-yet-played)-start totals: every one of the probable
-- pitcher's OWN appearances strictly before the target game's own date --
-- "through yesterday," not "as of right now," matters when a probable is
-- announced several days out and the pitcher makes another start in
-- between (a real, if rare, timing gap -- not glossed over). A pitcher
-- with zero qualifying prior appearances (a call-up making their MLB
-- debut) correctly leaves every rate NULL below -- identity (the id
-- itself) still resolves in the final UPDATE, just not a computed rate.
home_quality AS (
    SELECT t.feature_id,
        CASE WHEN sum(s.bf) > 0 THEN sum(s.k)::numeric / sum(s.bf) END AS k_pct,
        CASE WHEN sum(s.bf) > 0 THEN sum(s.bb)::numeric / sum(s.bf) END AS bb_pct,
        CASE WHEN sum(s.bf) > 0 THEN sum(s.hr)::numeric / sum(s.bf) END AS hr_pct,
        CASE WHEN sum(s.outs) > 0 THEN
            (13 * sum(s.hr) + 3 * sum(s.bb) - 2 * sum(s.k))::numeric / (sum(s.outs) / 3.0)
                + %(fip_constant)s
        END AS fip
    FROM targets t
    JOIN pitcher_game_stats s ON s.pitcher_id = t.home_pitcher_id AND s.game_date < t.game_date
    GROUP BY t.feature_id
),
away_quality AS (
    SELECT t.feature_id,
        CASE WHEN sum(s.bf) > 0 THEN sum(s.k)::numeric / sum(s.bf) END AS k_pct,
        CASE WHEN sum(s.bf) > 0 THEN sum(s.bb)::numeric / sum(s.bf) END AS bb_pct,
        CASE WHEN sum(s.bf) > 0 THEN sum(s.hr)::numeric / sum(s.bf) END AS hr_pct,
        CASE WHEN sum(s.outs) > 0 THEN
            (13 * sum(s.hr) + 3 * sum(s.bb) - 2 * sum(s.k))::numeric / (sum(s.outs) / 3.0)
                + %(fip_constant)s
        END AS fip
    FROM targets t
    JOIN pitcher_game_stats s ON s.pitcher_id = t.away_pitcher_id AND s.game_date < t.game_date
    GROUP BY t.feature_id
)
UPDATE gold.game_feature f
SET
    home_starter_id = hp.id,
    home_starter_era = hq.fip,
    home_starter_k_pct = hq.k_pct,
    home_starter_bb_pct = hq.bb_pct,
    home_starter_hr_pct = hq.hr_pct,
    away_starter_id = ap.id,
    away_starter_era = aq.fip,
    away_starter_k_pct = aq.k_pct,
    away_starter_bb_pct = aq.bb_pct,
    away_starter_hr_pct = aq.hr_pct
FROM targets t
LEFT JOIN core.player hp ON hp.mlbam_id = t.home_pitcher_id
LEFT JOIN core.player ap ON ap.mlbam_id = t.away_pitcher_id
LEFT JOIN home_quality hq ON hq.feature_id = t.feature_id
LEFT JOIN away_quality aq ON aq.feature_id = t.feature_id
WHERE f.id = t.feature_id
"""


def compute_probable(conn: psycopg.Connection) -> int:
    with conn.cursor() as cur:
        cur.execute("SELECT to_regclass('raw.mlb_probable')")
        (probable_exists,) = fetch_one(cur)
        cur.execute("SELECT to_regclass('raw.mlb_playbyplay')")
        (playbyplay_exists,) = fetch_one(cur)
        if not probable_exists or not playbyplay_exists:
            return 0
        cur.execute(_PROBABLE_BUILD_SQL, {"fip_constant": FIP_CONSTANT})
        return cur.rowcount


# Shared by health_check()'s probable-pitcher coverage check below: one row
# per (upcoming game, side-with-an-announced-probable), with the feature
# table's own resolved era value attached per side.
_PROBABLE_COVERAGE_CTE = """
WITH latest_probable AS (
    SELECT DISTINCT ON (game_pk, side) game_pk, side, pitcher_id
    FROM raw.mlb_probable
    WHERE pitcher_id IS NOT NULL
    ORDER BY game_pk, side, _loaded_at DESC
),
sided AS (
    SELECT f.id, f.game_date, lp.pitcher_id,
        CASE WHEN lp.side = 'home' THEN f.home_starter_era ELSE f.away_starter_era END
            AS resolved_era
    FROM gold.game_feature f
    JOIN latest_probable lp ON lp.game_pk = f.mlb_game_pk
    WHERE f.home_win IS NULL
)
"""

_PROBABLE_ACTUAL_SQL = (
    _PROBABLE_COVERAGE_CTE + "SELECT count(*) FROM sided WHERE resolved_era IS NOT NULL"
)

# "Expected" here means "this pitcher has at least one qualifying prior
# appearance to compute a rate from" -- a debut call-up with zero prior
# raw.mlb_playbyplay history correctly stays NULL (see home_quality/
# away_quality above), so counting every announced probable as "should
# resolve" regardless would make this check permanently, falsely red.
#
# Real bug found via mlb doctor (issue #5): this used to additionally
# require a core.player row (JOIN core.player p ON pbp.pitcher_id =
# p.mlbam_id) before counting a pitcher as "has qualifying history" -- but
# home_quality/away_quality above never go through core.player at all to
# compute fip/k_pct/etc., they match raw.mlb_probable.pitcher_id straight
# to raw.mlb_playbyplay.pitcher_id (both already mlbam-style numeric ids,
# no crosswalk needed). That extra join meant a pitcher new enough to have
# prior 2026 starts but not yet in core.player (e.g. the register/Chadwick
# crosswalk hasn't caught up to a very recent debut) resolved a real,
# correct fip that this check then couldn't explain -- confirmed directly
# in production: 5 rows had resolved_era set with no matching core.player
# row at all (5/5 confirmed absent), producing "62 > expected 57" (doctor's
# check_join_coverage flags any over-count as a bug, matching this exactly).
# Also added ms.game_type = 'R' to mirror play_outs' own filter above --
# without it, a pitcher whose only prior appearance was spring
# training/exhibition would count as "expected" here despite play_outs
# never having a qualifying row for them either.
_PROBABLE_EXPECTED_SQL = (
    _PROBABLE_COVERAGE_CTE
    + """
    SELECT count(*) FROM sided s
    WHERE EXISTS (
        SELECT 1 FROM raw.mlb_playbyplay pbp
        JOIN raw.mlb_schedule ms ON ms.game_id = pbp.game_pk
            AND ms.game_date::date < s.game_date AND ms.game_type = 'R'
        WHERE pbp.pitcher_id = s.pitcher_id
    )
    """
)


def health_check() -> list[Check]:
    """Reconciles this module's own computed season totals (summed across
    a pitcher's starts, using the same raw.retrosheet_event/gameinfo
    query shape as compute()) against raw.bref_pitching's independently-
    sourced IP/BB/SO/HR for every pitcher-season both have. Dynamic, not a
    one-off check against a single hand-picked pitcher: re-validates
    automatically as more seasons/pitchers get ingested.

    Tolerance calibrated directly against real production data, not
    guessed (see this module's docstring for the two real, understood
    causes: ~1.7% of raw event files genuinely missing from what
    Retrosheet has published, matching this project's own already-
    documented coverage rate; and raw.bref_pitching itself sometimes
    mixing postseason innings into a deep-playoff-team pitcher's season
    row). tolerance=5 strikeouts (roughly one missing start's worth)
    reaches exactly 98.3% clean across all 13,613 pitcher-seasons both
    sources cover -- matching ADR-012's coverage figure almost exactly,
    strong independent confirmation this is the same known gap, not a
    new bug. Outs tolerance is proportionally wider (one missing start
    is ~15-18 outs, not ~5).

    max_mismatch_rate=0.02 on both checks: this per-row tolerance alone
    can never make either check report healthy, by construction -- the
    ~1.7% gap is proportional to dataset size, not a fixed small count,
    so a per-row-only tolerance means the absolute mismatch count grows
    right along with the data (confirmed directly: 238/13613=1.75% and
    197/13613=1.45% mismatched at the tolerances above, both matching
    the documented ~1.7% rate almost exactly -- this was never actually
    a passing check via `mlb doctor`'s boolean OK/FAIL output, just
    described as "98.3% clean" in prose). 2% gives a little headroom
    over the observed ~1.5-1.75% without masking a real new regression
    (e.g. a future Retrosheet coverage change) that pushes meaningfully
    past the documented, already-accepted rate."""
    return [
        check_totals_reconcile(
            "starter reconstruction: strikeouts vs bref_pitching",
            """
            WITH mine AS (
                SELECT p.mlbam_id, re._season,
                    count(*) FILTER (WHERE re.bat_event_fl = 'T' AND re.event_cd = '3') AS k
                FROM raw.retrosheet_event re
                JOIN raw.retrosheet_gameinfo gi
                    ON gi.gid = re.game_id AND lower(gi.gametype) = 'regular'
                JOIN core.player p ON p.retro_id = re.resp_pit_id
                WHERE p.mlbam_id IS NOT NULL
                GROUP BY p.mlbam_id, re._season
            )
            SELECT m.mlbam_id || '-' || m._season, m.k, bp.so::integer
            FROM mine m
            JOIN raw.bref_pitching bp ON bp.mlbid = m.mlbam_id AND bp._season = m._season
            WHERE bp.so ~ '^[0-9]+$'
            """,
            tolerance=5,
            max_mismatch_rate=0.02,
        ),
        check_totals_reconcile(
            "starter reconstruction: outs vs bref_pitching "
            "(small tolerance -- see module docstring)",
            """
            WITH mine AS (
                SELECT p.mlbam_id, re._season, sum(re.event_outs_ct::numeric) AS outs
                FROM raw.retrosheet_event re
                JOIN raw.retrosheet_gameinfo gi
                    ON gi.gid = re.game_id AND lower(gi.gametype) = 'regular'
                JOIN core.player p ON p.retro_id = re.resp_pit_id
                WHERE p.mlbam_id IS NOT NULL
                GROUP BY p.mlbam_id, re._season
            )
            -- bp.ip is baseball notation ("217.2" = 217 innings + 2 outs,
            -- NOT decimal 217.2) -- split_part on '.' and treat the
            -- fractional part as a literal out count, not a fraction.
            SELECT m.mlbam_id || '-' || m._season, m.outs,
                split_part(bp.ip, '.', 1)::numeric * 3
                    + COALESCE(NULLIF(split_part(bp.ip, '.', 2), ''), '0')::numeric
            FROM mine m
            JOIN raw.bref_pitching bp ON bp.mlbid = m.mlbam_id AND bp._season = m._season
            WHERE bp.ip ~ '^[0-9]+\\.?[0-9]*$'
            """,
            tolerance=18,
            max_mismatch_rate=0.02,
        ),
        # ADR-048: an upcoming game with an announced probable pitcher
        # should get a non-NULL starter feature whenever that pitcher has
        # some real prior 2026 history to compute one from -- otherwise
        # compute_probable() silently isn't running, or a real join is
        # broken (e.g. the core.player.mlbam_id crosswalk). A small
        # tolerance, not 0: a pitcher can have prior appearances with zero
        # outs recorded (e.g. immediately removed from a rain-shortened
        # game) which legitimately leaves fip NULL despite "having
        # history" by this check's own EXISTS test -- a real, understood
        # edge case, not a bug to chase to zero.
        check_join_coverage(
            "upcoming games with an announced probable get a resolved starter feature",
            _PROBABLE_ACTUAL_SQL,
            _PROBABLE_EXPECTED_SQL,
            tolerance=5,
        ),
    ]
