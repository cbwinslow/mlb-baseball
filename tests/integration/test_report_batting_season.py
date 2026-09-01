"""gold.batting_season / gold.batting_team -- relation 3 of the grain-complete
statistic backbone (Plan 03B, ADR-278). Season and team roll-ups of
gold.batting_game, verified against hand-computed totals, including the
traded-player combined row and idempotency.
"""

import pytest

from mlb_baseball import report

_GAME_COLS = (
    "game_id",
    "player_id",
    "team_id",
    "season",
    "game_date",
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

_RATE_COLS = ("avg", "obp", "slg", "ops", "iso", "babip", "bb_pct", "k_pct")
_COUNT_COLS = _GAME_COLS[5:]  # pa .. gidp


def _blank_line(**kw):
    row = {c: 0 for c in _COUNT_COLS}
    row.update(kw)
    return row


def _seed_core(db_conn):
    with db_conn.cursor() as cur:
        cur.execute(
            "INSERT INTO core.team (id, retro_team_id, league, city, nickname, "
            "first_year, last_year) VALUES "
            "(7201, 'NYA', 'AL', 'New York', 'Yankees', 1903, 2026), "
            "(7202, 'BOS', 'AL', 'Boston', 'Red Sox', 1901, 2026) "
            "ON CONFLICT (id) DO NOTHING"
        )
        cur.execute(
            "INSERT INTO core.player (id, retro_id, last_name, first_name) VALUES "
            "(72001, 'aaa001', 'Solo', 'Sam'), "
            "(72002, 'bbb001', 'Traded', 'Tom') ON CONFLICT (id) DO NOTHING"
        )
        cur.execute(
            "INSERT INTO core.game (id, retro_game_id, season, game_date, game_number, "
            "home_team_id, away_team_id, game_type) VALUES "
            "(7290001, 'BS2023a', 2023, '2023-04-01', 0, 7201, 7202, 'regular'), "
            "(7290002, 'BS2023b', 2023, '2023-04-02', 0, 7201, 7202, 'regular'), "
            "(7290003, 'BS2023c', 2023, '2023-04-03', 0, 7202, 7201, 'regular') "
            "ON CONFLICT (id) DO NOTHING"
        )
    db_conn.commit()


def _seed_game_lines(db_conn, rows):
    with db_conn.cursor() as cur:
        for row in rows:
            cur.execute(
                "INSERT INTO gold.batting_game (" + ", ".join(_GAME_COLS) + ") "
                "VALUES (" + ", ".join(["%s"] * len(_GAME_COLS)) + ")",
                tuple(row[c] for c in _GAME_COLS),
            )
    db_conn.commit()


def _cleanup(db_conn):
    db_conn.rollback()
    with db_conn.cursor() as cur:
        cur.execute("DELETE FROM gold.batting_season WHERE season = 2023")
        cur.execute("DELETE FROM gold.batting_team WHERE season = 2023")
        cur.execute("DELETE FROM gold.batting_game WHERE season = 2023")
        cur.execute("DELETE FROM core.game WHERE id IN (7290001, 7290002, 7290003)")
        cur.execute("DELETE FROM core.player WHERE id IN (72001, 72002)")
        cur.execute("DELETE FROM core.team WHERE id IN (7201, 7202)")
    db_conn.commit()


def _season(db_conn, player_id, *, team_id):
    """One gold.batting_season row: the stint for team_id, or the combined
    row when team_id is None."""
    where = "team_id = %s" if team_id is not None else "team_id IS NULL AND is_combined"
    params = (player_id, team_id) if team_id is not None else (player_id,)
    with db_conn.cursor() as cur:
        cur.execute(
            "SELECT g, " + ", ".join(_COUNT_COLS) + ", " + ", ".join(_RATE_COLS) + ", is_combined "
            f"FROM gold.batting_season WHERE player_id = %s AND {where}",
            params,
        )
        row = cur.fetchone()
    if row is None:
        return None
    keys = ["g", *_COUNT_COLS, *_RATE_COLS, "is_combined"]
    return dict(zip(keys, row, strict=True))


def _build(db_conn):
    report._build_backbone_relation(
        db_conn, "gold.batting_season", report._BATTING_SEASON_SQL, source="gold.batting_game"
    )
    report._build_backbone_relation(
        db_conn, "gold.batting_team", report._BATTING_TEAM_SQL, source="gold.batting_game"
    )
    db_conn.commit()


def test_batting_season_rolls_a_single_team_player_into_one_season_line(db_conn):
    _cleanup(db_conn)
    _seed_core(db_conn)
    # Sam Solo, Yankees, 2 games:
    #   g1: PA4 AB4 R1 H2 (1x2B, 1xHR) TB6 RBI3 SO1
    #   g2: PA4 AB3 R1 H1 (1x1B) TB1 BB1 SF1
    _seed_game_lines(
        db_conn,
        [
            {
                "game_id": 7290001,
                "player_id": 72001,
                "team_id": 7201,
                "season": 2023,
                "game_date": "2023-04-01",
                **_blank_line(pa=4, ab=4, r=1, h=2, b2=1, hr=1, tb=6, rbi=3, so=1),
            },
            {
                "game_id": 7290002,
                "player_id": 72001,
                "team_id": 7201,
                "season": 2023,
                "game_date": "2023-04-02",
                **_blank_line(pa=4, ab=3, r=1, h=1, b1=1, tb=1, bb=1, sf=1),
            },
        ],
    )
    try:
        _build(db_conn)

        # season totals: g2 PA8 AB7 R2 H3 (1B1 2B1 HR1) TB7 RBI3 BB1 SF1 SO1
        expected_counts = {
            "pa": 8,
            "ab": 7,
            "r": 2,
            "h": 3,
            "b1": 1,
            "b2": 1,
            "b3": 0,
            "hr": 1,
            "tb": 7,
            "rbi": 3,
            "bb": 1,
            "ibb": 0,
            "hbp": 0,
            "sf": 1,
            "sh": 0,
            "so": 1,
            "gidp": 0,
        }
        stint = _season(db_conn, 72001, team_id=7201)
        assert stint is not None
        assert stint["g"] == 2
        assert stint["is_combined"] is False
        for k, v in expected_counts.items():
            assert stint[k] == v, k

        # AVG 3/7, OBP 4/9, SLG 7/7, OPS 4/9+1, ISO 1-3/7, BABIP 2/6, BB% 1/8, K% 1/8
        assert float(stint["avg"]) == pytest.approx(3 / 7)
        assert float(stint["obp"]) == pytest.approx(4 / 9)
        assert float(stint["slg"]) == pytest.approx(1.0)
        assert float(stint["ops"]) == pytest.approx(4 / 9 + 1.0)
        assert float(stint["iso"]) == pytest.approx(1.0 - 3 / 7)
        assert float(stint["babip"]) == pytest.approx(2 / 6)
        assert float(stint["bb_pct"]) == pytest.approx(1 / 8)
        assert float(stint["k_pct"]) == pytest.approx(1 / 8)

        # one-team player: the combined row equals the stint
        combined = _season(db_conn, 72001, team_id=None)
        assert combined is not None
        assert combined["is_combined"] is True
        for k, v in expected_counts.items():
            assert combined[k] == v, k
        assert float(combined["avg"]) == pytest.approx(3 / 7)
    finally:
        _cleanup(db_conn)


def test_batting_season_traded_player_gets_two_stints_and_a_combined_row(db_conn):
    _cleanup(db_conn)
    _seed_core(db_conn)
    # Tom Traded: Yankees (g1), then Red Sox (g3).
    #   NYA: PA3 AB3 H1 (1B) TB1 SO1
    #   BOS: PA4 AB4 R1 H2 (2x 1B) TB2 RBI1
    _seed_game_lines(
        db_conn,
        [
            {
                "game_id": 7290001,
                "player_id": 72002,
                "team_id": 7201,
                "season": 2023,
                "game_date": "2023-04-01",
                **_blank_line(pa=3, ab=3, h=1, b1=1, tb=1, so=1),
            },
            {
                "game_id": 7290003,
                "player_id": 72002,
                "team_id": 7202,
                "season": 2023,
                "game_date": "2023-04-03",
                **_blank_line(pa=4, ab=4, r=1, h=2, b1=2, tb=2, rbi=1),
            },
        ],
    )
    try:
        _build(db_conn)

        nya = _season(db_conn, 72002, team_id=7201)
        bos = _season(db_conn, 72002, team_id=7202)
        assert nya["g"] == 1 and nya["pa"] == 3 and nya["h"] == 1
        assert float(nya["avg"]) == pytest.approx(1 / 3)
        assert bos["g"] == 1 and bos["pa"] == 4 and bos["h"] == 2
        assert float(bos["avg"]) == pytest.approx(2 / 4)

        # combined: g2 PA7 AB7 R1 H3 (1B3) TB3 RBI1 SO1
        comb = _season(db_conn, 72002, team_id=None)
        assert comb["is_combined"] is True
        assert comb["g"] == 2
        assert comb["pa"] == 7 and comb["ab"] == 7 and comb["h"] == 3
        assert comb["b1"] == 3 and comb["tb"] == 3 and comb["rbi"] == 1 and comb["so"] == 1
        # combined AVG is total H / total AB, NOT the mean of the two stint AVGs
        assert float(comb["avg"]) == pytest.approx(3 / 7)
        assert float(comb["obp"]) == pytest.approx(3 / 7)  # no BB/HBP/SF
        assert float(comb["slg"]) == pytest.approx(3 / 7)
        assert float(comb["k_pct"]) == pytest.approx(1 / 7)
    finally:
        _cleanup(db_conn)


def test_batting_season_rebuild_is_idempotent(db_conn):
    _cleanup(db_conn)
    _seed_core(db_conn)
    _seed_game_lines(
        db_conn,
        [
            {
                "game_id": 7290001,
                "player_id": 72001,
                "team_id": 7201,
                "season": 2023,
                "game_date": "2023-04-01",
                **_blank_line(pa=4, ab=4, h=2, b2=1, hr=1, tb=6),
            },
        ],
    )
    try:
        _build(db_conn)
        first = _season(db_conn, 72001, team_id=7201)
        _build(db_conn)
        assert _season(db_conn, 72001, team_id=7201) == first
        with db_conn.cursor() as cur:
            cur.execute("SELECT count(*) FROM gold.batting_season WHERE season = 2023")
            # 1 stint + 1 combined
            assert cur.fetchone()[0] == 2
    finally:
        _cleanup(db_conn)


def test_batting_team_rolls_every_player_line_into_one_row_per_team(db_conn):
    _cleanup(db_conn)
    _seed_core(db_conn)
    # Two Yankees in one game + one in a second game.
    _seed_game_lines(
        db_conn,
        [
            {
                "game_id": 7290001,
                "player_id": 72001,
                "team_id": 7201,
                "season": 2023,
                "game_date": "2023-04-01",
                **_blank_line(pa=4, ab=4, h=2, b1=1, hr=1, tb=5, r=1, rbi=1, so=1),
            },
            {
                "game_id": 7290001,
                "player_id": 72002,
                "team_id": 7201,
                "season": 2023,
                "game_date": "2023-04-01",
                **_blank_line(pa=3, ab=2, h=1, b1=1, tb=1, bb=1, r=1),
            },
            {
                "game_id": 7290002,
                "player_id": 72001,
                "team_id": 7201,
                "season": 2023,
                "game_date": "2023-04-02",
                **_blank_line(pa=4, ab=4, h=1, b1=1, tb=1, so=2),
            },
        ],
    )
    try:
        _build(db_conn)
        with db_conn.cursor() as cur:
            cur.execute(
                "SELECT g, pa, ab, h, b1, hr, tb, r, rbi, bb, so, avg, obp, slg "
                "FROM gold.batting_team WHERE team_id = 7201 AND season = 2023"
            )
            row = cur.fetchone()
        g, pa, ab, h, b1, hr, tb, r, rbi, bb, so, avg, obp, slg = row
        # 2 distinct games; totals PA11 AB10 H4 (1B3, HR1) TB7 R2 RBI1 BB1 SO3
        assert g == 2
        assert (pa, ab, h, b1, hr, tb, r, rbi, bb, so) == (11, 10, 4, 3, 1, 7, 2, 1, 1, 3)
        assert float(avg) == pytest.approx(4 / 10)
        assert float(obp) == pytest.approx((4 + 1) / (10 + 1))  # (H+BB)/(AB+BB), no HBP/SF
        assert float(slg) == pytest.approx(7 / 10)
    finally:
        _cleanup(db_conn)


def test_batting_season_season_param_scopes_the_rebuild(db_conn):
    _cleanup(db_conn)
    _seed_core(db_conn)
    _seed_game_lines(
        db_conn,
        [
            {
                "game_id": 7290001,
                "player_id": 72001,
                "team_id": 7201,
                "season": 2023,
                "game_date": "2023-04-01",
                **_blank_line(pa=4, ab=4, h=2, tb=2),
            },
        ],
    )
    try:
        with db_conn.cursor() as cur:
            cur.execute("TRUNCATE gold.batting_season")
            cur.execute(report._BATTING_SEASON_SQL, {"season": 2022})
        db_conn.commit()
        with db_conn.cursor() as cur:
            cur.execute("SELECT count(*) FROM gold.batting_season WHERE season = 2023")
            assert cur.fetchone()[0] == 0
        with db_conn.cursor() as cur:
            cur.execute("TRUNCATE gold.batting_season")
            cur.execute(report._BATTING_SEASON_SQL, {"season": 2023})
        db_conn.commit()
        with db_conn.cursor() as cur:
            cur.execute("SELECT count(*) FROM gold.batting_season WHERE season = 2023")
            assert cur.fetchone()[0] == 2
    finally:
        _cleanup(db_conn)


def test_report_health_check_includes_the_season_and_team_rollups(db_conn):
    _cleanup(db_conn)
    _seed_core(db_conn)
    _seed_game_lines(
        db_conn,
        [
            {
                "game_id": 7290001,
                "player_id": 72001,
                "team_id": 7201,
                "season": 2023,
                "game_date": "2023-04-01",
                **_blank_line(pa=4, ab=4, h=2, b2=1, hr=1, tb=6),
            },
            {
                "game_id": 7290003,
                "player_id": 72002,
                "team_id": 7202,
                "season": 2023,
                "game_date": "2023-04-03",
                **_blank_line(pa=3, ab=3, h=1, b1=1, tb=1),
            },
        ],
    )
    try:
        _build(db_conn)
        checks = {c.name: c for c in report.health_check()}
        season_cov = next(c for n, c in checks.items() if "get a gold.batting_season row" in n)
        team_cov = next(c for n, c in checks.items() if "get a gold.batting_team row" in n)
        assert season_cov.ok, season_cov.detail
        assert team_cov.ok, team_cov.detail
        assert any("gold.batting_season" in n for n in checks)
        assert any("gold.batting_team" in n for n in checks)
    finally:
        _cleanup(db_conn)
