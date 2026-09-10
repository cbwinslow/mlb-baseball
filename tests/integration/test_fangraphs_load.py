"""Real DB, real DataFrame/COPY loading for the FanGraphs connector — every
``fungo.fangraphs`` call is faked.

``fangraphs._PARK_FACTOR_BOARDS`` binds ``fg.get_park_factors`` /
``get_park_factors_by_handedness`` into a module list at import time (like
``bref.TABLES``), so tests monkeypatch that list, not the ``fg`` attributes.
Everything else is reached through ``fangraphs._fg_call(fg.<name>, ...)`` with
a call-time attribute lookup, so patching ``fangraphs.fg.<name>`` is enough.
"""

from datetime import date

import pytest

from mlb_baseball.connectors import fangraphs

TABLES = [
    "raw.fangraphs_batting",
    "raw.fangraphs_pitching",
    "raw.fangraphs_fielding",
    "raw.fangraphs_guts",
    "raw.fangraphs_park_factors",
    "raw.fangraphs_park_factors_handedness",
    "raw.fangraphs_prospects",
    "raw.fangraphs_split_batting",
    "raw.fangraphs_split_pitching",
    "raw.fangraphs_projection",
]


class _FixedDate(date):
    @classmethod
    def today(cls):
        return date(2026, 6, 1)


@pytest.fixture(autouse=True)
def _fixed_date(monkeypatch):
    monkeypatch.setattr(fangraphs, "date", _FixedDate)


@pytest.fixture(autouse=True)
def _clean_tables(db_conn):
    # These raw tables are created on demand (no migration owns them); clean
    # before and after so "table absent" assertions and pytest-split ordering
    # stay deterministic. Same convention as test_bref_load.py.
    def _reset():
        with db_conn.cursor() as cur:
            for table in TABLES:
                cur.execute(f"DROP TABLE IF EXISTS {table}")
            cur.execute("DELETE FROM meta.ingestion_run WHERE source = %s", (fangraphs.SOURCE,))
        db_conn.commit()

    _reset()
    yield
    _reset()


def _leader_rows(n, first_id=1):
    return [
        {"Name": f"Player {i}", "xMLBAMID": 1000 + i, "playerid": str(i), "WAR": 1.0 + i, "HR": i}
        for i in range(first_id, first_id + n)
    ]


def _fake_leaders(monkeypatch, rows_by_group=None):
    rows_by_group = rows_by_group or {
        "bat": _leader_rows(3),
        "pit": _leader_rows(2),
        "fld": _leader_rows(2),
    }

    def fake_get_leaders(stat_group, start, end, **kwargs):
        assert kwargs.get("ind") == 1 and kwargs.get("qual") == 0
        return list(rows_by_group.get(stat_group, []))

    monkeypatch.setattr(fangraphs.fg, "get_leaders", fake_get_leaders)


def _fake_guts(monkeypatch, n=5):
    monkeypatch.setattr(
        fangraphs.fg,
        "get_guts_constants",
        lambda: [{"Season": 2000 + i, "wOBA": 0.32, "wOBAScale": 1.2} for i in range(n)],
    )


def _fake_park_factors(monkeypatch, n=4):
    monkeypatch.setattr(
        fangraphs,
        "_PARK_FACTOR_BOARDS",
        [
            (
                "raw.fangraphs_park_factors",
                lambda season: [{"Team": f"T{i}", "Basic": 100 + i} for i in range(n)],
            ),
            (
                "raw.fangraphs_park_factors_handedness",
                lambda season: [{"Team": f"T{i}", "HR_as_L": 1.0} for i in range(n)],
            ),
        ],
    )


def _fake_prospects(monkeypatch, n=3):
    monkeypatch.setattr(
        fangraphs.fg,
        "get_prospect_board",
        lambda season, **kw: [{"playerName": f"Prospect {i}", "UPID": i} for i in range(n)],
    )


def _fake_splits(monkeypatch, n=2):
    def fake_split_leaders(position, season, split):
        return [
            {"playerName": f"{position} {i}", "playerId": i, "PA": 100 + i, "split_seen": split}
            for i in range(n)
        ]

    monkeypatch.setattr(fangraphs.fg, "get_split_leaders", fake_split_leaders)


