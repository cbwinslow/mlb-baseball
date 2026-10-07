"""The datasets `mlb schema-watch` samples: one cheap request per dataset.

MLB API endpoints (response fields), publisher file lists (Retrosheet downloads page,
Chadwick register and Lahman GitHub directories) and board lists (FanGraphs and Savant
leaderboards, one season each). The parsers are pure so they are tested without the
network; the fetch functions are thin. Sample season is the last complete one so boards
that start late (Savant arsenal 2017, spin 2020) still answer.
"""

import re
from collections.abc import Callable
from typing import Any

import requests

from mlb_baseball.schema_watch import Dataset

USER_AGENT = "mlb-research-schema-watch"
TIMEOUT = 30
SAMPLE_SEASON = 2025
SAMPLE_DATE = "2025-07-04"
SAMPLE_GAME_PK = 745444
SAMPLE_TEAM_ID = 147

# name -> (path, params). Paths are the endpoints the `mlb_api` connector loads
# (docs/sources/mlb_api_endpoints.md, status "held").
MLB_API_BASE = "https://statsapi.mlb.com/api/v1"
MLB_API_ENDPOINTS: dict[str, tuple[str, dict[str, Any]]] = {
    "schedule": ("/schedule", {"sportId": 1, "date": SAMPLE_DATE}),
    "standings": ("/standings", {"leagueId": "103,104", "season": SAMPLE_SEASON}),
    "teams": ("/teams", {"sportId": 1, "season": SAMPLE_SEASON}),
    "team_roster": (f"/teams/{SAMPLE_TEAM_ID}/roster", {"season": SAMPLE_SEASON}),
    "transactions": ("/transactions", {"startDate": "2025-07-01", "endDate": "2025-07-07"}),
    "venues": ("/venues", {"season": SAMPLE_SEASON}),
    "draft": (f"/draft/{SAMPLE_SEASON}", {}),
    "boxscore": (f"/game/{SAMPLE_GAME_PK}/boxscore", {}),
    "play_by_play": (f"/game/{SAMPLE_GAME_PK}/playByPlay", {}),
    "win_probability": (f"/game/{SAMPLE_GAME_PK}/winProbability", {}),
    "linescore": (f"/game/{SAMPLE_GAME_PK}/linescore", {}),
    "context_metrics": (f"/game/{SAMPLE_GAME_PK}/contextMetrics", {}),
    "people": ("/people", {"personIds": 592450}),
    "sports": ("/sports", {}),
    "leagues": ("/leagues", {"sportId": 1}),
    "divisions": ("/divisions", {"sportId": 1}),
    "seasons": ("/seasons", {"sportId": 1, "season": SAMPLE_SEASON}),
    "awards": ("/awards", {}),
}

RETROSHEET_DOWNLOADS = "https://www.retrosheet.org/downloads/othercsvs.html"
CHADWICK_REGISTER_DIR = "https://api.github.com/repos/chadwickbureau/register/contents/data"
LAHMAN_CORE_DIR = "https://api.github.com/repos/cbwinslow/baseballdatabank/contents/core"


def _get(url: str, **params: Any) -> requests.Response:
    response = requests.get(
        url, params=params or None, headers={"User-Agent": USER_AGENT}, timeout=TIMEOUT
    )
    response.raise_for_status()
    return response


def retrosheet_files(html: str) -> dict[str, str]:
    """Zip files linked from Retrosheet's downloads page: file name -> "file"."""
    links = re.findall(r'href="[^"]*?/downloads/([^"]+\.zip)"', html)
    return {name: "file" for name in links}


def github_dir_files(listing: list[dict]) -> dict[str, str]:
    """File names in a GitHub contents-API directory listing: name -> "file"."""
    return {entry["name"]: "file" for entry in listing if entry.get("type") == "file"}


def frame_columns(frame: Any) -> dict[str, str]:
    """Column -> dtype for a DataFrame (or a list of dicts) from a board call."""
    if isinstance(frame, list):
        import pandas as pd

        frame = pd.DataFrame(frame)
    return {str(col): str(dtype) for col, dtype in frame.dtypes.items()}


def _mlb_api(path: str, params: dict[str, Any]) -> Callable[[], Any]:
    return lambda: _get(f"{MLB_API_BASE}{path}", **params).json()


def mlb_api_datasets() -> list[Dataset]:
    return [
        Dataset("mlb_api", name, _mlb_api(path, params))
        for name, (path, params) in MLB_API_ENDPOINTS.items()
    ]


def file_list_datasets() -> list[Dataset]:
    return [
        Dataset(
            "retrosheet",
            "downloads_page",
            lambda: retrosheet_files(_get(RETROSHEET_DOWNLOADS).text),
            kind="names",
        ),
        Dataset(
            "chadwick_register",
            "data_dir",
            lambda: github_dir_files(_get(CHADWICK_REGISTER_DIR).json()),
            kind="names",
        ),
        Dataset(
            "lahman",
            "core_dir",
            lambda: github_dir_files(_get(LAHMAN_CORE_DIR).json()),
            kind="names",
        ),
    ]


def board_datasets() -> list[Dataset]:
    """FanGraphs and Savant boards: one season each, columns and dtypes as the sample."""
    import fungo.fangraphs as fg

    from mlb_baseball.connectors import statcast_leaderboard

    boards: list[Dataset] = []
    for table, fn in statcast_leaderboard.SIMPLE_LEADERBOARDS:
        boards.append(
            Dataset(
                "statcast_leaderboard",
                table.removeprefix("raw."),
                lambda fn=fn: frame_columns(fn(SAMPLE_SEASON)),
                kind="names",
            )
        )
    fangraphs = {
        "leaders_bat": lambda: fg.get_leaders("bat", SAMPLE_SEASON, SAMPLE_SEASON, ind=1, qual=0),
        "leaders_pit": lambda: fg.get_leaders("pit", SAMPLE_SEASON, SAMPLE_SEASON, ind=1, qual=0),
        "leaders_fld": lambda: fg.get_leaders("fld", SAMPLE_SEASON, SAMPLE_SEASON, ind=1, qual=0),
        "guts": fg.get_guts_constants,
        "park_factors": lambda: fg.get_park_factors(SAMPLE_SEASON),
        "prospects": lambda: fg.get_prospect_board(SAMPLE_SEASON),
        "split_batting": lambda: fg.get_split_leaders("B", SAMPLE_SEASON, "vs_lhp"),
        "split_pitching": lambda: fg.get_split_leaders("P", SAMPLE_SEASON, "vs_lhp"),
    }
    for name, call in fangraphs.items():
        boards.append(Dataset("fangraphs", name, lambda c=call: frame_columns(c()), kind="names"))
    return boards


def all_datasets() -> list[Dataset]:
    return mlb_api_datasets() + file_list_datasets() + board_datasets()
