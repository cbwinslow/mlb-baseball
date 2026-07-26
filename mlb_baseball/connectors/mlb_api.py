"""Lands the current season's schedule and standings from MLB's own Stats API
(statsapi.mlb.com) into raw.mlb_schedule/raw.mlb_standing, via the `statsapi`
package (github.com/toddrob99/MLB-StatsAPI — 830+ stars, actively maintained,
already a pinned dependency in pyproject.toml).

Deliberately scoped to the current season only, not a historical backfill:
Retrosheet already covers full history for both schedules
(retrosheet_schedule.py, 1877-2026) and completed-game results
(retrosheet_gamelog.py, 1871-present) — pulling that same history again from
this API would be pure duplication with zero new information, at real extra
cost (season-by-season API calls back to 1901+). What this source actually
adds that nothing else in this pipeline can: the *current*, still-in-progress
season before Retrosheet has published it, including live game status
(Scheduled/Postponed/Cancelled/Completed Early — states that don't exist in
Retrosheet's completed-game-only products) and current standings. See
docs/DECISIONS.md for the ADR.

Because only one season is ever held, bootstrap() and update() are the same
full-reload operation (load_dataframe with no scope_column) — same pattern as
the Chadwick register and Lahman, not the per-year scoped-replace pattern the
historical Retrosheet connectors use, since there's nothing to accumulate
across runs here.

No retry-with-backoff around the statsapi calls (contrast mlb_baseball/net.py,
ADR-007): that was added only after a real, observed transient-failure
pattern against retrosheet.org. Nothing like that has been observed against
statsapi.mlb.com yet — add it here the same way, if and when it actually
happens, not speculatively.
"""

import json
from datetime import date

import pandas as pd
import statsapi

from mlb_baseball.db import get_connection
from mlb_baseball.health import Check, check_last_run, check_table_has_rows
from mlb_baseball.ingest import track_run
from mlb_baseball.load import load_dataframe

SOURCE = "mlb_api"


def _schedule_df(season: int) -> pd.DataFrame:
    games = statsapi.schedule(season=season, sportId=1)
    for game in games:
        # statsapi's own schedule() emits "losing_Team" (capital T) instead of
        # "losing_team" specifically for tied Spring Training/Exhibition games
        # (confirmed: 22/2946 games in a real 2026 pull, all game_type S/E,
        # winning_team == "Tie", never both keys present on the same game).
        # load.py's column-name sanitizing lowercases both to the same
        # Postgres column, which would otherwise be a DuplicateColumn error
        # on CREATE TABLE — coalesce here instead of letting that happen.
        if "losing_Team" in game:
            game["losing_team"] = game.pop("losing_Team")
        # national_broadcasts is a list — raw columns are text, so serialize
        # rather than let pandas fall back to Python's str() repr of the list.
        game["national_broadcasts"] = json.dumps(game.get("national_broadcasts") or [])
    df = pd.DataFrame(games)
    df["_season"] = str(season)
    return df


def _standings_df(season: int) -> pd.DataFrame:
    divisions = statsapi.standings_data(season=season)
    rows = []
    for division_id, division in divisions.items():
        for team in division["teams"]:
            rows.append({"division_id": division_id, "div_name": division["div_name"], **team})
    df = pd.DataFrame(rows)
    df["_season"] = str(season)
    return df


def _run(mode: str) -> dict[str, int]:
    season = date.today().year
    with get_connection() as conn, track_run(conn, SOURCE, mode) as result:
        counts = {
            "raw.mlb_schedule": load_dataframe(conn, "raw.mlb_schedule", _schedule_df(season)),
            "raw.mlb_standing": load_dataframe(conn, "raw.mlb_standing", _standings_df(season)),
        }
        conn.commit()
        result["rows"] = sum(counts.values())
    return counts


def bootstrap() -> dict[str, int]:
    return _run("bootstrap")


def update() -> dict[str, int]:
    return _run("update")


def health_check() -> list[Check]:
    return [
        check_table_has_rows("raw.mlb_schedule"),
        check_table_has_rows("raw.mlb_standing"),
        check_last_run(SOURCE),
    ]