def _fake_projections(monkeypatch, systems=("steamer",), ros=(), rows=None):
    rows = rows or [
        {"playerid": "1", "HR": 20, "WAR": 3.0},
        {"playerid": "2", "HR": 10, "WAR": 1.0},
    ]
    monkeypatch.setattr(fangraphs, "PRESEASON_SYSTEMS", list(systems))
    monkeypatch.setattr(fangraphs, "ROS_SYSTEMS", list(ros))
    monkeypatch.setattr(fangraphs, "PROJECTION_STAT_GROUPS", ["bat"])
    monkeypatch.setattr(
        fangraphs.fg, "get_projections", lambda system, stats: [dict(r) for r in rows]
    )


# --------------------------------------------------------------------------
# Season leaderboards
# --------------------------------------------------------------------------


def test_load_leaderboard_tags_season_and_scoped_replaces(db_conn, monkeypatch):
    _fake_leaders(monkeypatch)
    n = fangraphs._load_leaderboard(db_conn, "raw.fangraphs_batting", "bat", 2024)
    db_conn.commit()

    assert n == 3
    with db_conn.cursor() as cur:
        cur.execute("SELECT DISTINCT _season FROM raw.fangraphs_batting")
        assert cur.fetchall() == [("2024",)]


def test_load_leaderboard_rerun_replaces_not_duplicates(db_conn, monkeypatch):
    _fake_leaders(monkeypatch)
    fangraphs._load_leaderboard(db_conn, "raw.fangraphs_batting", "bat", 2024)
    fangraphs._load_leaderboard(db_conn, "raw.fangraphs_batting", "bat", 2024)
    db_conn.commit()

    with db_conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM raw.fangraphs_batting")
        assert cur.fetchone() == (3,)


def test_load_leaderboard_empty_response_is_a_noop(db_conn, monkeypatch):
    _fake_leaders(monkeypatch, rows_by_group={"fld": []})
    n = fangraphs._load_leaderboard(db_conn, "raw.fangraphs_fielding", "fld", 1900)
    db_conn.commit()

    assert n == 0
    with db_conn.cursor() as cur:
        cur.execute("SELECT to_regclass('raw.fangraphs_fielding')")
        assert cur.fetchone() == (None,)


# --------------------------------------------------------------------------
# Reference boards
# --------------------------------------------------------------------------


def test_load_guts_whole_table_replace_is_idempotent(db_conn, monkeypatch):
    _fake_guts(monkeypatch, n=5)
    fangraphs._load_guts(db_conn)
    fangraphs._load_guts(db_conn)
    db_conn.commit()

    with db_conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM raw.fangraphs_guts")
        assert cur.fetchone() == (5,)


def test_load_park_factors_loads_both_boards_per_season(db_conn, monkeypatch):
    _fake_park_factors(monkeypatch, n=4)
    total = fangraphs._load_park_factors(db_conn, 2024)
    db_conn.commit()

    assert total == 8
    with db_conn.cursor() as cur:
        cur.execute("SELECT DISTINCT _season FROM raw.fangraphs_park_factors")
        assert cur.fetchall() == [("2024",)]
        cur.execute("SELECT count(*) FROM raw.fangraphs_park_factors_handedness")
        assert cur.fetchone() == (4,)


def test_load_park_factors_keeps_basic_when_handedness_board_fails(db_conn, monkeypatch):
    # FanGraphs has handedness park factors only from 2002; a pre-2002 season
    # raises FangraphsError for that board. The basic board's rows for the same
    # season must still land (not be rolled back with the failed board).
    from fungo.exceptions import FangraphsError

    def _boom(season):
        raise FangraphsError(f"No Guts table found on handedness park factors {season}")

    monkeypatch.setattr(
        fangraphs,
        "_PARK_FACTOR_BOARDS",
        [
            ("raw.fangraphs_park_factors", lambda season: [{"Team": f"T{i}"} for i in range(3)]),
            ("raw.fangraphs_park_factors_handedness", _boom),
        ],
    )

    total = fangraphs._load_park_factors(db_conn, 2002)

    assert total == 3
    with db_conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM raw.fangraphs_park_factors")
        assert cur.fetchone() == (3,)
        cur.execute("SELECT to_regclass('raw.fangraphs_park_factors_handedness')")
        assert cur.fetchone() == (None,)


def test_load_prospects_per_season_scoped_replace(db_conn, monkeypatch):
    _fake_prospects(monkeypatch, n=3)
    fangraphs._load_prospects(db_conn, 2024)
    fangraphs._load_prospects(db_conn, 2024)
    db_conn.commit()

    with db_conn.cursor() as cur:
        cur.execute("SELECT count(*), count(DISTINCT _season) FROM raw.fangraphs_prospects")
        assert cur.fetchone() == (3, 1)


