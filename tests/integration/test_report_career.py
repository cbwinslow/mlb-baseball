"""gold.batting_career / gold.pitching_career -- relation 5 of the
grain-complete statistic backbone (Plan 03B, ADR-278). Career roll-ups of
the season tables, verified against hand-computed totals plus idempotency.
"""

import pytest

from mlb_baseball import report


def _seed_core(db_conn):
    with db_conn.cursor() as cur:
        cur.execute(
            "INSERT INTO core.team (id, retro_team_id, league, city, nickname, "
            "first_year, last_year) VALUES "
            "(7401, 'NYA', 'AL', 'New York', 'Yankees', 1903, 2026) ON CONFLICT (id) DO NOTHING"
        )
        cur.execute(
            "INSERT INTO core.player (id, retro_id, last_name, first_name) VALUES "
            "(74001, 'ccc001', 'Long', 'Career'), "
            "(74002, 'ddd001', 'Arm', 'Old') ON CONFLICT (id) DO NOTHING"
        )
    db_conn.commit()


def _seed_batting_season(db_conn, rows):
    cols = (
        "player_id",
        "season",
        "team_id",
        "is_combined",
        "g",
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
    with db_conn.cursor() as cur:
        for row in rows:
            full = {c: 0 for c in cols}
            full.update(row)
            cur.execute(
                "INSERT INTO gold.batting_season (" + ", ".join(cols) + ") "
                "VALUES (" + ", ".join(["%s"] * len(cols)) + ")",
                tuple(full[c] for c in cols),
            )
    db_conn.commit()


def _seed_pitching_season(db_conn, rows):
    cols = (
        "player_id",
        "season",
        "team_id",
        "is_combined",
        "g",
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
    with db_conn.cursor() as cur:
        for row in rows:
            full = {c: 0 for c in cols}
            full.update(row)
            cur.execute(
                "INSERT INTO gold.pitching_season (" + ", ".join(cols) + ") "
                "VALUES (" + ", ".join(["%s"] * len(cols)) + ")",
                tuple(full[c] for c in cols),
            )
    db_conn.commit()


def _cleanup(db_conn):
    db_conn.rollback()
    with db_conn.cursor() as cur:
        for player in (74001, 74002):
            cur.execute("DELETE FROM gold.batting_career WHERE player_id = %s", (player,))
            cur.execute("DELETE FROM gold.pitching_career WHERE player_id = %s", (player,))
            cur.execute("DELETE FROM gold.batting_season WHERE player_id = %s", (player,))
            cur.execute("DELETE FROM gold.pitching_season WHERE player_id = %s", (player,))
        cur.execute("DELETE FROM core.player WHERE id IN (74001, 74002)")
        cur.execute("DELETE FROM core.team WHERE id = 7401")
    db_conn.commit()


def _build(db_conn):
    report._build_backbone_relation(
        db_conn, "gold.batting_career", report._BATTING_CAREER_SQL, source="gold.batting_season"
    )
    report._build_backbone_relation(
        db_conn, "gold.pitching_career", report._PITCHING_CAREER_SQL, source="gold.pitching_season"
    )
    db_conn.commit()


def _row(db_conn, table, player_id, cols):
    with db_conn.cursor() as cur:
        cur.execute(
            f"SELECT {', '.join(cols)} FROM gold.{table} WHERE player_id = %s", (player_id,)
        )
        r = cur.fetchone()
    return dict(zip(cols, r, strict=True)) if r else None


def test_batting_career_sums_the_per_season_combined_rows(db_conn):
    _cleanup(db_conn)
    _seed_core(db_conn)
    # Only the is_combined rows should be summed. The stint row for 2021 is
    # decoy data that must NOT be double-counted.
    _seed_batting_season(
        db_conn,
        [
            # 2021 combined: PA600 AB540 H150 (2B30 3B2 HR20) TB244 BB50 SO110 G150
            {
                "player_id": 74001,
                "season": 2021,
                "team_id": None,
                "is_combined": True,
                "g": 150,
                "pa": 600,
                "ab": 540,
                "r": 90,
                "h": 150,
                "b2": 30,
                "b3": 2,
                "hr": 20,
                "tb": 244,
                "rbi": 80,
                "bb": 50,
                "so": 110,
                "b1": 150 - 30 - 2 - 20,
            },
            # 2021 stint (decoy -- half the combined, same player/season, must be ignored)
            {
                "player_id": 74001,
                "season": 2021,
                "team_id": 7401,
                "is_combined": False,
                "g": 75,
                "pa": 300,
                "ab": 270,
                "h": 75,
                "b1": 49,
                "b2": 15,
                "b3": 1,
                "hr": 10,
                "tb": 122,
                "bb": 25,
                "so": 55,
            },
            # 2022 combined: PA550 AB500 H140 (2B25 HR15) TB210 BB40 SO100 G140
            {
                "player_id": 74001,
                "season": 2022,
                "team_id": None,
                "is_combined": True,
                "g": 140,
                "pa": 550,
                "ab": 500,
                "r": 80,
                "h": 140,
                "b2": 25,
                "hr": 15,
                "tb": 210,
                "rbi": 70,
                "bb": 40,
                "so": 100,
                "b1": 140 - 25 - 15,
            },
        ],
    )
    try:
        _build(db_conn)
        cols = [
            "seasons",
            "first_season",
            "last_season",
            "g",
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
            "avg",
            "obp",
            "slg",
        ]
        c = _row(db_conn, "batting_career", 74001, cols)
        assert c is not None
        assert c["seasons"] == 2
        assert c["first_season"] == 2021
        assert c["last_season"] == 2022
        assert c["g"] == 290
        # career totals: PA1150 AB1040 R170 H290 2B55 3B2 HR35 TB454 BB90 SO210
        assert c["pa"] == 1150
        assert c["ab"] == 1040
        assert c["r"] == 170
        assert c["h"] == 290
        assert c["b2"] == 55
        assert c["b3"] == 2
        assert c["hr"] == 35
        assert c["tb"] == 454
        assert c["bb"] == 90
        assert c["so"] == 210
        # career AVG 290/1040, OBP (290+90)/(1040+90), SLG 454/1040
        assert float(c["avg"]) == pytest.approx(290 / 1040)
        assert float(c["obp"]) == pytest.approx((290 + 90) / (1040 + 90))
        assert float(c["slg"]) == pytest.approx(454 / 1040)
    finally:
        _cleanup(db_conn)


def test_pitching_career_sums_combined_rows_and_recomputes_rates(db_conn):
    _cleanup(db_conn)
    _seed_core(db_conn)
    _seed_pitching_season(
        db_conn,
        [
            {
                "player_id": 74002,
                "season": 2020,
                "team_id": None,
                "is_combined": True,
                "g": 30,
                "gs": 30,
                "bf": 800,
                "outs": 540,
                "h": 180,
                "r": 80,
                "bb": 50,
                "so": 200,
                "hr": 25,
                "w": 12,
                "l": 8,
            },
            {
                "player_id": 74002,
                "season": 2020,
                "team_id": 7401,
                "is_combined": False,
                "g": 15,
                "gs": 15,
                "bf": 400,
                "outs": 270,
                "h": 90,
                "r": 40,
                "bb": 25,
                "so": 100,
                "hr": 12,
            },
            {
                "player_id": 74002,
                "season": 2021,
                "team_id": None,
                "is_combined": True,
                "g": 28,
                "gs": 28,
                "bf": 720,
                "outs": 486,
                "h": 160,
                "r": 70,
                "bb": 45,
                "so": 190,
                "hr": 20,
                "w": 10,
                "l": 9,
            },
        ],
    )
    try:
        _build(db_conn)
        cols = [
            "seasons",
            "first_season",
            "last_season",
            "g",
            "gs",
            "bf",
            "outs",
            "h",
            "r",
            "bb",
            "so",
            "hr",
            "w",
            "l",
            "ra9",
            "whip",
            "k9",
            "k_bb",
        ]
        c = _row(db_conn, "pitching_career", 74002, cols)
        assert c["seasons"] == 2
        assert (c["first_season"], c["last_season"]) == (2020, 2021)
        # totals: G58 GS58 BF1520 outs1026 H340 R150 BB95 SO390 HR45 W22 L17
        assert (c["g"], c["gs"], c["bf"], c["outs"]) == (58, 58, 1520, 1026)
        assert (c["h"], c["r"], c["bb"], c["so"], c["hr"]) == (340, 150, 95, 390, 45)
        assert (c["w"], c["l"]) == (22, 17)
        assert float(c["ra9"]) == pytest.approx(150 * 27 / 1026)
        assert float(c["whip"]) == pytest.approx((340 + 95) * 3 / 1026)
        assert float(c["k9"]) == pytest.approx(390 * 27 / 1026)
        assert float(c["k_bb"]) == pytest.approx(390 / 95)
    finally:
        _cleanup(db_conn)


def test_career_rebuild_is_idempotent(db_conn):
    _cleanup(db_conn)
    _seed_core(db_conn)
    _seed_batting_season(
        db_conn,
        [
            {
                "player_id": 74001,
                "season": 2021,
                "team_id": None,
                "is_combined": True,
                "g": 10,
                "pa": 40,
                "ab": 36,
                "h": 12,
                "b1": 12,
                "tb": 12,
            },
        ],
    )
    try:
        _build(db_conn)
        first = _row(db_conn, "batting_career", 74001, ["g", "pa", "ab", "h", "avg"])
        _build(db_conn)
        assert _row(db_conn, "batting_career", 74001, ["g", "pa", "ab", "h", "avg"]) == first
        with db_conn.cursor() as cur:
            cur.execute("SELECT count(*) FROM gold.batting_career WHERE player_id = 74001")
            assert cur.fetchone()[0] == 1
    finally:
        _cleanup(db_conn)


def test_report_health_check_includes_the_career_rollups(db_conn):
    _cleanup(db_conn)
    _seed_core(db_conn)
    _seed_batting_season(
        db_conn,
        [
            {
                "player_id": 74001,
                "season": 2021,
                "team_id": None,
                "is_combined": True,
                "g": 10,
                "pa": 40,
                "ab": 36,
                "h": 12,
                "b1": 12,
                "tb": 12,
            },
        ],
    )
    _seed_pitching_season(
        db_conn,
        [
            {
                "player_id": 74002,
                "season": 2021,
                "team_id": None,
                "is_combined": True,
                "g": 5,
                "gs": 5,
                "bf": 100,
                "outs": 90,
                "h": 20,
                "r": 8,
                "so": 25,
            },
        ],
    )
    try:
        _build(db_conn)
        checks = {c.name: c for c in report.health_check()}
        b = next(c for n, c in checks.items() if "gets a gold.batting_career row" in n)
        p = next(c for n, c in checks.items() if "gets a gold.pitching_career row" in n)
        assert b.ok, b.detail
        assert p.ok, p.detail
    finally:
        _cleanup(db_conn)
