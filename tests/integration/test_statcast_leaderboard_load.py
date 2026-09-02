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
    "raw.statcast_batter_exitvelo",
    "raw.statcast_batter_expected",
    "raw.statcast_batter_percentile",
    "raw.statcast_batter_arsenal",
    "raw.statcast_pitcher_exitvelo",
    "raw.statcast_pitcher_expected",
    "raw.statcast_pitcher_percentile",
    "raw.statcast_pitcher_arsenal",
    "raw.statcast_pitcher_arsenal_stat",
    "raw.statcast_spin_dir",
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
    # Clean before and after: these raw tables are created on demand (no
    # migration owns them) and pytest-split may schedule a leaky test from
    # another file ahead of this one's "table absent" assertions.
    def _reset():
        with db_conn.cursor() as cur:
            for table in TABLES:
                cur.execute(f"DROP TABLE IF EXISTS {table}")
            cur.execute("DELETE FROM meta.ingestion_run WHERE source = %s", (sl.SOURCE,))
        db_conn.commit()

    _reset()
    yield
    _reset()


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


def test_bootstrap_backfills_a_leaderboard_added_after_a_season_was_already_completed(
    db_conn, monkeypatch
):
    # Regression: the original completeness check tested only one proxy
    # table (raw.statcast_sprint_speed) for "is this season done." Once a
    # season looked done via that one table, adding a brand-new leaderboard
    # later would never get backfilled for that season — bootstrap() would
    # skip straight past it forever, since the proxy table already had data.
    # Found for real: exactly this happened to the 10 official-aggregate
    # leaderboards added in ADR-020, against a production database that
    # already had raw.statcast_sprint_speed fully loaded for every past
    # season.
    monkeypatch.setattr(sl, "FIRST_YEAR", 2025)
    with patch.object(sl.pybaseball, "statcast_outs_above_average", return_value=pd.DataFrame()):
        _fake_leaderboards(monkeypatch)  # only sprint_speed + poptime exist yet
        sl.bootstrap()

        # Now simulate a new leaderboard being added to the module later.
        monkeypatch.setattr(
            sl,
            "SIMPLE_LEADERBOARDS",
            [
                ("raw.statcast_sprint_speed", lambda season: _leaderboard_df(3)),
                ("raw.statcast_poptime", lambda season: _leaderboard_df(2)),
                ("raw.statcast_new_thing", lambda season: _leaderboard_df(4)),
            ],
        )
        counts = sl.bootstrap()

    assert counts["raw.statcast_new_thing"] > 0
    with db_conn.cursor() as cur:
        cur.execute("SELECT DISTINCT _season FROM raw.statcast_new_thing ORDER BY 1")
        assert cur.fetchall() == [("2025",), ("2026",)]
    with db_conn.cursor() as cur:
        cur.execute("DROP TABLE IF EXISTS raw.statcast_new_thing")
    db_conn.commit()


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
    # str since the mypy typing pass — requests stringified the int anyway
    assert captured["params"]["year"] == "2024"
    assert len(df) == 1


def test_simple_leaderboards_includes_the_official_aggregate_functions():
    # The real (unmocked) module-level list, not the test-only fake one —
    # confirms the official-aggregate leaderboards (added on top of the
    # tracking-only ones) are actually wired into the load loop, not just
    # defined and forgotten.
    tables = dict(sl.SIMPLE_LEADERBOARDS)
    assert tables["raw.statcast_batter_exitvelo"] is sl.pybaseball.statcast_batter_exitvelo_barrels
    assert tables["raw.statcast_batter_expected"] is sl.pybaseball.statcast_batter_expected_stats
    assert (
        tables["raw.statcast_batter_percentile"] is sl.pybaseball.statcast_batter_percentile_ranks
    )
    assert tables["raw.statcast_batter_arsenal"] is sl.pybaseball.statcast_batter_pitch_arsenal
    assert (
        tables["raw.statcast_pitcher_exitvelo"] is sl.pybaseball.statcast_pitcher_exitvelo_barrels
    )
    assert tables["raw.statcast_pitcher_expected"] is sl.pybaseball.statcast_pitcher_expected_stats
    assert (
        tables["raw.statcast_pitcher_percentile"] is sl.pybaseball.statcast_pitcher_percentile_ranks
    )
    assert tables["raw.statcast_pitcher_arsenal"] is sl.pybaseball.statcast_pitcher_pitch_arsenal
    assert (
        tables["raw.statcast_pitcher_arsenal_stat"] is sl.pybaseball.statcast_pitcher_arsenal_stats
    )
    assert tables["raw.statcast_spin_dir"] is sl.pybaseball.statcast_pitcher_spin_dir_comp


def test_bootstrap_loads_official_aggregate_leaderboards_with_real_functions(db_conn, monkeypatch):
    # One real (unmocked) end-to-end check against the live pybaseball
    # functions for a single season, unlike the other tests here which all
    # replace SIMPLE_LEADERBOARDS with fakes.
    monkeypatch.setattr(sl, "FIRST_YEAR", 2024)
    with patch.object(sl.pybaseball, "statcast_outs_above_average", return_value=pd.DataFrame()):
        counts = sl.bootstrap()

    assert counts["raw.statcast_batter_exitvelo"] > 0
    assert counts["raw.statcast_pitcher_percentile"] > 0
    assert counts["raw.statcast_spin_dir"] > 0
    with db_conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM raw.statcast_batter_exitvelo")
        assert cur.fetchone()[0] > 0
