"""Team wOBA: point-in-time, no-leakage, within-season rolling weighted
on-base average (ADR-036, docs/RESEARCH.md). FanGraphs' own published
formula (their Sabermetrics Library, confirmed via research) --
FanGraphs itself doesn't support scraping or API access (confirmed
directly: their contact page states this explicitly), so this recreates
the calculation from data already ingested rather than fetching theirs.

wOBA = (0.690*uBB + 0.722*HBP + 0.878*1B + 1.242*2B + 1.569*3B + 2.015*HR)
       / (AB + uBB + SF + HBP)

Weights are FanGraphs' current-era published constants, used as a single
fixed set across every season -- FanGraphs' own linear weights actually
shift year to year (published on their "Guts!" page), and reliably
sourcing the exact per-season table failed the same way the FIP constant
lookup did (docs/RESEARCH.md, ADR-034) -- flagged here for the same
reason, so these aren't mistaken for a year-precise reproduction.
Verified anyway before trusting them: computed the real 2023 MLB
league-average wOBA directly from raw.retrosheet_event with these
weights and got .317, matching the real, independently-known 2023 league
value almost exactly.

Reconstructed from raw.retrosheet_event's per-play data (event_cd: 14=
unintentional BB, 16=HBP, 20/21/22/23=1B/2B/3B/HR; ab_fl/sf_fl=at-bat/
sac-fly flags -- all confirmed against real data before use, not assumed
from column names, same discipline as starter.py) rather than raw.
statcast_batter_expected's season-aggregate xwOBA, which would leak
future games mid-season (the same trap ADR-032 flagged for WAR).

wRC+ (compute_wrc_plus, ADR-037): park- and league-adjusted, built on
top of team wOBA once park_factor (park.py) is already populated on the
same gold.game_feature row.
    wRC+ = (((team_wOBA - league_wOBA) / WOBA_SCALE) + 1) / (park_factor/100) * 100
Sanity-checked algebraically before trusting it: a league-average hitter
(team_wOBA = league_wOBA) in a neutral park (park_factor = 100) reduces
to exactly 100, which is required by wRC+'s own definition (100 = league
average, by construction) -- confirms the formula is wired correctly
before ever touching real data. League wOBA is itself a rolling, no-
leakage, season-to-date value (every team's batting combined, entering
each game) -- using a season's FINAL league wOBA would leak the same way
a team's own current-season aggregate would.

WOBA_SCALE is a single fixed value (1.20, the commonly-cited modern-era
figure), not year-specific -- same tradeoff as the wOBA weights above and
ADR-034's FIP constant, for the identical reason (the exact per-season
value could not be reliably sourced via automated lookup in this
environment).

Same 1910-2025 coverage gap as starter.py, now half-closed the same way
(ADR-046): compute_live()/compute_wrc_plus_live() are the
raw.mlb_playbyplay equivalents for the 2026+ season, gated on
home_woba/home_wrc_plus IS NULL so they only ever fill the gap the
Retrosheet-based versions leave -- see starter.py::compute_live's
docstring for the full schema-difference writeup.
"""

import psycopg

from mlb_baseball.db import fetch_one, get_connection
from mlb_baseball.health import Check
from mlb_baseball.sql import read_sql

# FanGraphs' current-era published wOBA weights (see module docstring for
# why these are fixed, not year-specific).
W_UBB = 0.690
W_HBP = 0.722
W_1B = 0.878
W_2B = 1.242
W_3B = 1.569
W_HR = 2.015

# See module docstring for why this is fixed, not year-specific.
WOBA_SCALE = 1.20


def compute(conn: psycopg.Connection) -> int:
    with conn.cursor() as cur:
        # Two-table dependency, two-table gate (issue #9 item 2): the SQL
        # below also joins raw.retrosheet_gameinfo -- see team_rate.py's
        # compute() for the full explanation (two different connectors).
        cur.execute("SELECT to_regclass('raw.retrosheet_event')")
        (event_exists,) = fetch_one(cur)
        cur.execute("SELECT to_regclass('raw.retrosheet_gameinfo')")
        (gameinfo_exists,) = fetch_one(cur)
        if not event_exists or not gameinfo_exists:
            return 0
        cur.execute(
            read_sql("team_woba_retrosheet_update.sql"),
            {
                "w_ubb": W_UBB,
                "w_hbp": W_HBP,
                "w_1b": W_1B,
                "w_2b": W_2B,
                "w_3b": W_3B,
                "w_hr": W_HR,
            },
        )
        return cur.rowcount


