"""feature-store-v1 slice 1 -- the DuckDB feature build (mlb_baseball.feat).

Hand-built fixture: 2 batters + 2 pitchers across 5 regular games (one a
same-day doubleheader) plus one postseason game, seeded directly into
core/gold. Rolling windows are small enough to check by hand.

The clock (feat.py): event_ts = game_date + game_number * 3h; a form row's
available_ts == visible_ts == its event_ts (the value is entering form). The
6h lag lives in the rolling-window frame: doubleheader game 1 (event 03:00)
is > game 2's event_ts (06:00) minus 6h, so game 2's windows exclude it.
"""

import os
from datetime import timedelta

import duckdb
import pytest

from mlb_baseball import feat

SEASON = 2024

# (id, retro_game_id, date, game_number, home, away, home_score, away_score, type)
_GAMES = [
    (7900001, "TST202404010", "2024-04-01", 0, 7101, 7102, 5, 3, "regular"),
    (7900002, "TST202404150", "2024-04-15", 0, 7101, 7102, 4, 6, "regular"),
    (7900003, "TST202404180", "2024-04-18", 0, 7101, 7102, 2, 1, "regular"),
    (7900004, "TST202404201", "2024-04-20", 1, 7101, 7102, 3, 2, "regular"),  # DH game 1
    (7900005, "TST202404202", "2024-04-20", 2, 7101, 7102, 7, 1, "regular"),  # DH game 2
    (7900006, "TST202410010", "2024-10-01", 0, 7101, 7102, 1, 0, "wildcard"),  # excluded
]

# batter 70001 (team 7101, home): PA differs per game so a summed-numerator
# rate != a mean of per-game rates.
_B1 = {
    7900001: dict(pa=5, ab=5, h=1, b1=1, tb=1, so=3),
    7900002: dict(pa=10, ab=10, h=0, tb=0, so=5),
    7900003: dict(pa=2, ab=2, h=1, b1=1, tb=1, so=0),
    7900004: dict(pa=3, ab=3, h=0, tb=0, so=1),  # DH game 1
    7900005: dict(pa=6, ab=6, h=3, b2=3, tb=6, so=0),  # DH game 2
    7900006: dict(pa=4, ab=4, h=2, b2=2, tb=4, so=0),  # postseason, must be ignored
}
# batter 70002 (team 7102, away)
_B2 = {
    7900001: dict(pa=4, ab=4, h=1, b1=1, tb=1, so=1),
    7900002: dict(pa=5, ab=4, h=2, b1=1, hr=1, tb=5, so=1, bb=1),
    7900003: dict(pa=3, ab=3, h=0, tb=0, so=2),
    7900004: dict(pa=4, ab=4, h=1, b2=1, tb=2, so=0),
    7900005: dict(pa=4, ab=3, h=1, b1=1, tb=1, so=1, bb=1),
}
# pitcher 70003 (team 7101) starts every game; pitcher 70004 (team 7102) too.
_P1 = {
    7900001: dict(bf=20, outs=15, so=6, bb=2, r=3, hr=1),
    7900002: dict(bf=25, outs=18, so=8, bb=1, r=2, hr=0, hbp=1),
    7900003: dict(bf=22, outs=21, so=10, bb=0, r=1, hr=0),
    7900004: dict(bf=18, outs=12, so=4, bb=3, r=4, hr=2),
    7900005: dict(bf=24, outs=20, so=7, bb=2, r=2, hr=1),
}
_P2 = {
    7900001: dict(bf=21, outs=15, so=4, bb=3, r=5, hr=1),
    7900002: dict(bf=26, outs=24, so=9, bb=1, r=1, hr=0),
    7900003: dict(bf=20, outs=18, so=5, bb=2, r=2, hr=1),
    7900004: dict(bf=19, outs=15, so=6, bb=1, r=3, hr=1),
    7900005: dict(bf=23, outs=18, so=8, bb=2, r=4, hr=2),
}

_BAT_COLS = (
    "pa",
    "ab",
    "r",
    "h",
    "b1",
    "b2",
    "b3",
    "hr",
    "tb",
    "rbi",
    "bb",
    "ibb",
    "hbp",
    "sf",
    "sh",
    "so",
    "gidp",
)
_PIT_COLS = (
    "gs",
    "bf",
    "outs",
    "h",
    "r",
    "bb",
    "ibb",
    "so",
    "hr",
    "hbp",
    "wp",
    "bk",
    "w",
    "l",
    "sv",
)


