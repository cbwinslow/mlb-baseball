"""Measure the MLB API and PostgreSQL paths before changing a bulk loader.

This is deliberately a benchmark, not an ingestion command: it reads a
small live MLB schedule/sample and writes only to a transaction-scoped TEMP
table in ``mlb_test``. It never writes production data.

Example:
    TEST_DATABASE_URL=.../mlb_test \
      uv run python scripts/benchmark_mlb_api_ingestion.py --season 1967
"""

import argparse
import json
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlparse

import psycopg
import requests

SCHEDULE_URL = "https://statsapi.mlb.com/api/v1/schedule"
WIN_PROBABILITY_URL = "https://statsapi.mlb.com/api/v1/game/{game_pk}/winProbability"
WIN_PROB_FIELDS = (
    "atBatIndex,about,inning,halfInning,homeTeamWinProbability,"
    "awayTeamWinProbability,homeTeamWinProbabilityAdded"
)
_THREAD_LOCAL = threading.local()


def _test_database_url() -> str:
    url = os.environ.get("TEST_DATABASE_URL", "")
    database_name = urlparse(url).path.rsplit("/", 1)[-1].lower()
    if not url or "test" not in database_name:
        raise RuntimeError("TEST_DATABASE_URL must name a test database")
    return url


def _session() -> requests.Session:
    if not hasattr(_THREAD_LOCAL, "session"):
        _THREAD_LOCAL.session = requests.Session()
    return _THREAD_LOCAL.session


def _game_pks(season: int, limit: int) -> list[int]:
    response = requests.get(SCHEDULE_URL, params={"sportId": 1, "season": season}, timeout=30)
    response.raise_for_status()
    games = [game["gamePk"] for day in response.json().get("dates", []) for game in day["games"]]
    return [int(game_pk) for game_pk in games[:limit]]


def _fetch_win_probability(game_pk: int) -> tuple[int, bytes | None, str]:
    response = _session().get(
        WIN_PROBABILITY_URL.format(game_pk=game_pk),
        params={"fields": WIN_PROB_FIELDS},
        timeout=30,
    )
    if response.status_code == 404:
        return game_pk, None, "unavailable"
    response.raise_for_status()
    return game_pk, response.content, "loaded"


def _fetch_benchmark(
    game_pks: list[int], workers: int
) -> tuple[float, list[tuple[int, bytes | None, str]]]:
    started = time.monotonic()
    with ThreadPoolExecutor(max_workers=workers) as pool:
        rows = list(pool.map(_fetch_win_probability, game_pks))
    return time.monotonic() - started, rows


def _database_benchmark(url: str, rows: list[tuple[int, bytes]]) -> dict[str, float]:
    """Compare per-row commits with one COPY into a temporary table only."""
    with psycopg.connect(url) as conn, conn.cursor() as cur:
        cur.execute("CREATE TEMP TABLE benchmark_payload (game_pk bigint, payload jsonb)")
        started = time.monotonic()
        for game_pk, payload in rows:
            cur.execute(
                "INSERT INTO benchmark_payload (game_pk, payload) VALUES (%s, %s::jsonb)",
                (game_pk, payload.decode()),
            )
            conn.commit()
        per_row_seconds = time.monotonic() - started

        cur.execute("TRUNCATE benchmark_payload")
        started = time.monotonic()
        with cur.copy("COPY benchmark_payload (game_pk, payload) FROM STDIN") as copy:
            for game_pk, payload in rows:
                copy.write_row((game_pk, payload.decode()))
        conn.commit()
        copy_seconds = time.monotonic() - started
    return {"per_row_commit_seconds": per_row_seconds, "single_copy_seconds": copy_seconds}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--season", type=int, default=1967)
    parser.add_argument("--sample-games", type=int, default=32)
    parser.add_argument("--workers", type=int, nargs="+", default=[1, 4, 8, 16])
    args = parser.parse_args()

    url = _test_database_url()
    game_pks = _game_pks(args.season, args.sample_games)
    if not game_pks:
        raise RuntimeError(f"MLB returned no games for {args.season}")

    results = {"season": args.season, "games": len(game_pks), "requests": []}
    fetched_rows: list[tuple[int, bytes]] | None = None
    for workers in args.workers:
        seconds, rows = _fetch_benchmark(game_pks, workers)
        loaded_rows = [
            (game_pk, payload) for game_pk, payload, status in rows if status == "loaded"
        ]
        unavailable = sum(status == "unavailable" for _, _, status in rows)
        results["requests"].append(
            {
                "workers": workers,
                "seconds": round(seconds, 3),
                "games_per_second": round(len(rows) / seconds, 2),
                "loaded_games": len(loaded_rows),
                "unavailable_games": unavailable,
                "mean_payload_bytes": round(
                    sum(len(payload) for _, payload in loaded_rows) / len(loaded_rows)
                )
                if loaded_rows
                else 0,
            }
        )
        fetched_rows = loaded_rows
    assert fetched_rows is not None
    results["database"] = {
        key: round(value, 3) for key, value in _database_benchmark(url, fetched_rows).items()
    }
    print(json.dumps(results, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
