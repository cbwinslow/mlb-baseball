"""gold.pitching_game from raw.mlb_boxscore_pitching -- the 2026-onward
game-grain builder (backbone-2026-source). Verifies the box-score line against
hand-computed totals, the new `er` column (populated for 2026, NULL for the
1910-2025 Retrosheet era), the source marker, and idempotency.
"""

from mlb_baseball import report

_BOX_COLS = (
    "game_pk",
    "team_id",
    "person_id",
    "games_started",
    "batters_faced",
    "outs",
    "hits",
    "runs",
    "earned_runs",
    "base_on_balls",
    "intentional_walks",
    "strike_outs",
    "home_runs",
    "hit_batsmen",
    "wild_pitches",
    "balks",
    "wins",
    "losses",
    "saves",
)


def _cleanup(db_conn):
    db_conn.rollback()
    with db_conn.cursor() as cur:
        cur.execute("DELETE FROM gold.pitching_game WHERE game_id IN (7860001, 7860002)")
        cur.execute("DELETE FROM core.game WHERE id IN (7860001, 7860002)")
        cur.execute("DELETE FROM core.player WHERE id IN (76003, 76004, 76005)")
        cur.execute("DELETE FROM core.team WHERE id IN (7603, 7604)")
        cur.execute("DROP TABLE IF EXISTS raw.mlb_boxscore_pitching")
    db_conn.commit()


def _seed(db_conn):
    with db_conn.cursor() as cur:
        cur.execute("DROP TABLE IF EXISTS raw.mlb_boxscore_pitching")
        cur.execute(
            "CREATE TABLE raw.mlb_boxscore_pitching ("
            + ", ".join(f"{c} text" for c in _BOX_COLS)
            + ")"
        )
        cur.execute(
            "INSERT INTO core.team (id, retro_team_id, league, city, nickname, "
            "first_year, last_year, mlb_team_id) VALUES "
            "(7603, 'NYA', 'AL', 'New York', 'Yankees', 1903, 2026, 147), "
            "(7604, 'BOS', 'AL', 'Boston', 'Red Sox', 1901, 2026, 111) "
            "ON CONFLICT (id) DO NOTHING"
        )
        cur.execute(
            "INSERT INTO core.player (id, mlbam_id, retro_id, last_name, first_name) VALUES "
            "(76003, '700003', 'strp001', 'Starter', 'Sam'), "
            "(76004, '700004', 'relr001', 'Reliever', 'Rae'), "
            "(76005, '700005', 'pick001', 'Pickoff', 'Pip') ON CONFLICT (id) DO NOTHING"
        )
        cur.execute(
            "INSERT INTO core.game (id, game_pk, season, game_date, game_number, "
            "home_team_id, away_team_id, game_type, winning_pitcher_id) VALUES "
            "(7860001, '2026101', 2026, '2026-04-06', 0, 7603, 7604, 'regular', 76003), "
            "(7860002, 'RS2025x', 2025, '2025-06-01', 0, 7603, 7604, 'regular', NULL) "
            "ON CONFLICT (id) DO NOTHING"
        )
        # Sam (start): BF20 outs15 H4 R3 ER2 BB2 SO6 HR1 HBP1 W1.
        # Rae (relief): BF6 outs6 H1 R0 ER0 BB1 SO3 WP1 SV1.
        rows = [
            {
                "game_pk": "2026101",
                "team_id": "147",
                "person_id": "700003",
                "games_started": "1",
                "batters_faced": "20",
                "outs": "15",
                "hits": "4",
                "runs": "3",
                "earned_runs": "2",
                "base_on_balls": "2",
                "intentional_walks": "0",
                "strike_outs": "6",
                "home_runs": "1",
                "hit_batsmen": "1",
                "wild_pitches": "0",
                "balks": "0",
                "wins": "1",
                "losses": "0",
                "saves": "0",
            },
            {
                "game_pk": "2026101",
                "team_id": "147",
                "person_id": "700004",
                "games_started": "0",
                "batters_faced": "6",
                "outs": "6",
                "hits": "1",
                "runs": "0",
                "earned_runs": "0",
                "base_on_balls": "1",
                "intentional_walks": "0",
                "strike_outs": "3",
                "home_runs": "0",
                "hit_batsmen": "0",
                "wild_pitches": "1",
                "balks": "0",
                "wins": "0",
                "losses": "0",
                "saves": "1",
            },
            # position player emergency "pitcher" -- all zeros, faced nobody.
            {
                "game_pk": "2026101",
                "team_id": "147",
                "person_id": "700004",
                "games_started": "0",
                "batters_faced": "0",
                "outs": "0",
                "hits": "0",
                "runs": "0",
                "earned_runs": "0",
                "base_on_balls": "0",
                "intentional_walks": "0",
                "strike_outs": "0",
                "home_runs": "0",
                "hit_batsmen": "0",
                "wild_pitches": "0",
                "balks": "0",
                "wins": "0",
                "losses": "0",
                "saves": "0",
            },
            # Pip: entered, picked off / caught the runner, was pulled --
            # a real MLB line with outs > 0 and batters_faced = 0. Must NOT
            # be dropped (the builder keeps a line with any recorded activity).
            {
                "game_pk": "2026101",
                "team_id": "147",
                "person_id": "700005",
                "games_started": "0",
                "batters_faced": "0",
                "outs": "1",
                "hits": "0",
                "runs": "0",
                "earned_runs": "0",
                "base_on_balls": "0",
                "intentional_walks": "0",
                "strike_outs": "0",
                "home_runs": "0",
                "hit_batsmen": "0",
                "wild_pitches": "0",
                "balks": "0",
                "wins": "0",
                "losses": "0",
                "saves": "0",
            },
        ]
        for r in rows:
            cur.execute(
                "INSERT INTO raw.mlb_boxscore_pitching (" + ", ".join(_BOX_COLS) + ") "
                "VALUES (" + ", ".join(["%s"] * len(_BOX_COLS)) + ")",
                tuple(r[c] for c in _BOX_COLS),
            )
        # A 1910-2025 Retrosheet-era game line, written directly (as the
        # Retrosheet builder would -- no `er`): must keep er NULL.
        cur.execute(
            "INSERT INTO gold.pitching_game (game_id, player_id, team_id, season, "
            "game_date, gs, bf, outs, h, r, so, source) VALUES "
            "(7860002, 76003, 7603, 2025, '2025-06-01', 1, 24, 18, 6, 3, 7, 'retrosheet_event')"
        )
    db_conn.commit()