def _cleanup(db_conn):
    db_conn.rollback()
    game_ids = [g[0] for g in _GAMES]
    with db_conn.cursor() as cur:
        cur.execute("DELETE FROM gold.batting_game WHERE game_id = ANY(%s)", (game_ids,))
        cur.execute("DELETE FROM gold.pitching_game WHERE game_id = ANY(%s)", (game_ids,))
        cur.execute("DELETE FROM core.game WHERE id = ANY(%s)", (game_ids,))
        cur.execute("DELETE FROM core.player WHERE id = ANY(%s)", ([70001, 70002, 70003, 70004],))
        cur.execute("DELETE FROM core.team WHERE id = ANY(%s)", ([7101, 7102],))
    db_conn.commit()


def _insert_line(cur, table, cols, game_id, player_id, team_id, date, values):
    row = {c: 0 for c in cols}
    row.update(values)
    names = ["game_id", "player_id", "team_id", "season", "game_date", *cols]
    cur.execute(
        f"INSERT INTO {table} ({', '.join(names)}) VALUES ({', '.join(['%s'] * len(names))})",
        (game_id, player_id, team_id, SEASON, date, *(row[c] for c in cols)),
    )


def _seed(db_conn):
    _cleanup(db_conn)
    with db_conn.cursor() as cur:
        cur.execute(
            "INSERT INTO core.team (id, retro_team_id, league, city, nickname, "
            "first_year, last_year) VALUES "
            "(7101, 'TSA', 'AL', 'Test', 'Alphas', 1901, 2026), "
            "(7102, 'TSB', 'AL', 'Test', 'Betas', 1901, 2026)"
        )
        cur.execute(
            "INSERT INTO core.player (id, retro_id, last_name, first_name) VALUES "
            "(70001, 'bat001', 'Batter', 'One'), (70002, 'bat002', 'Batter', 'Two'), "
            "(70003, 'pit001', 'Pitcher', 'One'), (70004, 'pit002', 'Pitcher', 'Two')"
        )
        for gid, retro, date, gn, home, away, hs, as_, gtype in _GAMES:
            cur.execute(
                "INSERT INTO core.game (id, retro_game_id, season, game_date, "
                "game_number, home_team_id, away_team_id, home_score, away_score, "
                "game_type) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                (gid, retro, SEASON, date, gn, home, away, hs, as_, gtype),
            )
        by_id = {g[0]: g for g in _GAMES}
        for gid, vals in _B1.items():
            _insert_line(cur, "gold.batting_game", _BAT_COLS, gid, 70001, 7101, by_id[gid][2], vals)
        for gid, vals in _B2.items():
            _insert_line(cur, "gold.batting_game", _BAT_COLS, gid, 70002, 7102, by_id[gid][2], vals)
        for gid, vals in _P1.items():
            _insert_line(
                cur,
                "gold.pitching_game",
                _PIT_COLS,
                gid,
                70003,
                7101,
                by_id[gid][2],
                {**vals, "gs": 1},
            )
        for gid, vals in _P2.items():
            _insert_line(
                cur,
                "gold.pitching_game",
                _PIT_COLS,
                gid,
                70004,
                7102,
                by_id[gid][2],
                {**vals, "gs": 1},
            )
    db_conn.commit()


@pytest.fixture
def built(db_conn, tmp_path):
    _seed(db_conn)
    dbfile = tmp_path / "feat.duckdb"
    pg_url = os.environ["DATABASE_URL"]
    try:
        counts = feat.build(duckdb_path=dbfile, pg_url=pg_url, feature_version="v1")
        yield dbfile, counts
    finally:
        _cleanup(db_conn)


def _q(dbfile, sql, params=None):
    con = duckdb.connect()
    try:
        con.execute(f"ATTACH '{dbfile}' AS mlbfeat (READ_ONLY)")
        con.execute("USE mlbfeat")
        return con.execute(sql, params or []).fetchall()
    finally:
        con.close()


def _row(dbfile, sql, params=None):
    rows = _q(dbfile, sql, params)
    assert len(rows) == 1, f"expected 1 row, got {len(rows)}"
    return rows[0]


def test_build_returns_row_counts(built):
    _dbfile, counts = built
    # 2 batters * 5 regular games, 2 pitchers * 5 regular games, 5 games.
    assert counts == {
        "feat.player_form": 10,
        "feat.pitcher_form": 10,
        "feat.game": 5,
    }


def test_one_row_per_player_event_version_and_no_window_column(built):
    dbfile, _counts = built
    cols = {r[0] for r in _q(dbfile, "PRAGMA table_info('feat.player_form')")}
    assert "window" not in cols
    (dupes,) = _row(
        dbfile,
        "SELECT count(*) FROM (SELECT player_id, event_ts, feature_version "
        "FROM feat.player_form GROUP BY 1, 2, 3 HAVING count(*) > 1)",
    )
    assert dupes == 0


def test_postseason_game_is_excluded(built):
    dbfile, _counts = built
    (n,) = _row(
        dbfile,
        "SELECT count(*) FROM feat.player_form WHERE retro_game_id = 'TST202410010'",
    )
    assert n == 0