# --------------------------------------------------------------------------
# Splits
# --------------------------------------------------------------------------


def test_split_boards_scope_on_season_and_split_without_cross_delete(db_conn, monkeypatch):
    _fake_splits(monkeypatch, n=2)

    fangraphs._load_split_board(db_conn, "raw.fangraphs_split_batting", "B", 2024, "vs_lhp")
    fangraphs._load_split_board(db_conn, "raw.fangraphs_split_batting", "B", 2024, "vs_rhp")
    db_conn.commit()

    with db_conn.cursor() as cur:
        cur.execute(
            "SELECT _split, count(*) FROM raw.fangraphs_split_batting GROUP BY _split ORDER BY 1"
        )
        assert cur.fetchall() == [("vs_lhp", 2), ("vs_rhp", 2)]

    # Re-loading one split replaces only that split's rows.
    fangraphs._load_split_board(db_conn, "raw.fangraphs_split_batting", "B", 2024, "vs_lhp")
    db_conn.commit()
    with db_conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM raw.fangraphs_split_batting")
        assert cur.fetchone() == (4,)


# --------------------------------------------------------------------------
# Projection snapshot history
# --------------------------------------------------------------------------


def test_projections_seed_then_unchanged_rerun_appends_nothing(db_conn, monkeypatch):
    _fake_projections(monkeypatch)

    first = fangraphs._load_projections(db_conn)
    assert first == {"raw.fangraphs_projection": 2}

    second = fangraphs._load_projections(db_conn)
    assert second == {"raw.fangraphs_projection": 0}

    with db_conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM raw.fangraphs_projection")
        assert cur.fetchone() == (2,)


def test_projections_append_only_the_moved_key(db_conn, monkeypatch):
    _fake_projections(
        monkeypatch, rows=[{"playerid": "1", "HR": 20, "WAR": 3.0}, {"playerid": "2", "HR": 10}]
    )
    fangraphs._load_projections(db_conn)

    # Player 1's HR projection moves; player 2 unchanged.
    _fake_projections(
        monkeypatch, rows=[{"playerid": "1", "HR": 25, "WAR": 3.0}, {"playerid": "2", "HR": 10}]
    )
    appended = fangraphs._load_projections(db_conn)

    assert appended == {"raw.fangraphs_projection": 1}
    with db_conn.cursor() as cur:
        cur.execute(
            "SELECT playerid, count(*) FROM raw.fangraphs_projection GROUP BY playerid ORDER BY 1"
        )
        assert cur.fetchall() == [("1", 2), ("2", 1)]
        cur.execute(
            "SELECT hr FROM raw.fangraphs_projection WHERE playerid = '1' "
            "ORDER BY _loaded_at DESC LIMIT 1"
        )
        # raw.* columns are all text (schema derived from the DataFrame, no
        # type inference — same as raw.bref_*).
        assert cur.fetchone() == ("25",)


def test_projections_tag_horizon_preseason_vs_ros(db_conn, monkeypatch):
    monkeypatch.setattr(fangraphs, "PRESEASON_SYSTEMS", ["steamer"])
    monkeypatch.setattr(fangraphs, "ROS_SYSTEMS", ["steamerr"])
    monkeypatch.setattr(fangraphs, "PROJECTION_STAT_GROUPS", ["bat"])
    monkeypatch.setattr(fangraphs.fg, "get_projections", lambda s, g: [{"playerid": "1", "HR": 5}])

    fangraphs._load_projections(db_conn)

    with db_conn.cursor() as cur:
        cur.execute(
            "SELECT _projection_system, _horizon FROM raw.fangraphs_projection "
            "ORDER BY _projection_system"
        )
        assert cur.fetchall() == [("steamer", "preseason"), ("steamerr", "ros")]


# --------------------------------------------------------------------------
# Orchestration
# --------------------------------------------------------------------------


@pytest.fixture
def _tiny_ranges(monkeypatch):
    monkeypatch.setattr(fangraphs, "LEADERBOARD_FIRST_YEAR", 2025)
    monkeypatch.setattr(fangraphs, "PARK_FACTOR_FIRST_YEAR", 2025)
    monkeypatch.setattr(fangraphs, "PROSPECT_FIRST_YEAR", 2025)
    monkeypatch.setattr(fangraphs, "SPLIT_FIRST_YEAR", 2025)
    monkeypatch.setattr(fangraphs, "CURATED_SPLITS", ["vs_rhp"])


