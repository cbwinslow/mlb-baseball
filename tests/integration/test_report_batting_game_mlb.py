"""gold.batting_game from raw.mlb_boxscore_batting -- the 2026-onward game-grain
builder (backbone-2026-source). Verifies the box-score line against
hand-computed totals, the source marker, and idempotency.

raw.mlb_boxscore_batting is a dynamically-created landing table in production
(mlb_baseball/load.py), not a migration, so this file creates it, matching
test_report.py's convention for raw.bref_* / raw.retrosheet_event.
"""

from mlb_baseball import report

_BOX_COLS = (
    "game_pk",
    "team_id",
    "person_id",
    "plate_appearances",
    "at_bats",
    "runs",
    "hits",
    "doubles",
    "triples",
    "home_runs",
    "total_bases",
    "rbi",
    "base_on_balls",
    "intentional_walks",
    "hit_by_pitch",
    "sac_flies",
    "sac_bunts",
    "strike_outs",
    "ground_into_double_play",
)


def _cleanup(db_conn):
    db_conn.rollback()
    with db_conn.cursor() as cur:
        cur.execute("DELETE FROM gold.batting_game WHERE game_id = 7850001")
        cur.execute("DELETE FROM core.game WHERE id = 7850001")
        cur.execute("DELETE FROM core.player WHERE id IN (76001, 76002)")
        cur.execute("DELETE FROM core.team WHERE id IN (7601, 7602)")
        cur.execute("DROP TABLE IF EXISTS raw.mlb_boxscore_batting")
    db_conn.commit()


def _seed(db_conn):
    with db_conn.cursor() as cur:
        cur.execute("DROP TABLE IF EXISTS raw.mlb_boxscore_batting")
        cur.execute(
            "CREATE TABLE raw.mlb_boxscore_batting ("
            + ", ".join(f"{c} text" for c in _BOX_COLS)
            + ")"
        )
        cur.execute(
            "INSERT INTO core.team (id, retro_team_id, league, city, nickname, "
            "first_year, last_year, mlb_team_id) VALUES "
            "(7601, 'NYA', 'AL', 'New York', 'Yankees', 1903, 2026, 147), "
            "(7602, 'BOS', 'AL', 'Boston', 'Red Sox', 1901, 2026, 111) "
            "ON CONFLICT (id) DO NOTHING"
        )
        cur.execute(
            "INSERT INTO core.player (id, mlbam_id, last_name, first_name) VALUES "
            "(76001, '700001', 'Alpha', 'Ann'), "
            "(76002, '700002', 'Beta', 'Ben') ON CONFLICT (id) DO NOTHING"
        )
        cur.execute(
            "INSERT INTO core.game (id, game_pk, retro_game_id, season, game_date, "
            "game_number, home_team_id, away_team_id, game_type) VALUES "
            "(7850001, '2026001', NULL, 2026, '2026-04-05', 0, 7601, 7602, 'regular') "
            "ON CONFLICT (id) DO NOTHING"
        )
        # Ann: PA5 AB4 R1 H2 (1 double + 1 HR -> b1 = 0), TB6, RBI3, BB1, SO1.
        #   PA 5 = AB 4 + BB 1.
        # Ben: PA4 AB3 H1 (single -> b1 = 1), TB1, RBI1, HBP1, GIDP1.
        #   PA 4 = AB 3 + HBP 1.
        rows = [
            {
                "game_pk": "2026001",
                "team_id": "147",
                "person_id": "700001",
                "plate_appearances": "5",
                "at_bats": "4",
                "runs": "1",
                "hits": "2",
                "doubles": "1",
                "triples": "0",
                "home_runs": "1",
                "total_bases": "6",
                "rbi": "3",
                "base_on_balls": "1",
                "intentional_walks": "0",
                "hit_by_pitch": "0",
                "sac_flies": "0",
                "sac_bunts": "0",
                "strike_outs": "1",
                "ground_into_double_play": "0",
            },
            {
                "game_pk": "2026001",
                "team_id": "147",
                "person_id": "700002",
                "plate_appearances": "4",
                "at_bats": "3",
                "runs": "0",
                "hits": "1",
                "doubles": "0",
                "triples": "0",
                "home_runs": "0",
                "total_bases": "1",
                "rbi": "1",
                "base_on_balls": "0",
                "intentional_walks": "0",
                "hit_by_pitch": "1",
                "sac_flies": "0",
                "sac_bunts": "0",
                "strike_outs": "0",
                "ground_into_double_play": "1",
            },
            # A defensive replacement with 0 PA -- must NOT produce a row.
            {
                "game_pk": "2026001",
                "team_id": "147",
                "person_id": "700002",
                "plate_appearances": "0",
                "at_bats": "0",
                "runs": "0",
                "hits": "0",
                "doubles": "0",
                "triples": "0",
                "home_runs": "0",
                "total_bases": "0",
                "rbi": "0",
                "base_on_balls": "0",
                "intentional_walks": "0",
                "hit_by_pitch": "0",
                "sac_flies": "0",
                "sac_bunts": "0",
                "strike_outs": "0",
                "ground_into_double_play": "0",
            },
        ]
        for r in rows:
            cur.execute(
                "INSERT INTO raw.mlb_boxscore_batting (" + ", ".join(_BOX_COLS) + ") "
                "VALUES (" + ", ".join(["%s"] * len(_BOX_COLS)) + ")",
                tuple(r[c] for c in _BOX_COLS),
            )
    db_conn.commit()


