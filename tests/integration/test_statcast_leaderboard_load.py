"""Real DB, real DataFrame/COPY loading — only pybaseball's own HTTP calls
are mocked. SIMPLE_LEADERBOARDS is monkeypatched to a small fake set rather
than patching pybaseball's real functions directly: the module binds each
function object into that list at import time, so patching
`pybaseball.statcast_sprint_speed` etc. afterwards wouldn't reach the
already-captured reference — replacing the list itself is what the loop
in _load_season actually reads at call time."""

from datetime import date
from unittest.mock import patch

import pandas as pd
import pytest

from mlb_baseball.connectors import statcast_leaderboard as sl

TABLES = [
    "raw.statcast_sprint_speed",
    "raw.statcast_poptime",
    "raw.statcast_framing",
    "raw.statcast_jump",
    "raw.statcast_catch_prob",
    "raw.statcast_oaa_direction",
    "raw.statcast_running_split",
    "raw.statcast_oaa",
]


def _leaderboard_df(n, name="Player One"):
    return pd.DataFrame({"player_id": list(range(n)), "name": [name] * n})


class _FixedDate(date):
    @classmethod
    def today(cls):
        return date(2026, 6, 1)


@pytest.fixture(autouse=True)
def _fixed_date(monkeypatch):
    monkeypatch.setattr(sl, "date", _FixedDate)


@pytest.fixture(autouse=True)
def _clean_tables(db_conn):
    yield
    with db_conn.cursor() as cur:
        for table in TABLES:
            cur.execute(f"DROP TABLE IF EXISTS {table}")
        cur.execute("DELETE FROM meta.ingestion_run WHERE source = %s", (sl.SOURCE,))
    db_conn.commit()


def _fake_leaderboards(monkeypatch, fn_a=None, fn_b=None):
    fn_a = fn_a or (lambda season: _leaderboard_df(3))
    fn_b = fn_b or (lambda season: _leaderboard_df(2))
    monkeypatch.setattr(
        sl,
        "SIMPLE_LEADERBOARDS",
        [("raw.statcast_sprint_speed", fn_a), ("raw.statcast_poptime", fn_b)],
    )


def test_load_season_loads_every_simple_leaderboard(db_conn, monkeypatch):
    _fake_leaderboards(monkeypatch)
    with patch.object(sl.pybaseball, "statcast_outs_above_average", return_value=pd.DataFrame()):
        counts = sl._load_season(db_conn, 2025)

    assert counts["raw.statcast_sprint_speed"] == 3
    assert counts["raw.statcast_poptime"] == 2
    with db_conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM raw.statcast_sprint_speed")
        assert cur.fetchone() == (3,)


def test_load_season_rerunning_replaces_instead_of_duplicating(db_conn, monkeypatch):
    _fake_leaderboards(monkeypatch)
    with patch.object(sl.pybaseball, "statcast_outs_above_average", return_value=pd.DataFrame()):
        sl._load_season(db_conn, 2025)
        sl._load_season(db_conn, 2025)

    with db_conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM raw.statcast_sprint_speed")
        assert cur.fetchone() == (3,)


def test_load_season_skips_a_failing_leaderboard_and_continues(db_conn, monkeypatch):
    def flaky(season):
        raise RuntimeError("simulated Savant scrape failure")

    _fake_leaderboards(monkeypatch, fn_a=flaky)
    with patch.object(sl.pybaseball, "statcast_outs_above_average", return_value=pd.DataFrame()):
        counts = sl._load_season(db_conn, 2025)

    assert counts["raw.statcast_sprint_speed"] == 0
    assert counts["raw.statcast_poptime"] == 2
    with db_conn.cursor() as cur:
        cur.execute("SELECT to_regclass('raw.statcast_sprint_speed')")
        assert cur.fetchone() == (None,)  # never created — the one failure didn't land anything


def test_load_oaa_loops_every_non_catcher_position(db_conn):
    calls = []

    def fake_oaa(season, pos):
        calls.append(pos)
        return _leaderboard_df(1) if pos == 3 else pd.DataFrame()

    with patch.object(sl.pybaseball, "statcast_outs_above_average", side_effect=fake_oaa):
        total = sl._load_oaa(db_conn, 2025)

    assert calls == sl.OAA_POSITIONS
    assert 2 not in calls  # catcher explicitly excluded (library raises ValueError for it)
    assert total == 1
    with db_conn.cursor() as cur:
        cur.execute("SELECT _scope FROM raw.statcast_oaa")
        assert cur.fetchone() == ("2025_3",)


def test_bootstrap_loads_multiple_seasons(db_conn, monkeypatch):
    monkeypatch.setattr(sl, "FIRST_YEAR", 2025)
    _fake_leaderboards(monkeypatch)
    with patch.object(sl.pybaseball, "statcast_outs_above_average", return_value=pd.DataFrame()):
        counts = sl.bootstrap()

    assert counts["raw.statcast_sprint_speed"] > 0
    with db_conn.cursor() as cur:
        cur.execute("SELECT DISTINCT _season FROM raw.statcast_sprint_speed ORDER BY 1")
        assert cur.fetchall() == [("2025",), ("2026",)]


def test_update_reloads_current_season_only(db_conn, monkeypatch):
    monkeypatch.setattr(sl, "FIRST_YEAR", 2025)
    _fake_leaderboards(monkeypatch)
    with patch.object(sl.pybaseball, "statcast_outs_above_average", return_value=pd.DataFrame()):
        sl.bootstrap()
        sl.update()

    with db_conn.cursor() as cur:
        cur.execute(
            "SELECT _season, count(*) FROM raw.statcast_sprint_speed GROUP BY _season ORDER BY 1"
        )
        assert cur.fetchall() == [("2025", 3), ("2026", 3)]


def test_health_check_reports_last_run_not_freshness(db_conn, monkeypatch):
    monkeypatch.setattr(sl, "FIRST_YEAR", 2026)
    _fake_leaderboards(monkeypatch)
    with patch.object(sl.pybaseball, "statcast_outs_above_average", return_value=pd.DataFrame()):
        sl.bootstrap()

    checks = sl.health_check()

    assert any(c.name == f"{sl.SOURCE} last run" for c in checks)
    assert not any(c.name == f"{sl.SOURCE} freshness" for c in checks)


def test_fetch_framing_uses_the_corrected_leaderboard_url(monkeypatch):
    # Regression: pybaseball's own statcast_catcher_framing() still points at
    # the old /catcher_framing URL, which Savant has moved off (confirmed
    # directly — it now returns the ordinary HTML leaderboard page even with
    # csv=true, causing a pandas CSV-parse error). _fetch_framing must hit
    # the new /leaderboard/catcher-framing URL instead.
    captured = {}

    class FakeResponse:
        content = b"id,name\n1,Test Catcher\n"

        def raise_for_status(self):
            pass

    def fake_get(url, params=None):
        captured["url"] = url
        captured["params"] = params
        return FakeResponse()

    with patch.object(sl.requests, "get", side_effect=fake_get):
        df = sl._fetch_framing(2024)

    assert captured["url"] == sl.FRAMING_URL
    assert "/catcher_framing" not in captured["url"]
    assert captured["params"]["year"] == 2024
    assert len(df) == 1
