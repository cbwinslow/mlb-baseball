"""gold.pitching_season / gold.pitching_team -- relation 4 of the
grain-complete statistic backbone (Plan 03B, ADR-278). Season and team
roll-ups of gold.pitching_game, verified against hand-computed totals,
including the traded-pitcher combined row and idempotency.
"""

import pytest

from mlb_baseball import report

_GAME_COLS = (
    "game_id",
    "player_id",
    "team_id",
    "season",
    "game_date",
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
_COUNT_COLS = _GAME_COLS[5:]
_RATE_COLS = ("ra9", "whip", "k9", "bb9", "hr9", "k_bb")


def _blank(**kw):
    row = {c: 0 for c in _COUNT_COLS}
    row.update(kw)
    return row


def _seed_core(db_conn):
    with db_conn.cursor() as cur:
        cur.execute(
            "INSERT INTO core.team (id, retro_team_id, league, city, nickname, "
            "first_year, last_year) VALUES "
            "(7301, 'NYA', 'AL', 'New York', 'Yankees', 1903, 2026), "
            "(7302, 'BOS', 'AL', 'Boston', 'Red Sox', 1901, 2026) "
            "ON CONFLICT (id) DO NOTHING"
        )
        cur.execute(
            "INSERT INTO core.player (id, retro_id, last_name, first_name) VALUES "
            "(73001, 'ppp001', 'Solo', 'Pat'), "
            "(73002, 'qqq001', 'Dealt', 'Dan') ON CONFLICT (id) DO NOTHING"
        )
        cur.execute(
            "INSERT INTO core.game (id, retro_game_id, season, game_date, game_number, "
            "home_team_id, away_team_id, game_type) VALUES "
            "(7390001, 'PS2023a', 2023, '2023-04-01', 0, 7301, 7302, 'regular'), "
            "(7390002, 'PS2023b', 2023, '2023-04-02', 0, 7301, 7302, 'regular'), "
            "(7390003, 'PS2023c', 2023, '2023-04-03', 0, 7302, 7301, 'regular') "
            "ON CONFLICT (id) DO NOTHING"
        )
    db_conn.commit()


def _seed_game_lines(db_conn, rows):
    with db_conn.cursor() as cur:
        for row in rows:
            cur.execute(
                "INSERT INTO gold.pitching_game (" + ", ".join(_GAME_COLS) + ") "
                "VALUES (" + ", ".join(["%s"] * len(_GAME_COLS)) + ")",
                tuple(row[c] for c in _GAME_COLS),
            )
    db_conn.commit()


def _cleanup(db_conn):
    db_conn.rollback()
    with db_conn.cursor() as cur:
        cur.execute("DELETE FROM gold.pitching_season WHERE season = 2023")
        cur.execute("DELETE FROM gold.pitching_team WHERE season = 2023")
        cur.execute("DELETE FROM gold.pitching_game WHERE season = 2023")
        cur.execute("DELETE FROM core.game WHERE id IN (7390001, 7390002, 7390003)")
        cur.execute("DELETE FROM core.player WHERE id IN (73001, 73002)")
        cur.execute("DELETE FROM core.team WHERE id IN (7301, 7302)")
    db_conn.commit()


def _season(db_conn, player_id, *, team_id):
    where = "team_id = %s" if team_id is not None else "team_id IS NULL AND is_combined"
    params = (player_id, team_id) if team_id is not None else (player_id,)
    with db_conn.cursor() as cur:
        cur.execute(
            "SELECT g, " + ", ".join(_COUNT_COLS) + ", " + ", ".join(_RATE_COLS) + ", is_combined "
            f"FROM gold.pitching_season WHERE player_id = %s AND {where}",
            params,
        )
        row = cur.fetchone()
    if row is None:
        return None
    keys = ["g", *_COUNT_COLS, *_RATE_COLS, "is_combined"]
    return dict(zip(keys, row, strict=True))


def _build(db_conn):
    report._build_backbone_relation(
        db_conn, "gold.pitching_season", report._PITCHING_SEASON_SQL, source="gold.pitching_game"
    )
    report._build_backbone_relation(
        db_conn, "gold.pitching_team", report._PITCHING_TEAM_SQL, source="gold.pitching_game"
    )
    db_conn.commit()


def test_pitching_season_rolls_a_single_team_pitcher_into_one_line(db_conn):
    _cleanup(db_conn)
    _seed_core(db_conn)
    # Pat Solo, Yankees:
    #   g1 (start): BF10 outs6 H3 R2 BB1 SO4 HR1 W1
    #   g2 (relief): BF4 outs3 H1 SO2
    _seed_game_lines(
        db_conn,
        [
            {
                "game_id": 7390001,
                "player_id": 73001,
                "team_id": 7301,
                "season": 2023,
                "game_date": "2023-04-01",
                **_blank(gs=1, bf=10, outs=6, h=3, r=2, bb=1, so=4, hr=1, w=1),
            },
            {
                "game_id": 7390002,
                "player_id": 73001,
                "team_id": 7301,
                "season": 2023,
                "game_date": "2023-04-02",
                **_blank(gs=0, bf=4, outs=3, h=1, so=2),
            },
        ],
    )
    try:
        _build(db_conn)
        stint = _season(db_conn, 73001, team_id=7301)
        assert stint is not None
        assert stint["is_combined"] is False
        assert stint["g"] == 2
        expected = {
            "gs": 1,
            "bf": 14,
            "outs": 9,
            "h": 4,
            "r": 2,
            "bb": 1,
            "ibb": 0,
            "so": 6,
            "hr": 1,
            "hbp": 0,
            "wp": 0,
            "bk": 0,
            "w": 1,
            "l": 0,
            "sv": 0,
        }
        for k, v in expected.items():
            assert stint[k] == v, k
        # outs 9 = 3.0 IP. RA9 = 2*27/9 = 6, WHIP = 5*3/9, K9 = 6*27/9 = 18,
        # BB9 = 27/9 = 3, HR9 = 27/9 = 3, K:BB = 6/1 = 6
        assert float(stint["ra9"]) == pytest.approx(6.0)
        assert float(stint["whip"]) == pytest.approx(5 * 3 / 9)
        assert float(stint["k9"]) == pytest.approx(18.0)
        assert float(stint["bb9"]) == pytest.approx(3.0)
        assert float(stint["hr9"]) == pytest.approx(3.0)
        assert float(stint["k_bb"]) == pytest.approx(6.0)

        combined = _season(db_conn, 73001, team_id=None)
        assert combined["is_combined"] is True
        for k, v in expected.items():
            assert combined[k] == v, k
        assert float(combined["ra9"]) == pytest.approx(6.0)
    finally:
        _cleanup(db_conn)


def test_pitching_season_traded_pitcher_gets_two_stints_and_a_combined_row(db_conn):
    _cleanup(db_conn)
    _seed_core(db_conn)
    # Dan Dealt: Yankees (g1), Red Sox (g3).
    #   NYA: BF12 outs9 H4 R3 BB2 SO5 HR1 L1
    #   BOS: BF6 outs6 H1 R0 SO3 SV1
    _seed_game_lines(
        db_conn,
        [
            {
                "game_id": 7390001,
                "player_id": 73002,
                "team_id": 7301,
                "season": 2023,
                "game_date": "2023-04-01",
                **_blank(gs=1, bf=12, outs=9, h=4, r=3, bb=2, so=5, hr=1, l=1),
            },
            {
                "game_id": 7390003,
                "player_id": 73002,
                "team_id": 7302,
                "season": 2023,
                "game_date": "2023-04-03",
                **_blank(gs=0, bf=6, outs=6, h=1, r=0, so=3, sv=1),
            },
        ],
    )
    try:
        _build(db_conn)
        nya = _season(db_conn, 73002, team_id=7301)
        bos = _season(db_conn, 73002, team_id=7302)
        assert nya["outs"] == 9 and nya["r"] == 3 and nya["l"] == 1
        assert bos["outs"] == 6 and bos["r"] == 0 and bos["sv"] == 1

        comb = _season(db_conn, 73002, team_id=None)
        assert comb["is_combined"] is True
        assert comb["g"] == 2
        assert comb["gs"] == 1
        # totals: BF18 outs15 H5 R3 BB2 SO8 HR1 L1 SV1
        assert (comb["bf"], comb["outs"], comb["h"], comb["r"], comb["bb"], comb["so"]) == (
            18,
            15,
            5,
            3,
            2,
            8,
        )
        assert comb["l"] == 1 and comb["sv"] == 1
        # RA9 = 3 * 27 / 15 = 5.4, WHIP = 7 * 3 / 15 = 1.4, K:BB = 8/2 = 4
        assert float(comb["ra9"]) == pytest.approx(3 * 27 / 15)
        assert float(comb["whip"]) == pytest.approx(7 * 3 / 15)
        assert float(comb["k_bb"]) == pytest.approx(4.0)
    finally:
        _cleanup(db_conn)


def test_pitching_season_rebuild_is_idempotent(db_conn):
    _cleanup(db_conn)
    _seed_core(db_conn)
    _seed_game_lines(
        db_conn,
        [
            {
                "game_id": 7390001,
                "player_id": 73001,
                "team_id": 7301,
                "season": 2023,
                "game_date": "2023-04-01",
                **_blank(gs=1, bf=10, outs=15, h=3, r=1, so=6),
            },
        ],
    )
    try:
        _build(db_conn)
        first = _season(db_conn, 73001, team_id=7301)
        _build(db_conn)
        assert _season(db_conn, 73001, team_id=7301) == first
        with db_conn.cursor() as cur:
            cur.execute("SELECT count(*) FROM gold.pitching_season WHERE season = 2023")
            assert cur.fetchone()[0] == 2  # 1 stint + 1 combined
    finally:
        _cleanup(db_conn)


def test_pitching_team_rolls_every_pitcher_line_into_one_row_per_team(db_conn):
    _cleanup(db_conn)
    _seed_core(db_conn)
    _seed_game_lines(
        db_conn,
        [
            {
                "game_id": 7390001,
                "player_id": 73001,
                "team_id": 7301,
                "season": 2023,
                "game_date": "2023-04-01",
                **_blank(gs=1, bf=20, outs=18, h=5, r=2, bb=1, so=8, hr=1),
            },
            {
                "game_id": 7390001,
                "player_id": 73002,
                "team_id": 7301,
                "season": 2023,
                "game_date": "2023-04-01",
                **_blank(gs=0, bf=6, outs=6, h=2, r=1, bb=1, so=1),
            },
            {
                "game_id": 7390002,
                "player_id": 73001,
                "team_id": 7301,
                "season": 2023,
                "game_date": "2023-04-02",
                **_blank(gs=1, bf=15, outs=15, h=3, r=0, so=5),
            },
        ],
    )
    try:
        _build(db_conn)
        with db_conn.cursor() as cur:
            cur.execute(
                "SELECT g, gs, bf, outs, h, r, bb, so, hr, ra9, whip, k9 "
                "FROM gold.pitching_team WHERE team_id = 7301 AND season = 2023"
            )
            g, gs, bf, outs, h, r, bb, so, hr, ra9, whip, k9 = cur.fetchone()
        # 2 distinct games; totals GS2 BF41 outs39 H10 R3 BB2 SO14 HR1
        assert g == 2
        assert (gs, bf, outs, h, r, bb, so, hr) == (2, 41, 39, 10, 3, 2, 14, 1)
        assert float(ra9) == pytest.approx(3 * 27 / 39)
        assert float(whip) == pytest.approx((10 + 2) * 3 / 39)
        assert float(k9) == pytest.approx(14 * 27 / 39)
    finally:
        _cleanup(db_conn)


def test_pitching_season_zero_ip_pitcher_gets_null_rates(db_conn):
    _cleanup(db_conn)
    _seed_core(db_conn)
    # A pitcher who faced a batter but recorded no outs (all reached).
    _seed_game_lines(
        db_conn,
        [
            {
                "game_id": 7390001,
                "player_id": 73001,
                "team_id": 7301,
                "season": 2023,
                "game_date": "2023-04-01",
                **_blank(gs=0, bf=3, outs=0, h=2, r=2, bb=1),
            },
        ],
    )
    try:
        _build(db_conn)
        stint = _season(db_conn, 73001, team_id=7301)
        assert stint["outs"] == 0
        assert stint["ra9"] is None
        assert stint["whip"] is None
        assert stint["k9"] is None
        assert stint["bb9"] is None
        # k_bb divides by BB, not outs: SO 0 / BB 1 -> 0.0, not NULL
        assert float(stint["k_bb"]) == pytest.approx(0.0)
    finally:
        _cleanup(db_conn)


def test_report_health_check_includes_the_pitching_rollups(db_conn):
    _cleanup(db_conn)
    _seed_core(db_conn)
    _seed_game_lines(
        db_conn,
        [
            {
                "game_id": 7390001,
                "player_id": 73001,
                "team_id": 7301,
                "season": 2023,
                "game_date": "2023-04-01",
                **_blank(gs=1, bf=10, outs=15, h=3, r=1, so=6),
            },
            {
                "game_id": 7390003,
                "player_id": 73002,
                "team_id": 7302,
                "season": 2023,
                "game_date": "2023-04-03",
                **_blank(gs=1, bf=12, outs=18, h=4, r=2, so=5),
            },
        ],
    )
    try:
        _build(db_conn)
        checks = {c.name: c for c in report.health_check()}
        season_cov = next(c for n, c in checks.items() if "get a gold.pitching_season row" in n)
        team_cov = next(c for n, c in checks.items() if "get a gold.pitching_team row" in n)
        assert season_cov.ok, season_cov.detail
        assert team_cov.ok, team_cov.detail
    finally:
        _cleanup(db_conn)