def compute_wrc_plus(conn: psycopg.Connection) -> int:
    """Must run after compute() (needs home_woba/away_woba already set)
    and after park.compute() (needs park_factor already set) -- reads
    both directly off gold.game_feature rather than recomputing them."""
    with conn.cursor() as cur:
        # Two-table dependency, two-table gate (issue #9 item 2) -- see
        # compute() above / team_rate.py's compute() for the full
        # explanation.
        cur.execute("SELECT to_regclass('raw.retrosheet_event')")
        (event_exists,) = fetch_one(cur)
        cur.execute("SELECT to_regclass('raw.retrosheet_gameinfo')")
        (gameinfo_exists,) = fetch_one(cur)
        if not event_exists or not gameinfo_exists:
            return 0
        cur.execute(
            read_sql("team_wrc_plus_retrosheet_update.sql"),
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


# raw.mlb_playbyplay covers 2026+ only -- see starter.py::compute_live's
# docstring (ADR-046) for the full schema differences (descriptive
# event_type text, no bat_home_id-equivalent -- team side derived from
# half_inning: 'bottom' = home team batting, matching bat_home_id='1').
# AB is an explicit allowlist, not a denylist, since it's the narrower
# category: every event_type that counts as an official at-bat (a
# batted-ball out, a hit, a strikeout) -- excludes walks/HBP/sac
# plays/catcher interference (the standard AB definition) and the
# baserunning-only event types (caught_stealing*/pickoff*/wild_pitch/
# game_advisory), which aren't a batter's own plate appearance at all.
_AB_EVENT_TYPES = (
    "single",
    "double",
    "triple",
    "home_run",
    "strikeout",
    "strikeout_double_play",
    "field_out",
    "force_out",
    "double_play",
    "grounded_into_double_play",
    "fielders_choice",
    "fielders_choice_out",
    "field_error",
    "triple_play",
    "other_out",
)


def compute_live(conn: psycopg.Connection) -> int:
    """raw.mlb_playbyplay equivalent of compute() (ADR-046 for
    starter.py's sibling version) -- gated on home_woba IS NULL so it
    only ever fills the gap compute() leaves; the two sources don't
    overlap in practice."""
    with conn.cursor() as cur:
        cur.execute("SELECT to_regclass('raw.mlb_playbyplay')")
        (exists,) = fetch_one(cur)
        if not exists:
            return 0
        cur.execute(
            read_sql("team_woba_live_update.sql"),
            {
                "w_ubb": W_UBB,
                "w_hbp": W_HBP,
                "w_1b": W_1B,
                "w_2b": W_2B,
                "w_3b": W_3B,
                "w_hr": W_HR,
                "ab_types": list(_AB_EVENT_TYPES),
            },
        )
        return cur.rowcount


def compute_wrc_plus_live(conn: psycopg.Connection) -> int:
    """Must run after compute_live() and park.compute() -- same
    dependency as compute_wrc_plus(). Gated on home_wrc_plus IS NULL."""
    with conn.cursor() as cur:
        cur.execute("SELECT to_regclass('raw.mlb_playbyplay')")
        (exists,) = fetch_one(cur)
        if not exists:
            return 0
        cur.execute(
            read_sql("team_wrc_plus_live_update.sql"),
            {
                "w_ubb": W_UBB,
                "w_hbp": W_HBP,
                "w_1b": W_1B,
                "w_2b": W_2B,
                "w_3b": W_3B,
                "w_hr": W_HR,
                "woba_scale": WOBA_SCALE,
                "ab_types": list(_AB_EVENT_TYPES),
            },
        )
        return cur.rowcount


def health_check() -> list[Check]:
    """Bounds are broad because gold.game_feature is per-game, so
    an early-season game can reflect just 1-3 real games (legitimate
    small-sample noise, the same reason home_win_pct can be exactly 1.0
    early in a season), not a full-season average. wRC+ is centered on
    100 by construction and has much less small-sample sensitivity since
    it's already relative to the same-sized league-wide sample.

    home_woba's bound was widened 0.05-0.65 -> 0.02-0.70 after a real
    production case, verified by hand on 2026-08-14: the Philadelphia
    Stars (retro_team_id PH5, Negro League, 1934-1949) entering their
    1946-05-13 home game had exactly one prior 1946 game with Retrosheet
    play-by-play coverage (an away game, NW2194605050) -- in it, they
    went 0-for-56 (56 AB) with 2 unintentional walks and zero hits. Hand
    calculation matches production exactly: wOBA = (0.690*2) / (56+2) =
    0.023793..., i.e. home_woba's stored value to 13 decimal places.
    Not a bug -- Retrosheet's Negro League play-by-play coverage is
    sparse enough that a team's entire "prior sample" for a season can be
    a single real, if extreme, game. Full verified range across all
    400,356 non-null home/away_woba rows in production: 0.0238-0.6067."""
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute(read_sql("offense_health_check.sql"))
        bad_woba, bad_wrc, bad_away_woba, bad_away_wrc = fetch_one(cur)

    def _check(name: str, bad: int, bounds: str) -> Check:
        if bad:
            return Check(name, False, f"{bad} rows outside {bounds}")
        return Check(name, True, f"all computed values within {bounds}")

    return [
        _check("home_woba plausible range", bad_woba, "0.02-0.70"),
        _check("home_wrc_plus plausible range", bad_wrc, "20-250"),
        _check("away_woba plausible range", bad_away_woba, "0.02-0.70"),
        _check("away_wrc_plus plausible range", bad_away_wrc, "20-250"),
    ]
