"""Real DB, real DataFrame/COPY loading — only pybaseball's own HTTP calls
are mocked. bref.TABLES is monkeypatched to fake callables rather than
patching pybaseball.batting_stats_bref/pitching_stats_bref directly: the
module binds each function object into that list at import time, so
patching the pybaseball attribute afterwards wouldn't reach the
already-captured reference _load_season actually iterates over."""

from datetime import date

import pandas as pd
import pytest

from mlb_baseball.connectors import bref

TABLES = [
    "raw.bref_batting",
    "raw.bref_pitching",
    "raw.bref_war_batting",
    "raw.bref_war_pitching",
]


def _stats_df(n, name="Player One"):
    return pd.DataFrame({"Name": [name] * n, "Age": list(range(20, 20 + n))})


class _FixedDate(date):
    @classmethod
    def today(cls):
        return date(2026, 6, 1)


@pytest.fixture(autouse=True)
def _fixed_date(monkeypatch):
    monkeypatch.setattr(bref, "date", _FixedDate)


@pytest.fixture(autouse=True)
def _clean_tables(db_conn):
    yield
    with db_conn.cursor() as cur:
        for table in TABLES:
            cur.execute(f"DROP TABLE IF EXISTS {table}")
        cur.execute("DELETE FROM meta.ingestion_run WHERE source = %s", (bref.SOURCE,))
    db_conn.commit()


def _fake_tables(monkeypatch, batting_fn=None, pitching_fn=None):
    batting_fn = batting_fn or (lambda season: _stats_df(3))
    pitching_fn = pitching_fn or (lambda season: _stats_df(2))
    monkeypatch.setattr(
        bref, "TABLES", [("raw.bref_batting", batting_fn), ("raw.bref_pitching", pitching_fn)]
    )


@pytest.fixture(autouse=True)
def _fake_war_tables(monkeypatch):
    # bwar_bat/bwar_pitch take no season argument (real-history-in-one-call —
    # see module docstring), so the fakes below must accept the same
    # return_all kwarg _load_war() passes through call_with_retry.
    monkeypatch.setattr(
        bref,
        "WAR_TABLES",
        [
            ("raw.bref_war_batting", lambda return_all=False: _stats_df(2)),
            ("raw.bref_war_pitching", lambda return_all=False: _stats_df(1)),
        ],
    )


def test_load_season_loads_batting_and_pitching(db_conn, monkeypatch):
    _fake_tables(monkeypatch)
    counts = bref._load_season(db_conn, 2024)

    assert counts["raw.bref_batting"] == 3
    assert counts["raw.bref_pitching"] == 2
    with db_conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM raw.bref_batting")
        assert cur.fetchone() == (3,)


def test_load_season_rerunning_replaces_instead_of_duplicating(db_conn, monkeypatch):
    _fake_tables(monkeypatch)
    bref._load_season(db_conn, 2024)
    bref._load_season(db_conn, 2024)

    with db_conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM raw.bref_batting")
        assert cur.fetchone() == (3,)


def test_load_season_skips_a_failing_stat_type_and_continues(db_conn, monkeypatch):
    def flaky(season):
        raise RuntimeError("simulated failure")

    _fake_tables(monkeypatch, batting_fn=flaky)
    counts = bref._load_season(db_conn, 2024)

    assert counts["raw.bref_batting"] == 0
    assert counts["raw.bref_pitching"] == 2
    with db_conn.cursor() as cur:
        cur.execute("SELECT to_regclass('raw.bref_batting')")
        assert cur.fetchone() == (None,)


def test_load_war_loads_batting_and_pitching_war(db_conn):
    counts = bref._load_war(db_conn)

    assert counts["raw.bref_war_batting"] == 2
    assert counts["raw.bref_war_pitching"] == 1
    with db_conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM raw.bref_war_batting")
        assert cur.fetchone() == (2,)


def test_load_war_rerunning_replaces_instead_of_duplicating(db_conn):
    bref._load_war(db_conn)
    bref._load_war(db_conn)

    with db_conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM raw.bref_war_batting")
        assert cur.fetchone() == (2,)


def test_load_war_skips_a_failing_table_and_continues(db_conn, monkeypatch):
    def flaky(return_all=False):
        raise RuntimeError("simulated failure")

    monkeypatch.setattr(
        bref, "WAR_TABLES", [("raw.bref_war_batting", flaky), ("raw.bref_war_pitching", flaky)]
    )
    counts = bref._load_war(db_conn)

    assert counts["raw.bref_war_batting"] == 0
    assert counts["raw.bref_war_pitching"] == 0
    with db_conn.cursor() as cur:
        cur.execute("SELECT to_regclass('raw.bref_war_batting')")
        assert cur.fetchone() == (None,)


def test_bootstrap_loads_multiple_seasons(db_conn, monkeypatch):
    monkeypatch.setattr(bref, "FIRST_YEAR", 2025)
    _fake_tables(
        monkeypatch, batting_fn=lambda season: _stats_df(1), pitching_fn=lambda season: _stats_df(1)
    )
    counts = bref.bootstrap()

    assert counts["raw.bref_batting"] > 0
    assert counts["raw.bref_war_batting"] == 2
    assert counts["raw.bref_war_pitching"] == 1
    with db_conn.cursor() as cur:
        cur.execute("SELECT DISTINCT _season FROM raw.bref_batting ORDER BY 1")
        assert cur.fetchall() == [("2025",), ("2026",)]
        cur.execute("SELECT count(*) FROM raw.bref_war_batting")
        assert cur.fetchone() == (2,)


def test_update_reloads_current_season_only(db_conn, monkeypatch):
    monkeypatch.setattr(bref, "FIRST_YEAR", 2025)
    _fake_tables(
        monkeypatch, batting_fn=lambda season: _stats_df(1), pitching_fn=lambda season: _stats_df(1)
    )
    bref.bootstrap()
    bref.update()

    with db_conn.cursor() as cur:
        cur.execute("SELECT _season, count(*) FROM raw.bref_batting GROUP BY _season ORDER BY 1")
        assert cur.fetchall() == [("2025", 1), ("2026", 1)]


def test_health_check_reports_last_run_not_freshness(db_conn, monkeypatch):
    monkeypatch.setattr(bref, "FIRST_YEAR", 2026)
    _fake_tables(
        monkeypatch, batting_fn=lambda season: _stats_df(1), pitching_fn=lambda season: _stats_df(1)
    )
    bref.bootstrap()

    checks = bref.health_check()

    assert any(c.name == f"{bref.SOURCE} last run" for c in checks)
    assert not any(c.name == f"{bref.SOURCE} freshness" for c in checks)
    assert any(c.name == "raw.bref_war_batting" for c in checks)
    assert any(c.name == "raw.bref_war_pitching" for c in checks)
    assert all(c.ok for c in checks)