def _build(db_conn):
    report._build_backbone_relation_multi(
        db_conn,
        "gold.pitching_game",
        [(report._PITCHING_GAME_MLB_SQL, "raw.mlb_boxscore_pitching")],
    )
    db_conn.commit()


def _line(db_conn, game_id, player_id):
    with db_conn.cursor() as cur:
        cur.execute(
            "SELECT gs, bf, outs, h, r, er, bb, ibb, so, hr, hbp, wp, bk, w, l, sv, "
            "team_id, source FROM gold.pitching_game "
            "WHERE game_id = %s AND player_id = %s",
            (game_id, player_id),
        )
        row = cur.fetchone()
    keys = [
        "gs",
        "bf",
        "outs",
        "h",
        "r",
        "er",
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
        "team_id",
        "source",
    ]
    return dict(zip(keys, row, strict=True)) if row else None


def test_pitching_game_mlb_box_lines_match_hand_math_and_populate_er(db_conn):
    _cleanup(db_conn)
    _seed(db_conn)
    try:
        _build(db_conn)
        sam = _line(db_conn, 7860001, 76003)
        assert sam == {
            "gs": 1,
            "bf": 20,
            "outs": 15,
            "h": 4,
            "r": 3,
            "er": 2,
            "bb": 2,
            "ibb": 0,
            "so": 6,
            "hr": 1,
            "hbp": 1,
            "wp": 0,
            "bk": 0,
            "w": 1,
            "l": 0,
            "sv": 0,
            "team_id": 7603,
            "source": "mlb_boxscore",
        }
        rae = _line(db_conn, 7860001, 76004)
        assert rae == {
            "gs": 0,
            "bf": 6,
            "outs": 6,
            "h": 1,
            "r": 0,
            "er": 0,
            "bb": 1,
            "ibb": 0,
            "so": 3,
            "hr": 0,
            "hbp": 0,
            "wp": 1,
            "bk": 0,
            "w": 0,
            "l": 0,
            "sv": 1,
            "team_id": 7603,
            "source": "mlb_boxscore",
        }
        with db_conn.cursor() as cur:
            cur.execute("SELECT count(*) FROM gold.pitching_game WHERE game_id = 7860001")
            # Sam + Rae + Pip (pickoff, bf=0 outs=1). The all-zero bf=0 outs=0
            # position-player line is the only one dropped.
            assert cur.fetchone()[0] == 3
    finally:
        _cleanup(db_conn)


def test_pitching_game_mlb_keeps_a_line_with_outs_but_no_batters_faced(db_conn):
    # A pitcher who enters, retires a baserunner (pickoff / caught stealing)
    # and is pulled has outs > 0 and batters_faced = 0 -- a real MLB line the
    # builder must not drop.
    _cleanup(db_conn)
    _seed(db_conn)
    try:
        _build(db_conn)
        with db_conn.cursor() as cur:
            cur.execute(
                "SELECT bf, outs FROM gold.pitching_game "
                "WHERE game_id = 7860001 AND player_id = 76005"
            )
            assert cur.fetchone() == (0, 1)
    finally:
        _cleanup(db_conn)


def test_pitching_game_retrosheet_era_row_has_null_er(db_conn):
    _cleanup(db_conn)
    _seed(db_conn)
    try:
        with db_conn.cursor() as cur:
            cur.execute(
                "SELECT er FROM gold.pitching_game WHERE game_id = 7860002 AND player_id = 76003"
            )
            assert cur.fetchone() == (None,)
    finally:
        _cleanup(db_conn)


def test_pitching_game_mlb_rebuild_is_idempotent(db_conn):
    _cleanup(db_conn)
    _seed(db_conn)
    try:
        _build(db_conn)
        first = _line(db_conn, 7860001, 76003)
        _build(db_conn)
        assert _line(db_conn, 7860001, 76003) == first
        with db_conn.cursor() as cur:
            cur.execute("SELECT count(*) FROM gold.pitching_game WHERE game_id = 7860001")
            assert cur.fetchone()[0] == 3
    finally:
        _cleanup(db_conn)
