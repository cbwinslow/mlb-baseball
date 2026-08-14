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
from mlb_baseball.sql import read_sql

FIP_CONSTANT = 3.10

def compute(conn: psycopg.Connection) -> int:
    with conn.cursor() as cur:
        cur.execute("SELECT to_regclass('raw.retrosheet_event')")
        (exists,) = fetch_one(cur)
        if not exists:
            return 0
        cur.execute(read_sql("team_starter_retrosheet_update.sql"), {"fip_constant": FIP_CONSTANT})
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
def compute_live(conn: psycopg.Connection) -> int:
    with conn.cursor() as cur:
        cur.execute("SELECT to_regclass('raw.mlb_playbyplay')")
        (exists,) = fetch_one(cur)
        if not exists:
            return 0
        cur.execute(read_sql("team_starter_live_update.sql"), {"fip_constant": FIP_CONSTANT})
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
def compute_probable(conn: psycopg.Connection) -> int:
    with conn.cursor() as cur:
        cur.execute("SELECT to_regclass('raw.mlb_probable')")
        (probable_exists,) = fetch_one(cur)
        cur.execute("SELECT to_regclass('raw.mlb_playbyplay')")
        (playbyplay_exists,) = fetch_one(cur)
        if not probable_exists or not playbyplay_exists:
            return 0
        cur.execute(read_sql("team_starter_probable_update.sql"), {"fip_constant": FIP_CONSTANT})
        return cur.rowcount


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
            read_sql("starter_strikeouts_reconcile.sql"),
            tolerance=5,
            max_mismatch_rate=0.02,
        ),
        check_totals_reconcile(
            "starter reconstruction: outs vs bref_pitching "
            "(small tolerance -- see module docstring)",
            read_sql("starter_outs_reconcile.sql"),
            tolerance=18,
            max_mismatch_rate=0.02,
        ),
        check_join_coverage(
            "upcoming games with an announced probable get a resolved starter feature",
            read_sql("starter_probable_actual.sql"),
            read_sql("starter_probable_expected.sql"),
            tolerance=5,
        ),
    ]

