"""The one place that says what every raw table should hold.

Adding a dataset is one ``Dataset(...)`` entry here: a table, an expectation from
``model.py``, and the ``mlb ingest`` command that closes a gap (idempotent: it skips
what is already loaded). Year bounds come from the constants the connectors already
use, so this file and the loaders cannot disagree about a first year. A table with no
derivable expectation says why, in the output.
"""

from dataclasses import replace

from mlb_baseball.connectors import (
    bref,
    fangraphs,
    lahman,
    mlb_api,
    retrosheet,
    retrosheet_event,
    retrosheet_gamelog,
    statcast,
    statcast_leaderboard,
)
from mlb_baseball.coverage.live import MlbScheduleTotals
from mlb_baseball.coverage.model import (
    SCHEDULE_SETTLED_LABEL,
    Dataset,
    GameDates,
    Games,
    KalshiCandles,
    LiveCheck,
    ManifestFiles,
    NoExpectation,
    PolymarketWindows,
    Present,
    Referenced,
    ScheduleSettled,
    Seasons,
    manifest_label,
)

ANALYTICS_FIX = "mlb ingest mlb_api --stage analytics --start-year {first} --end-year {last}"
MLB_FIX = "mlb ingest mlb_api"

_NO_FIRST_YEAR = (
    "season-scoped endpoint, but no first valid year is recorded in mlb_api.py (the loader "
    "asks every season from 1901 and early seasons return nothing); task 1.1 probes it"
)
_CATALOG = "whole-catalog reference list reloaded each run; the source publishes no countable total"
_RETROSHEET_FIRST_PUBLISHED = (
    "no per-year publisher list is recorded offline; the manifest line for this source "
    "covers the archives it knows"
)
_MARKETS = (
    "catalog discovered from the venue's own listing; the venue publishes no total to "
    "compare against"
)


def _no(source: str, reason: str, *tables: str) -> list[Dataset]:
    return [
        Dataset(source, f"raw.{t}", NoExpectation(reason), f"mlb ingest {source}") for t in tables
    ]


def _seasons(source: str, spec: Seasons, *tables: str, caveat: str = "") -> list[Dataset]:
    return [Dataset(source, f"raw.{t}", spec, f"mlb ingest {source}", caveat) for t in tables]


def _present(source: str, *tables: str) -> list[Dataset]:
    return [Dataset(source, f"raw.{t}", Present(), f"mlb ingest {source}") for t in tables]


def _manifest(source: str) -> Dataset:
    return Dataset(source, manifest_label(source), ManifestFiles(source), f"mlb ingest {source}")


_EVENT_FIRST = min(years.start for years in retrosheet_event.PBP_DECADE_ARCHIVES.values())