def _build(db_conn):
    report._build_backbone_relation_multi(
        db_conn,
        "gold.batting_game",
        [(report._BATTING_GAME_MLB_SQL, "raw.mlb_boxscore_batting")],
    )
    db_conn.commit()


def _line(db_conn, player_id):
    with db_conn.cursor() as cur:
        cur.execute(
            "SELECT pa, ab, r, h, b1, b2, b3, hr, tb, rbi, bb, ibb, hbp, sf, sh, so, "
            "gidp, team_id, source FROM gold.batting_game "
            "WHERE game_id = 7850001 AND player_id = %s",
            (player_id,),
        )
        row = cur.fetchone()
    keys = [
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
        "team_id",
        "source",
    ]
    return dict(zip(keys, row, strict=True)) if row else None


def test_batting_game_mlb_box_lines_match_hand_math(db_conn):
    _cleanup(db_conn)
    _seed(db_conn)
    try:
        _build(db_conn)
        ann = _line(db_conn, 76001)
        assert ann == {
            "pa": 5,
            "ab": 4,
            "r": 1,
            "h": 2,
            "b1": 0,
            "b2": 1,
            "b3": 0,
            "hr": 1,
            "tb": 6,
            "rbi": 3,
            "bb": 1,
            "ibb": 0,
            "hbp": 0,
            "sf": 0,
            "sh": 0,
            "so": 1,
            "gidp": 0,
            "team_id": 7601,
            "source": "mlb_boxscore",
        }
        ben = _line(db_conn, 76002)
        assert ben == {
            "pa": 4,
            "ab": 3,
            "r": 0,
            "h": 1,
            "b1": 1,
            "b2": 0,
            "b3": 0,
            "hr": 0,
            "tb": 1,
            "rbi": 1,
            "bb": 0,
            "ibb": 0,
            "hbp": 1,
            "sf": 0,
            "sh": 0,
            "so": 0,
            "gidp": 1,
            "team_id": 7601,
            "source": "mlb_boxscore",
        }
        with db_conn.cursor() as cur:
            cur.execute("SELECT count(*) FROM gold.batting_game WHERE game_id = 7850001")
            assert cur.fetchone()[0] == 2  # the 0-PA replacement produced no row
    finally:
        _cleanup(db_conn)


def test_batting_game_mlb_rebuild_is_idempotent(db_conn):
    _cleanup(db_conn)
    _seed(db_conn)
    try:
        _build(db_conn)
        first = _line(db_conn, 76001)
        _build(db_conn)
        assert _line(db_conn, 76001) == first
        with db_conn.cursor() as cur:
            cur.execute("SELECT count(*) FROM gold.batting_game WHERE game_id = 7850001")
            assert cur.fetchone()[0] == 2
    finally:
        _cleanup(db_conn)


def test_batting_game_mlb_skips_pre_2026_and_non_regular(db_conn):
    _cleanup(db_conn)
    _seed(db_conn)
    try:
        with db_conn.cursor() as cur:
            cur.execute("UPDATE core.game SET season = 2025 WHERE id = 7850001")
        db_conn.commit()
        _build(db_conn)
        with db_conn.cursor() as cur:
            cur.execute("SELECT count(*) FROM gold.batting_game WHERE game_id = 7850001")
            assert cur.fetchone()[0] == 0

        with db_conn.cursor() as cur:
            cur.execute(
                "UPDATE core.game SET season = 2026, game_type = 'spring' WHERE id = 7850001"
            )
        db_conn.commit()
        _build(db_conn)
        with db_conn.cursor() as cur:
            cur.execute("SELECT count(*) FROM gold.batting_game WHERE game_id = 7850001")
            assert cur.fetchone()[0] == 0
    finally:
        _cleanup(db_conn)


def test_report_health_check_covers_the_mlb_boxscore_rows(db_conn):
    _cleanup(db_conn)
    _seed(db_conn)
    try:
        _build(db_conn)
        checks = {c.name: c for c in report.health_check()}
        cov = next(
            c for n, c in checks.items() if "mlb_boxscore-sourced gold.batting_game row" in n
        )
        assert cov.ok, cov.detail
        guard = next(c for n, c in checks.items() if "written by both builders" in n)
        assert guard.ok, guard.detail
    finally:
        _cleanup(db_conn)


def test_batting_game_mlb_degrades_without_the_box_score_table(db_conn):
    _cleanup(db_conn)  # no raw.mlb_boxscore_batting
    assert (
        report._build_backbone_relation_multi(
            db_conn,
            "gold.batting_game",
            [(report._BATTING_GAME_MLB_SQL, "raw.mlb_boxscore_batting")],
        )
        == 0
    )
    with db_conn.cursor() as cur:
        cur.execute("SELECT 1")
        assert cur.fetchone() == (1,)