def test_first_game_window_rate_is_null_not_zero(built):
    dbfile, _counts = built
    pa, so_num, k_pct = _row(
        dbfile,
        "SELECT pa_7d, so_num_7d, k_pct_7d FROM feat.player_form "
        "WHERE player_id = 70001 AND retro_game_id = 'TST202404010'",
    )
    assert pa == 0
    assert so_num == 0
    assert k_pct is None


def test_window_rate_is_summed_numerator_over_summed_denominator(built):
    dbfile, _counts = built
    # batter 70001, doubleheader game 2 (event 2024-04-20 06:00). 7d window
    # ends 6h earlier (00:00), so it sees 2024-04-15 (pa 10, so 5) and
    # 2024-04-18 (pa 2, so 0) -- NOT the DH game 1 line at 03:00.
    pa, so_num, k_pct = _row(
        dbfile,
        "SELECT pa_7d, so_num_7d, k_pct_7d FROM feat.player_form "
        "WHERE player_id = 70001 AND retro_game_id = 'TST202404202'",
    )
    assert pa == 12
    assert so_num == 5
    assert k_pct == pytest.approx(5 / 12)  # not (0.5 + 0.0) / 2 == 0.25


def test_doubleheader_game_2_excludes_game_1_box_score(built):
    dbfile, _counts = built
    # DH game 2's 30d/std windows: 2024-04-01 + 04-15 + 04-18 only.
    pa30, so30, pastd, sostd = _row(
        dbfile,
        "SELECT pa_30d, so_num_30d, pa_std, so_num_std FROM feat.player_form "
        "WHERE player_id = 70001 AND retro_game_id = 'TST202404202'",
    )
    assert (pa30, so30) == (17, 8)  # 5+10+2, 3+5+0  -- DH game 1 (pa 3, so 1) not included
    assert (pastd, sostd) == (17, 8)


def test_clock_ordering_holds_on_every_row(built):
    dbfile, _counts = built
    for relation in ("feat.player_form", "feat.pitcher_form", "feat.game"):
        (bad,) = _row(
            dbfile,
            f"SELECT count(*) FROM {relation} "
            "WHERE NOT (event_ts <= available_ts AND available_ts <= visible_ts)",
        )
        assert bad == 0, relation


def test_lag_constant_drives_the_window_frame_not_available_ts(built, tmp_path, monkeypatch):
    """The lag lives in the rolling-window frame, not in available_ts (a form
    row's value is entering form, knowable at first pitch). Proof: a form row's
    available_ts equals its event_ts regardless of the lag; but shrinking the
    lag from 6h to 3h lets doubleheader game 1 (event 03:00) into game 2's
    (event 06:00) window, so game 2's numerators change.
    """
    dbfile, _counts = built
    (delta,) = _row(dbfile, "SELECT available_ts - event_ts FROM feat.player_form LIMIT 1")
    assert delta == timedelta(0)

    dh2_6h = _row(
        dbfile,
        "SELECT pa_std, so_num_std FROM feat.player_form "
        "WHERE player_id = 70001 AND retro_game_id = 'TST202404202'",
    )

    monkeypatch.setattr(feat, "AVAILABLE_LAG_HOURS", 3)
    other = tmp_path / "feat_lag3.duckdb"
    feat.build(duckdb_path=other, pg_url=os.environ["DATABASE_URL"], feature_version="v1")
    (delta3,) = _row(other, "SELECT available_ts - event_ts FROM feat.player_form LIMIT 1")
    assert delta3 == timedelta(0)  # still event_ts
    dh2_3h = _row(
        other,
        "SELECT pa_std, so_num_std FROM feat.player_form "
        "WHERE player_id = 70001 AND retro_game_id = 'TST202404202'",
    )
    assert dh2_3h != dh2_6h  # game 1 now inside game 2's window
    # game 1 was pa=3, so=1; with lag 3h it enters game 2's std window
    assert dh2_3h[0] == dh2_6h[0] + 3
    assert dh2_3h[1] == dh2_6h[1] + 1


def test_pitcher_form_rates_and_fip_like(built):
    dbfile, _counts = built
    # pitcher 70003, DH game 2. 30d window: 2024-04-01 + 04-15 + 04-18.
    bf, so_num, k_pct, k_bb, ra9, fip = _row(
        dbfile,
        "SELECT bf_30d, so_num_30d, k_pct_30d, k_minus_bb_pct_30d, ra9_30d, fip_like_30d "
        "FROM feat.pitcher_form WHERE player_id = 70003 AND retro_game_id = 'TST202404202'",
    )
    assert bf == 67  # 20 + 25 + 22
    assert so_num == 24  # 6 + 8 + 10
    assert k_pct == pytest.approx(24 / 67)
    assert k_bb == pytest.approx((24 - 3) / 67)  # bb 2 + 1 + 0
    assert ra9 == pytest.approx(6 * 27 / 54)  # r 3+2+1, outs 15+18+21
    assert fip == pytest.approx((13 * 1 + 3 * (3 + 1) - 2 * 24) / (54 / 3.0) + 3.1)