DATASETS: list[Dataset] = [
    # MLB Stats API: per-game datasets, one unit per played game in raw.mlb_schedule.
    *[
        Dataset(
            "mlb_api", f"raw.{table}", Games(mlb_api.FIRST_WIN_PROB_YEAR, ledger), ANALYTICS_FIX
        )
        for table, ledger in (
            ("mlb_win_prob", "win_probability"),
            ("mlb_game_context", "context_metrics"),
            ("mlb_linescore", None),
        )
    ],
    *[
        Dataset("mlb_api", f"raw.{table}", Games(mlb_api.FIRST_PLAYBYPLAY_YEAR), MLB_FIX)
        for table in (
            "mlb_playbyplay",
            "mlb_boxscore_batting",
            "mlb_boxscore_pitching",
            "mlb_boxscore_fielding",
            "mlb_umpire",
        )
    ],
    # MLB Stats API: per-season datasets.
    *_seasons("mlb_api", Seasons(mlb_api.FIRST_SCHEDULE_YEAR), "mlb_schedule", "mlb_roster"),
    Dataset(
        "mlb_api",
        SCHEDULE_SETTLED_LABEL,
        ScheduleSettled(),
        MLB_FIX,
        "a past game left Scheduled means the schedule was not refreshed; the update reloads "
        "the current season, and a bootstrap reloads older ones",
    ),
    *_seasons("mlb_api", Seasons(mlb_api.FIRST_STANDINGS_YEAR), "mlb_standing"),
    *_seasons("mlb_api", Seasons(mlb_api.FIRST_TRANSACTION_YEAR), "mlb_transaction"),
    *_seasons("mlb_api", Seasons(mlb_api.FIRST_DRAFT_YEAR, column="draft_year"), "mlb_draft"),
    *_no(
        "mlb_api",
        _NO_FIRST_YEAR,
        "mlb_player_pool",
        "mlb_free_agent",
        "mlb_coach",
        "mlb_alumni",
        "mlb_game_pace",
        "mlb_player_stat",
        "mlb_team_stat",
        "mlb_stat_leader",
        "mlb_team_leader",
        "mlb_attendance",
    ),
    # MLB Stats API entity tables: complete when every id the other tables use is here.
    Dataset(
        "mlb_api",
        "raw.mlb_person",
        Referenced(
            ("person_id",),
            (
                ("raw.mlb_roster", ("person_id",)),
                ("raw.mlb_boxscore_batting", ("person_id",)),
                ("raw.mlb_boxscore_pitching", ("person_id",)),
                ("raw.mlb_boxscore_fielding", ("person_id",)),
                ("raw.mlb_umpire", ("person_id",)),
                ("raw.mlb_draft", ("person_id",)),
                ("raw.mlb_transaction", ("person_id",)),
                ("raw.mlb_probable", ("pitcher_id",)),
            ),
            "person",
        ),
        "mlb ingest mlb_api",
        "the loader fetches people for ids found in raw.mlb_roster only, so an id seen only in "
        "box scores, the draft or transactions is never fetched by this command; the draft and "
        "transactions also name amateurs and minor leaguers, so read the roster line as the "
        "defect and the others as scope until the owner decides to widen it",
    ),
    Dataset(
        "mlb_api",
        "raw.mlb_venue",
        Referenced(
            ("venue_id",),
            (("raw.mlb_schedule", ("venue_id",)), ("raw.mlb_team_history", ("venue_id",))),
            "venue",
        ),
        "mlb ingest mlb_api",
    ),
    Dataset(
        "mlb_api",
        "raw.mlb_team_history",
        Referenced(
            ("team_id",),
            (
                ("raw.mlb_schedule", ("home_id",)),
                ("raw.mlb_schedule", ("away_id",)),
                ("raw.mlb_roster", ("team_id",)),
                ("raw.mlb_transaction", ("to_team_id",)),
                ("raw.mlb_draft", ("team_id",)),
            ),
            "team",
        ),
        "mlb ingest mlb_api",
        "the connector loads MLB (sportId 1) teams only; transaction destinations include "
        "minor-league and other clubs, so that line is scope, not a defect",
    ),
    *_no(
        "mlb_api",
        _CATALOG,
        "mlb_sport",
        "mlb_league",
        "mlb_division",
        "mlb_season",
        "mlb_affiliate",
        "mlb_award",
        "mlb_conference",
        "mlb_official_scorer",
        "mlb_umpire_directory",
        "mlb_datacaster",
        "mlb_personnel",
    ),
    *_no(
        "mlb_api",
        "snapshots of games in progress, transient by design; no countable total",
        "mlb_live_game",
    ),
    *_no(
        "mlb_api",
        "daily probable-pitcher announcements for upcoming games only; no countable total",
        "mlb_probable",
    ),
    # Retrosheet: seasons from the connectors' own first year; a season is published
    # after it ends, so the last expected one is the previous year.
    *_seasons(
        "retrosheet",
        Seasons(retrosheet.FIRST_YEAR, "prior"),
        "retrosheet_allplayers",
        "retrosheet_batting",
        "retrosheet_fielding",
        "retrosheet_gameinfo",
        "retrosheet_pitching",
        "retrosheet_plays",
        "retrosheet_teamstats",
    ),
    *_seasons(
        "retrosheet_event", Seasons(_EVENT_FIRST, "prior"), "retrosheet_event", "retrosheet_game"
    ),
    *_seasons(
        "retrosheet_gamelog", Seasons(retrosheet_gamelog.FIRST_YEAR, "prior"), "retrosheet_gamelog"
    ),
    *_present("retrosheet_gamelog", "retrosheet_gamelog_post"),
    *_seasons(
        "retrosheet_roster", Seasons(retrosheet_gamelog.FIRST_YEAR, "prior"), "retrosheet_roster"
    ),
    *_no(
        "retrosheet_schedule",
        "one schedule.zip; the seasons it contains are not listed anywhere offline",
        "retrosheet_schedule",
    ),
    *_present("retrosheet_transaction", "retrosheet_transaction"),
    *_no(
        "retrosheet_box",
        _RETROSHEET_FIRST_PUBLISHED,
        "retrosheet_box_game",
        "retrosheet_box_batting",
        "retrosheet_box_pitching",
        "retrosheet_box_fielding",
        "retrosheet_box_double",
        "retrosheet_box_doubleplay",
        "retrosheet_box_homerun",
        "retrosheet_box_sacbunt",
        "retrosheet_box_stolenbase",
        "retrosheet_box_triple",
        "retrosheet_box_tripleplay",
    ),
    *_present(
        "retrosheet_reference",
        "retrosheet_ballpark",
        "retrosheet_biofile",
        "retrosheet_biofile0",
        "retrosheet_coach",
        "retrosheet_coach0",
        "retrosheet_manager",
        "retrosheet_park",
        "retrosheet_relative",
        "retrosheet_team",
        "retrosheet_team0",
        "retrosheet_umpire",
    ),
    *[
        _manifest(source)
        for source in (
            "retrosheet",
            "retrosheet_box",
            "retrosheet_event",
            "retrosheet_gamelog",
            "retrosheet_reference",
            "retrosheet_roster",
            "retrosheet_schedule",
            "retrosheet_transaction",
        )
    ],
    # Lahman: one release, one file per table.
    *[
        Dataset("lahman", table, Present(), "mlb ingest lahman")
        for table, _, _ in lahman.TABLES
        if table not in ("raw.lahman_people", "raw.lahman_teams")
    ],
    Dataset(
        "lahman",
        "raw.lahman_people",
        Referenced(
            ("playerid",),
            tuple(
                (f"raw.lahman_{t}", ("playerid",))
                for t in ("batting", "pitching", "fielding", "appearances")
            ),
            "player",
        ),
        "mlb ingest lahman",
    ),
    Dataset(
        "lahman",
        "raw.lahman_teams",
        Referenced(
            ("yearid", "teamid"),
            tuple(
                (f"raw.lahman_{t}", ("yearid", "teamid"))
                for t in ("batting", "pitching", "fielding", "appearances")
            ),
            "team-season",
        ),
        "mlb ingest lahman",
    ),
    # Statcast.
    Dataset(
        "statcast",
        "raw.statcast_pitch",
        GameDates(statcast.FIRST_STATCAST_YEAR),
        "mlb ingest statcast",
        "bootstrap skips a past season that already has any rows (load.season_already_loaded), "
        "so a partly loaded past season is not repaired by it; no per-date repair command exists",
    ),
    *[
        Dataset(
            "statcast_leaderboard",
            table,
            Seasons(
                statcast_leaderboard.FIRST_SERVED_YEAR.get(table, statcast_leaderboard.FIRST_YEAR)
            ),
            "mlb ingest statcast_leaderboard",
        )
        for table in (
            *[table for table, _ in statcast_leaderboard.SIMPLE_LEADERBOARDS],
            "raw.statcast_oaa",
        )
    ],
    # FanGraphs.
    *_seasons(
        "fangraphs",
        Seasons(fangraphs.LEADERBOARD_FIRST_YEAR),
        "fangraphs_batting",
        "fangraphs_pitching",
        "fangraphs_fielding",
    ),
    *_seasons("fangraphs", Seasons(fangraphs.PARK_FACTOR_FIRST_YEAR), "fangraphs_park_factors"),
    *_seasons("fangraphs", Seasons(fangraphs.PROSPECT_FIRST_YEAR), "fangraphs_prospects"),
    *_seasons(
        "fangraphs",
        Seasons(fangraphs.SPLIT_FIRST_YEAR),
        "fangraphs_split_batting",
        "fangraphs_split_pitching",
    ),
    *_present("fangraphs", "fangraphs_guts"),
    *_no(
        "fangraphs",
        "handedness park factors start about 1980 per a connector comment; no exact year recorded",
        "fangraphs_park_factors_handedness",
    ),
    *_no(
        "fangraphs",
        "point-in-time projection captures; which captures should exist is undefined",
        "fangraphs_projection",
    ),
    # Baseball-Reference.
    *_seasons("bref", Seasons(bref.FIRST_YEAR), "bref_batting", "bref_pitching"),
    *_present("bref", "bref_war_batting", "bref_war_pitching"),
    # Chadwick register: whole files.
    *_present("register", "register_names", "register_links", "register_countries"),
    # Every MLB player id the other sources use should be in the register (Chadwick adds new
    # players shortly after a first appearance).
    Dataset(
        "register",
        "raw.register_people",
        Referenced(
            ("key_mlbam",),
            (
                ("raw.mlb_roster", ("person_id",)),
                ("raw.mlb_boxscore_batting", ("person_id",)),
                ("raw.mlb_boxscore_pitching", ("person_id",)),
                ("raw.mlb_boxscore_fielding", ("person_id",)),
                ("raw.mlb_umpire", ("person_id",)),
                ("raw.statcast_pitch", ("batter",)),
                ("raw.statcast_pitch", ("pitcher",)),
            ),
            "person",
        ),
        "mlb ingest register",
        "checked 2026-10-07: modern players are all present. The roster lines left over are "
        "Negro League players (1922-1945) the register does not list (a scope question, "
        "openspec negro-league-scope); 5 box-score players appear only in 2026 exhibition "
        "games against national teams; the umpire line is 2 placeholder rows (NO UMPIRE, "
        "1B Umpire) and 2 umpires, not players. A "
        "2026 debut missing here means the register has not caught up: reload it with "
        "`mlb ingest register`. The FanGraphs, Retrosheet and Baseball-Reference ids are not "
        "checked here (key_fangraphs lags for new players: 256 2026 FanGraphs ids had none on "
        "2026-10-07)",
    ),
    # Prediction markets.
    Dataset(
        "kalshi",
        "raw.kalshi_candle",
        KalshiCandles(),
        "mlb ingest kalshi --mode backfill",
    ),
    *_no("kalshi", _MARKETS, "kalshi_event", "kalshi_market", "kalshi_series"),
    *_no(
        "kalshi",
        "price snapshots captured by cron at run time; there is no fixed set to compare against",
        "kalshi_snapshot",
    ),
    Dataset(
        "polymarket",
        "raw.polymarket_price",
        PolymarketWindows(),
        "mlb ingest polymarket --mode backfill",
    ),
    *_no(
        "polymarket",
        _MARKETS,
        "polymarket_event",
        "polymarket_market",
        "polymarket_outcome",
    ),
    *_no(
        "polymarket",
        "price snapshots captured by cron at run time; there is no fixed set to compare against",
        "polymarket_snapshot",
    ),
    # News.
    *_no(
        "news",
        "continuous article feed; the publishers give no total to compare against",
        "news",
    ),
]

