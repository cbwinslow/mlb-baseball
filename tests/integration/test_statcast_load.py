"""Real DB, real DataFrame/COPY loading — only the network (pybaseball's
own HTTP calls) is mocked, returning small fixture payloads shaped like
real pybaseball.statcast() output (a handful of representative columns,
not the full 119 — the loader doesn't care which columns are present)."""

from datetime import date
from unittest.mock import patch

import pandas as pd
import pytest

from mlb_baseball.connectors import statcast

TABLE = statcast.TABLE


def _pitch_df(n, game_pk=1):
    return pd.DataFrame(
        {
            "pitch_type": ["FF"] * n,
            "game_pk": [game_pk] * n,
            "release_speed": [95.0] * n,
            "player_name": [f"Pitcher {game_pk}"] * n,
        }
    )


class _FixedDate(date):
    @classmethod
    def today(cls):
        return date(2026, 3, 1)  # keeps the current-season range tiny in tests


@pytest.fixture(autouse=True)
def _fixed_date(monkeypatch):
    monkeypatch.setattr(statcast, "date", _FixedDate)


@pytest.fixture(autouse=True)
def _clean_table(db_conn):
    yield
    with db_conn.cursor() as cur:
        cur.execute(f"DROP TABLE IF EXISTS {TABLE}")
        cur.execute("DELETE FROM meta.ingestion_run WHERE source = %s", (statcast.SOURCE,))
    db_conn.commit()


def test_load_week_creates_table_and_loads_rows(db_conn):
    with patch.object(statcast.pybaseball, "statcast", return_value=_pitch_df(5)):
        count = statcast._load_week(db_conn, 2026, date(2026, 2, 1), date(2026, 2, 7))
    db_conn.commit()

    assert count == 5
    with db_conn.cursor() as cur:
        cur.execute(f"SELECT count(*) FROM {TABLE}")
        assert cur.fetchone() == (5,)


def test_load_week_returns_zero_without_touching_db_when_empty(db_conn):
    with patch.object(statcast.pybaseball, "statcast", return_value=pd.DataFrame()):
        count = statcast._load_week(db_conn, 2026, date(2026, 2, 1), date(2026, 2, 7))

    assert count == 0
    with db_conn.cursor() as cur:
        cur.execute("SELECT to_regclass(%s)", (TABLE,))
        assert cur.fetchone() == (None,)


def _single_week(monkeypatch, year):
    monkeypatch.setattr(
        statcast, "_season_date_ranges", lambda season: [(date(year, 2, 1), date(year, 2, 7))]
    )


def test_load_season_replaces_only_its_own_weeks_not_other_seasons(db_conn, monkeypatch):
    # Two different seasons' data must coexist — reloading one season must
    # not disturb another's already-loaded rows (season-scoped replace).
    _single_week(monkeypatch, 2025)
    with patch.object(statcast.pybaseball, "statcast", return_value=_pitch_df(3, game_pk=2025)):
        statcast._load_season(db_conn, 2025)
    _single_week(monkeypatch, 2026)
    with patch.object(statcast.pybaseball, "statcast", return_value=_pitch_df(2, game_pk=2026)):
        statcast._load_season(db_conn, 2026)

    with db_conn.cursor() as cur:
        cur.execute(f"SELECT _season, count(*) FROM {TABLE} GROUP BY _season ORDER BY 1")
        assert cur.fetchall() == [("2025", 3), ("2026", 2)]


def test_load_season_rerunning_replaces_instead_of_duplicating(db_conn, monkeypatch):
    _single_week(monkeypatch, 2026)
    with patch.object(statcast.pybaseball, "statcast", return_value=_pitch_df(4, game_pk=2026)):
        statcast._load_season(db_conn, 2026)
        statcast._load_season(db_conn, 2026)

    with db_conn.cursor() as cur:
        cur.execute(f"SELECT count(*) FROM {TABLE}")
        assert cur.fetchone() == (4,)


def test_load_season_skips_a_failing_week_and_continues(db_conn, monkeypatch):
    monkeypatch.setattr(
        statcast,
        "_season_date_ranges",
        lambda season: [
            (date(2026, 2, 1), date(2026, 2, 7)),
            (date(2026, 2, 8), date(2026, 2, 14)),
        ],
    )
    calls = {"count": 0}

    def flaky_statcast(start_dt, end_dt, verbose=False):
        calls["count"] += 1
        if calls["count"] == 2:
            raise RuntimeError("simulated transient failure")
        return _pitch_df(2, game_pk=calls["count"])

    with patch.object(statcast.pybaseball, "statcast", side_effect=flaky_statcast):
        total = statcast._load_season(db_conn, 2026)

    # 2 weekly chunks, the second one fails — only the first's rows land.
    assert total == 2
    with db_conn.cursor() as cur:
        cur.execute(f"SELECT count(*) FROM {TABLE}")
        assert cur.fetchone() == (2,)


def test_bootstrap_loads_multiple_seasons(db_conn, monkeypatch):
    monkeypatch.setattr(statcast, "FIRST_STATCAST_YEAR", 2025)
    with patch.object(statcast.pybaseball, "statcast", return_value=_pitch_df(1)):
        counts = statcast.bootstrap()

    assert counts[TABLE] > 0
    with db_conn.cursor() as cur:
        cur.execute(f"SELECT DISTINCT _season FROM {TABLE} ORDER BY 1")
        assert cur.fetchall() == [("2025",), ("2026",)]


def test_update_reloads_current_season_only(db_conn, monkeypatch):
    monkeypatch.setattr(statcast, "FIRST_STATCAST_YEAR", 2025)
    with patch.object(statcast.pybaseball, "statcast", return_value=_pitch_df(1)):
        statcast.bootstrap()
        counts = statcast.update()

    assert counts[TABLE] > 0
    with db_conn.cursor() as cur:
        cur.execute(f"SELECT _season, count(*) FROM {TABLE} GROUP BY _season ORDER BY 1")
        rows = dict(cur.fetchall())
    assert rows["2025"] > 0  # untouched by update()
    assert rows["2026"] > 0  # reloaded by update()


def test_health_check_reports_last_run_not_freshness(db_conn):
    # Unlike mlb_api, statcast isn't on a repeating schedule — health_check
    # should use check_last_run (pass/fail on the last run), not
    # check_recent_run's staleness-implies-broken semantics.
    with patch.object(statcast.pybaseball, "statcast", return_value=_pitch_df(1)):
        statcast.bootstrap()

    checks = statcast.health_check()

    assert any(c.name == f"{statcast.SOURCE} last run" for c in checks)
    assert not any(c.name == f"{statcast.SOURCE} freshness" for c in checks)
    assert all(c.ok for c in checks)