def test_feat_game_form_columns_match_manual_rollup(built):
    dbfile, _counts = built
    # DH game 2. Home team 7101 offensive form = batter 70001's 30d rollup
    # (2024-04-01 + 04-15 + 04-18): pa 17, so 8.
    home_k, home_bb, home_slg, starter_bf, starter_kbb, actual = _row(
        dbfile,
        "SELECT home_k_pct_30d, home_bb_pct_30d, home_slg_30d, "
        "home_starter_bf_30d, home_starter_k_minus_bb_pct_30d, starter_is_actual "
        "FROM feat.game WHERE game_pk = 'TST202404202'",
    )
    assert home_k == pytest.approx(8 / 17)
    assert home_bb == pytest.approx(0.0)
    assert home_slg == pytest.approx(2 / 17)  # tb 1 + 0 + 1, ab 5 + 10 + 2
    assert starter_bf == 67
    assert starter_kbb == pytest.approx((24 - 3) / 67)
    assert actual is True


def test_feat_game_home_win_label(built):
    dbfile, _counts = built
    wins = dict(_q(dbfile, "SELECT game_pk, home_win FROM feat.game ORDER BY game_pk"))
    assert wins["TST202404010"] is True  # 5-3
    assert wins["TST202404150"] is False  # 4-6


def test_append_only_second_version_leaves_v1_byte_identical(built, db_conn):
    dbfile, _counts = built
    before = _q(
        dbfile,
        "SELECT * FROM feat.player_form WHERE feature_version = 'v1' ORDER BY player_id, event_ts",
    )
    feat.build(duckdb_path=dbfile, pg_url=os.environ["DATABASE_URL"], feature_version="v2")
    after = _q(
        dbfile,
        "SELECT * FROM feat.player_form WHERE feature_version = 'v1' ORDER BY player_id, event_ts",
    )
    assert after == before
    (v2,) = _row(dbfile, "SELECT count(*) FROM feat.player_form WHERE feature_version = 'v2'")
    assert v2 == 10
    (both,) = _row(dbfile, "SELECT count(DISTINCT feature_version) FROM feat.player_form")
    assert both == 2


def test_feat_sql_files_never_read_gold_game_feature():
    from mlb_baseball.sql import read_sql

    for name in ("feat_player_form.sql", "feat_pitcher_form.sql", "feat_game.sql"):
        assert "game_feature" not in read_sql(f"duckdb/{name}")


def test_health_check_passes_on_a_clean_build(built):
    dbfile, _counts = built
    checks = feat.health_check(duckdb_path=dbfile)
    assert checks
    assert all(c.ok for c in checks), [(c.name, c.detail) for c in checks if not c.ok]


def test_health_check_reports_missing_build(tmp_path):
    checks = feat.health_check(duckdb_path=tmp_path / "nope.duckdb")
    assert len(checks) == 1
    assert not checks[0].ok
    assert "mlb build" in checks[0].detail


def test_leakage_checks_pass_on_a_real_build(built):
    # Task 6.4: the two store-level leakage checks run green against an
    # actual `feat.build`, not just hand-built fixtures. CI exercises this
    # via the normal full-suite run.
    from mlb_research import leakage_checks

    dbfile, _counts = built
    results = leakage_checks.run_all(dbfile)
    assert [r.name for r in results] == ["clock_consistency", "doubleheader_ordering"]
    assert all(results), [(r.name, r.detail) for r in results if not r.ok]


def test_doubleheader_check_goes_red_if_game_1_leaks_into_game_2(built):
    # The failure mode task 6.4 names: if the builder let the first game of a
    # doubleheader enter the second game's window, game 2's rolling numerators
    # would differ from game 1's. Simulate that by bumping one game-2 numerator
    # in a writable copy of the build and confirm the check catches it.
    import shutil

    from mlb_research import leakage_checks

    dbfile, _counts = built
    leaky = dbfile.parent / "leaky.duckdb"
    shutil.copy(dbfile, leaky)
    con = duckdb.connect(str(leaky))
    try:
        con.execute(
            "UPDATE feat.player_form SET so_num_std = so_num_std + 1 "
            "WHERE player_id = 70001 AND retro_game_id = 'TST202404202'"
        )
    finally:
        con.close()

    result = leakage_checks.check_doubleheader_ordering(leaky)
    assert not result.ok
    assert not result.evidence.empty