# Text date column per raw table whose rows carry a data date (formats differ per table;
# ``meta.data_date`` parses them). Tables not listed here simply report no date range.
DATE_COLUMNS: dict[str, str] = {
    "raw.mlb_schedule": "game_date",
    "raw.mlb_live_game": "game_date",
    "raw.mlb_transaction": "date",
    "raw.statcast_pitch": "game_date",
    "raw.retrosheet_plays": "date",
    "raw.retrosheet_gameinfo": "date",
    "raw.retrosheet_teamstats": "date",
    "raw.retrosheet_batting": "date",
    "raw.retrosheet_pitching": "date",
    "raw.retrosheet_fielding": "date",
    "raw.retrosheet_box_game": "date",
    "raw.retrosheet_game": "game_dt",
    "raw.retrosheet_gamelog": "date",
    "raw.retrosheet_gamelog_post": "date",
    "raw.retrosheet_schedule": "date",
    "raw.retrosheet_transaction": "primary_date",
    "raw.kalshi_candle": "ts",
    "raw.kalshi_market": "open_time",
    "raw.polymarket_price": "ts",
    "raw.polymarket_event": "startdate",
    "raw.fangraphs_projection": "_captured_date",
}

# Live checks (``mlb coverage --probe``): the publisher is asked, not our own tables.
LIVE_CHECKS: dict[str, LiveCheck] = {"raw.mlb_schedule": MlbScheduleTotals()}

DATASETS = [
    replace(
        d,
        date_column=DATE_COLUMNS.get(d.table, d.date_column),
        live=LIVE_CHECKS.get(d.table, d.live),
    )
    for d in DATASETS
]
