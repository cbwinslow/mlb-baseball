"""Lands Retrosheet's classic game logs into raw.retrosheet_gamelog: one row
per game, 1871-present — wider coverage than the modern CSV product's 1898+
(see retrosheet.py), because this is a different, older Retrosheet product.

Source: retrosheet.org/gamelogs/gl{year}.zip, one zip per year. The file
inside is headerless — field layout is fixed and documented at
retrosheet.org/gamelogs/glfields.txt (161 fields; verified against real
downloaded data, not just the doc, before hardcoding GAMELOG_FIELDS below).

Same shape as retrosheet.py otherwise: per-year scoped replace (too much
history to fully reload every run). bootstrap() fetches sequentially — this
module originally used the same bounded-thread-pool approach as retrosheet.py,
but reverted along with it after a real hang there (44 threads stuck in
futex_wait_queue, no safe way to root-cause it without a profiler this
environment doesn't have) — see docs/DECISIONS.md ADR-005. This module's own
run hadn't shown the same failure, but keeping both connectors on the same,
simpler, provably-reliable code path was judged safer than leaving one on an
approach just shown to be capable of hanging.
"""

import io
import zipfile
from datetime import date

import pandas as pd
import psycopg
import requests

from mlb_baseball.db import get_connection
from mlb_baseball.health import Check, check_last_run, check_table_has_rows
from mlb_baseball.ingest import track_run
from mlb_baseball.load import load_dataframe

SOURCE = "retrosheet_gamelog"
BASE_URL = "https://www.retrosheet.org/gamelogs"
FIRST_YEAR = 1871
TABLE = "raw.retrosheet_gamelog"

GAMELOG_FIELDS = [
    "date",
    "game_number",
    "day_of_week",
    "v_team",
    "v_league",
    "v_game_number",
    "h_team",
    "h_league",
    "h_game_number",
    "v_score",
    "h_score",
    "length_outs",
    "day_night",
    "completion",
    "forfeit",
    "protest",
    "park_id",
    "attendance",
    "time_of_game_minutes",
    "v_line_score",
    "h_line_score",
    "v_at_bats",
    "v_hits",
    "v_doubles",
    "v_triples",
    "v_homeruns",
    "v_rbi",
    "v_sac_hits",
    "v_sac_flies",
    "v_hbp",
    "v_walks",
    "v_intentional_walks",
    "v_strikeouts",
    "v_stolen_bases",
    "v_caught_stealing",
    "v_grounded_into_dp",
    "v_first_on_catcher_interference",
    "v_left_on_base",
    "v_pitchers_used",
    "v_individual_earned_runs",
    "v_team_earned_runs",
    "v_wild_pitches",
    "v_balks",
    "v_putouts",
    "v_assists",
    "v_errors",
    "v_passed_balls",
    "v_double_plays",
    "v_triple_plays",
    "h_at_bats",
    "h_hits",
    "h_doubles",
    "h_triples",
    "h_homeruns",
    "h_rbi",
    "h_sac_hits",
    "h_sac_flies",
    "h_hbp",
    "h_walks",
    "h_intentional_walks",
    "h_strikeouts",
    "h_stolen_bases",
    "h_caught_stealing",
    "h_grounded_into_dp",
    "h_first_on_catcher_interference",
    "h_left_on_base",
    "h_pitchers_used",
    "h_individual_earned_runs",
    "h_team_earned_runs",
    "h_wild_pitches",
    "h_balks",
    "h_putouts",
    "h_assists",
    "h_errors",
    "h_passed_balls",
    "h_double_plays",
    "h_triple_plays",
    "ump_home_id",
    "ump_home_name",
    "ump_1b_id",
    "ump_1b_name",
    "ump_2b_id",
    "ump_2b_name",
    "ump_3b_id",
    "ump_3b_name",
    "ump_lf_id",
    "ump_lf_name",
    "ump_rf_id",
    "ump_rf_name",
    "v_manager_id",
    "v_manager_name",
    "h_manager_id",
    "h_manager_name",
    "winning_pitcher_id",
    "winning_pitcher_name",
    "losing_pitcher_id",
    "losing_pitcher_name",
    "saving_pitcher_id",
    "saving_pitcher_name",
    "gwrbi_batter_id",
    "gwrbi_batter_name",
    "v_starting_pitcher_id",
    "v_starting_pitcher_name",
    "h_starting_pitcher_id",
    "h_starting_pitcher_name",
]
for _i in range(1, 10):
    GAMELOG_FIELDS += [f"v_player{_i}_id", f"v_player{_i}_name", f"v_player{_i}_pos"]
for _i in range(1, 10):
    GAMELOG_FIELDS += [f"h_player{_i}_id", f"h_player{_i}_name", f"h_player{_i}_pos"]
GAMELOG_FIELDS += ["additional_info", "acquisition_info"]

assert len(GAMELOG_FIELDS) == 161, f"expected 161 fields, got {len(GAMELOG_FIELDS)}"


def _fetch_year_zip(year: int) -> bytes | None:
    response = requests.get(f"{BASE_URL}/gl{year}.zip", timeout=60)
    if response.status_code == 404:
        return None
    response.raise_for_status()
    return response.content


def _extract_gamelog(year: int, zip_bytes: bytes) -> pd.DataFrame:
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        (member,) = (n for n in zf.namelist() if n.lower() == f"gl{year}.txt")
        with zf.open(member) as f:
            df = pd.read_csv(f, header=None, names=GAMELOG_FIELDS, low_memory=False).copy()
    df["_season"] = str(year)
    return df


def _load_zip(conn: psycopg.Connection, year: int, zip_bytes: bytes) -> dict[str, int]:
    df = _extract_gamelog(year, zip_bytes)
    return {TABLE: load_dataframe(conn, TABLE, df, scope_column="_season", scope_value=str(year))}


def _load_year(conn: psycopg.Connection, year: int) -> dict[str, int]:
    zip_bytes = _fetch_year_zip(year)
    if zip_bytes is None:
        return {}
    return _load_zip(conn, year, zip_bytes)


def bootstrap() -> dict[str, int]:
    totals: dict[str, int] = {}
    with get_connection() as conn, track_run(conn, SOURCE, "bootstrap") as result:
        for year in range(FIRST_YEAR, date.today().year + 1):
            for table, count in _load_year(conn, year).items():
                totals[table] = totals.get(table, 0) + count
            conn.commit()
        result["rows"] = sum(totals.values())
    return totals


def update() -> dict[str, int]:
    with get_connection() as conn, track_run(conn, SOURCE, "update") as result:
        totals = _load_year(conn, date.today().year)
        conn.commit()
        result["rows"] = sum(totals.values())
    return totals


def health_check() -> list[Check]:
    return [check_table_has_rows(TABLE), check_last_run(SOURCE)]