def test_bootstrap_loads_multiple_seasons(db_conn, monkeypatch, _tiny_ranges):
    _fake_leaders(monkeypatch)
    _fake_guts(monkeypatch)
    _fake_park_factors(monkeypatch)
    _fake_prospects(monkeypatch)
    _fake_splits(monkeypatch)
    _fake_projections(monkeypatch)

    totals = fangraphs.bootstrap()

    assert totals["raw.fangraphs_batting"] > 0
    with db_conn.cursor() as cur:
        cur.execute("SELECT DISTINCT _season FROM raw.fangraphs_batting ORDER BY 1")
        assert cur.fetchall() == [("2025",), ("2026",)]
        cur.execute("SELECT count(*) FROM raw.fangraphs_guts")
        assert cur.fetchone()[0] > 0
        cur.execute("SELECT count(*) FROM raw.fangraphs_projection")
        assert cur.fetchone()[0] == 2


def test_bootstrap_skips_a_failing_unit_and_continues(db_conn, monkeypatch, _tiny_ranges):
    def flaky_leaders(stat_group, start, end, **kwargs):
        if stat_group == "bat":
            raise RuntimeError("simulated FanGraphs failure")
        return _leader_rows(1)

    monkeypatch.setattr(fangraphs.fg, "get_leaders", flaky_leaders)
    _fake_guts(monkeypatch)
    _fake_park_factors(monkeypatch)
    _fake_prospects(monkeypatch)
    _fake_splits(monkeypatch)
    _fake_projections(monkeypatch)

    totals = fangraphs.bootstrap()

    assert totals.get("raw.fangraphs_batting", 0) == 0
    assert totals["raw.fangraphs_pitching"] > 0
    with db_conn.cursor() as cur:
        cur.execute("SELECT to_regclass('raw.fangraphs_batting')")
        assert cur.fetchone() == (None,)
        cur.execute("SELECT count(*) FROM raw.fangraphs_pitching")
        assert cur.fetchone()[0] > 0


def test_update_reloads_current_season_only(db_conn, monkeypatch, _tiny_ranges):
    _fake_leaders(monkeypatch)
    _fake_guts(monkeypatch)
    _fake_park_factors(monkeypatch)
    _fake_prospects(monkeypatch)
    _fake_splits(monkeypatch)
    _fake_projections(monkeypatch)

    fangraphs.bootstrap()
    fangraphs.update()

    with db_conn.cursor() as cur:
        cur.execute(
            "SELECT _season, count(*) FROM raw.fangraphs_batting GROUP BY _season ORDER BY 1"
        )
        assert cur.fetchall() == [("2025", 3), ("2026", 3)]


def test_update_is_idempotent(db_conn, monkeypatch, _tiny_ranges):
    _fake_leaders(monkeypatch)
    _fake_guts(monkeypatch)
    _fake_park_factors(monkeypatch)
    _fake_prospects(monkeypatch)
    _fake_splits(monkeypatch)
    _fake_projections(monkeypatch)

    fangraphs.update()
    fangraphs.update()

    with db_conn.cursor() as cur:
        for table in ("raw.fangraphs_batting", "raw.fangraphs_guts", "raw.fangraphs_projection"):
            cur.execute(f"SELECT count(*) FROM {table}")
            assert cur.fetchone()[0] > 0
        cur.execute("SELECT count(*) FROM raw.fangraphs_projection")
        assert cur.fetchone() == (2,)  # second update appended nothing


# --------------------------------------------------------------------------
# Health
# --------------------------------------------------------------------------


def test_health_check_reports_tables_run_and_freshness(db_conn, monkeypatch, _tiny_ranges):
    _fake_leaders(monkeypatch)
    _fake_guts(monkeypatch)
    _fake_park_factors(monkeypatch)
    _fake_prospects(monkeypatch)
    _fake_splits(monkeypatch)
    _fake_projections(monkeypatch)
    fangraphs.update()

    checks = fangraphs.health_check()
    names = {c.name for c in checks}

    assert "raw.fangraphs_batting" in names
    assert "raw.fangraphs_projection" in names
    assert f"{fangraphs.SOURCE} last run" in names
    assert f"{fangraphs.SOURCE} freshness" in names
    assert all(c.ok for c in checks), [(c.name, c.detail) for c in checks if not c.ok]
