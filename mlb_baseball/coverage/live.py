"""Live checks: ask the publisher what exists and compare with what a table holds.

Only runs with ``mlb coverage --probe``. Every check is a bounded, paced set of GET requests
(finite timeout, shared retry); none writes, and a request that fails is reported, never
counted as zero."""

import time
from dataclasses import dataclass
from datetime import date
from urllib.parse import urlencode

import psycopg

from mlb_baseball.connectors import mlb_api
from mlb_baseball.coverage.model import Group
from mlb_baseball.net import get_with_retry

# Game types the schedule check compares: regular season and the postseason series.
SCHEDULE_GAME_TYPES = ("R", "F", "D", "L", "W")
# American and National League. Without this filter the Stats API's sportId=1 schedule also
# returns Negro League clubs (team ids 14xx/15xx, 1920s-1948), which the connector does not
# hold; that is a scope question (openspec negro-league-scope), not missing rows.
MAJOR_LEAGUE_IDS = "103,104"
REQUEST_PAUSE_SECONDS = 0.2
PROBE_TIMEOUT_SECONDS = 20
SCHEDULE_URL = "https://statsapi.mlb.com/api/v1/schedule"


@dataclass(frozen=True)
class LiveResult:
    """``groups``: one per season, expected = what the source reports, held = what we hold."""

    groups: list[Group]
    errors: list[str]


@dataclass(frozen=True)
class MlbScheduleTotals:
    """Per season, the Stats API's own game count against the rows of ``raw.mlb_schedule``
    with a regular-season or postseason game type. The count is ``totalGames`` of one tiny
    plain-HTTP request (``fields`` trims the response; plain HTTP because the ``statsapi``
    library returned 1 more game than the API for 1950). It is asked for everything the
    ``sportId=1`` level returns, and again for American and National League only; the
    second number rides in the group label so Negro League clubs (see above) can be told
    apart from other differences."""

    first: int = mlb_api.FIRST_SCHEDULE_YEAR
    unit: str = "game"

    @property
    def description(self) -> str:
        return (
            "Stats API schedule totalGames per season, sportId=1 (AL/NL-only count in "
            "brackets), regular season + postseason, versus rows of this table"
        )

    @staticmethod
    def _total(year: int, league_ids: str | None) -> int:
        params = {
            "sportId": "1",
            "season": str(year),
            "gameType": ",".join(SCHEDULE_GAME_TYPES),
            "fields": "totalGames",
        }
        if league_ids:
            params["leagueId"] = league_ids
        url = f"{SCHEDULE_URL}?{urlencode(params, safe=',')}"
        return int(get_with_retry(url, timeout=PROBE_TIMEOUT_SECONDS).json()["totalGames"])

    def measure(self, cur: psycopg.Cursor, table: str) -> LiveResult:
        cur.execute(
            f"""
            SELECT _season, count(*) FROM {table}
            WHERE game_type = ANY(%s) AND _season ~ '^[0-9]+$'
            GROUP BY _season
            """,
            (list(SCHEDULE_GAME_TYPES),),
        )
        held = {season: int(n) for season, n in cur.fetchall()}
        groups: list[Group] = []
        errors: list[str] = []
        for year in range(self.first, date.today().year + 1):
            try:
                everything = self._total(year, None)
                time.sleep(REQUEST_PAUSE_SECONDS)
                major = self._total(year, MAJOR_LEAGUE_IDS)
            except Exception as exc:  # report the season, keep checking the rest
                errors.append(f"{year}: {type(exc).__name__}: {exc}")
                continue
            label = f"{year} (AL/NL {major:,})"
            groups.append(Group(label, everything, held.get(str(year), 0)))
            time.sleep(REQUEST_PAUSE_SECONDS)
        return LiveResult(groups, errors)
