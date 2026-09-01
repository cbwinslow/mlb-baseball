"""gold.pitching_game — second relation of the grain-complete statistic
backbone (Plan 03B, ADR-278). Verifies the pitching box line built from
raw.retrosheet_event against hand-computed totals, including per-runner run
attribution, plus idempotency.
"""

from mlb_baseball import report

_COLS = (
    "resp_pit_id",
    "resp_pit_start_fl",
    "event_cd",
    "bat_event_fl",
    "event_outs_ct",
    "wp_fl",
    "bat_dest_id",
    "run1_dest_id",
    "run1_resp_pit_id",
)


def _seed(db_conn):
    """One regular-season game: a starter (Cole) who allows a 2-run HR and a
    reliever (Chapman) who records one out. bat_home_id '0' -> away team is
    batting, so the pitchers are on the home team (7101)."""
    with db_conn.cursor() as cur:
        cur.execute("DROP TABLE IF EXISTS raw.retrosheet_event")
        cur.execute("DROP TABLE IF EXISTS raw.retrosheet_gameinfo")
        cur.execute(
            "CREATE TABLE raw.retrosheet_event ("
            "game_id text, bat_id text, bat_home_id text, resp_pit_id text, "
            "resp_pit_start_fl text, "
            "event_cd text, bat_event_fl text, event_outs_ct text, wp_fl text, "
            "bat_dest_id text, run1_dest_id text, run2_dest_id text, run3_dest_id text, "
            "run1_resp_pit_id text, run2_resp_pit_id text, run3_resp_pit_id text)"
        )
        cur.execute("CREATE TABLE raw.retrosheet_gameinfo (gid text, gametype text)")
        cur.execute("INSERT INTO raw.retrosheet_gameinfo VALUES ('PG202406020', 'regular')")

        cur.execute(
            "INSERT INTO core.team "
            "(id, retro_team_id, league, city, nickname, first_year, last_year) "
            "VALUES (7101, 'NYA', 'AL', 'New York', 'Yankees', 1903, 2026), "
            "(7102, 'BOS', 'AL', 'Boston', 'Red Sox', 1901, 2026) ON CONFLICT (id) DO NOTHING"
        )
        cur.execute(
            "INSERT INTO core.player (id, retro_id, last_name, first_name) VALUES "
            "(70004, 'colg001', 'Cole', 'Gerrit'), "
            "(70005, 'chap001', 'Chapman', 'Aroldis') ON CONFLICT (id) DO NOTHING"
        )
        cur.execute(
            "INSERT INTO core.game (id, retro_game_id, season, game_date, game_number, "
            "home_team_id, away_team_id, game_type, winning_pitcher_id) "
            "VALUES (7800002, 'PG202406020', 2024, '2024-06-02', 0, 7101, 7102, 'regular', 70004) "
            "ON CONFLICT (id) DO NOTHING"
        )

        blank = {c: "" for c in _COLS}
        events = [
            # Cole: K, single, 2-run HR (own dest 6 + run1 from the single scores,
            # both charged to Cole), walk, groundout, then a wild pitch.
            {
                **blank,
                "resp_pit_id": "colg001",
                "resp_pit_start_fl": "T",
                "event_cd": "3",
                "bat_event_fl": "T",
                "event_outs_ct": "1",
            },
            {
                **blank,
                "resp_pit_id": "colg001",
                "resp_pit_start_fl": "T",
                "event_cd": "20",
                "bat_event_fl": "T",
                "event_outs_ct": "0",
            },
            {
                **blank,
                "resp_pit_id": "colg001",
                "resp_pit_start_fl": "T",
                "event_cd": "23",
                "bat_event_fl": "T",
                "event_outs_ct": "0",
                "bat_dest_id": "6",
                "run1_dest_id": "4",
                "run1_resp_pit_id": "colg001",
            },
            {
                **blank,
                "resp_pit_id": "colg001",
                "resp_pit_start_fl": "T",
                "event_cd": "14",
                "bat_event_fl": "T",
                "event_outs_ct": "0",
            },
            {
                **blank,
                "resp_pit_id": "colg001",
                "resp_pit_start_fl": "T",
                "event_cd": "2",
                "bat_event_fl": "T",
                "event_outs_ct": "1",
            },
            {
                **blank,
                "resp_pit_id": "colg001",
                "resp_pit_start_fl": "T",
                "event_cd": "9",
                "bat_event_fl": "F",
                "event_outs_ct": "0",
                "wp_fl": "T",
            },
            {  # Cole: hit batter, then a balk (leaves a runner on 1st for Cole).
                **blank,
                "resp_pit_id": "colg001",
                "resp_pit_start_fl": "T",
                "event_cd": "16",
                "bat_event_fl": "T",
                "event_outs_ct": "0",
            },
            {
                **blank,
                "resp_pit_id": "colg001",
                "resp_pit_start_fl": "T",
                "event_cd": "11",
                "bat_event_fl": "F",
                "event_outs_ct": "0",
            },
            # Chapman comes in. A single (charged to Chapman) scores the runner
            # Cole left on first -> the run is charged to COLE, not Chapman.
            {
                **blank,
                "resp_pit_id": "chap001",
                "resp_pit_start_fl": "F",
                "event_cd": "20",
                "bat_event_fl": "T",
                "event_outs_ct": "0",
                "run1_dest_id": "4",
                "run1_resp_pit_id": "colg001",
            },
            {
                **blank,
                "resp_pit_id": "chap001",
                "resp_pit_start_fl": "F",
                "event_cd": "3",
                "bat_event_fl": "T",
                "event_outs_ct": "1",
            },
        ]
        for e in events:
            cur.execute(
                "INSERT INTO raw.retrosheet_event (game_id, bat_home_id, "
                + ", ".join(_COLS)
                + ") VALUES ('PG202406020', '0', "
                + ", ".join(["%s"] * len(_COLS))
                + ")",
                tuple(e[c] for c in _COLS),
            )
    db_conn.commit()


def _cleanup(db_conn):
    db_conn.rollback()
    with db_conn.cursor() as cur:
        cur.execute("DELETE FROM gold.pitching_game WHERE game_id = 7800002")
        cur.execute("DELETE FROM core.game WHERE id = 7800002")
        cur.execute("DELETE FROM core.player WHERE id IN (70004, 70005)")
        cur.execute("DELETE FROM core.team WHERE id IN (7101, 7102)")
        cur.execute("DROP TABLE IF EXISTS raw.retrosheet_event")
        cur.execute("DROP TABLE IF EXISTS raw.retrosheet_gameinfo")
    db_conn.commit()


def _line(db_conn, player_id):
    with db_conn.cursor() as cur:
        cur.execute(
            "SELECT gs, bf, outs, h, r, bb, ibb, so, hr, hbp, wp, bk, w, l, sv, team_id "
            "FROM gold.pitching_game WHERE game_id = 7800002 AND player_id = %s",
            (player_id,),
        )
        row = cur.fetchone()
    keys = [
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
        "team_id",
    ]
    return dict(zip(keys, row, strict=True)) if row else None


def _build(db_conn):
    report._build_backbone_relation(db_conn, "gold.pitching_game", report._PITCHING_GAME_SQL)
    db_conn.commit()


def test_pitching_game_box_lines_match_hand_math(db_conn):
    _cleanup(db_conn)
    _seed(db_conn)
    try:
        _build(db_conn)
        cole = _line(db_conn, 70004)
        assert cole == {
            "gs": 1,
            "bf": 6,
            "outs": 2,
            "h": 2,
            # 3 runs: his own HR, the runner scoring on the HR, and -- the key
            # inherited-runner case -- the runner he left on first who scored on
            # Chapman's single (run1_resp_pit_id charges Cole, not Chapman).
            "r": 3,
            "bb": 1,
            "ibb": 0,
            "so": 1,
            "hr": 1,
            "hbp": 1,
            "wp": 1,
            "bk": 1,
            "w": 1,
            "l": 0,
            "sv": 0,
            "team_id": 7101,
        }
        chapman = _line(db_conn, 70005)
        assert chapman == {
            "gs": 0,
            "bf": 2,
            "outs": 1,
            "h": 1,
            "r": 0,  # the run that scored while he pitched is Cole's inherited runner
            "bb": 0,
            "ibb": 0,
            "so": 1,
            "hr": 0,
            "hbp": 0,
            "wp": 0,
            "bk": 0,
            "w": 0,
            "l": 0,
            "sv": 0,
            "team_id": 7101,
        }
    finally:
        _cleanup(db_conn)


def test_pitching_game_rebuild_is_idempotent(db_conn):
    _cleanup(db_conn)
    _seed(db_conn)
    try:
        _build(db_conn)
        first = _line(db_conn, 70004)
        _build(db_conn)
        assert _line(db_conn, 70004) == first
        with db_conn.cursor() as cur:
            cur.execute("SELECT count(*) FROM gold.pitching_game WHERE game_id = 7800002")
            assert cur.fetchone()[0] == 2
    finally:
        _cleanup(db_conn)


def test_pitching_game_skips_postseason_games(db_conn):
    _cleanup(db_conn)
    _seed(db_conn)
    with db_conn.cursor() as cur:
        cur.execute("UPDATE core.game SET game_type = 'divisionseries' WHERE id = 7800002")
    db_conn.commit()
    try:
        _build(db_conn)
        with db_conn.cursor() as cur:
            cur.execute("SELECT count(*) FROM gold.pitching_game WHERE game_id = 7800002")
            assert cur.fetchone()[0] == 0
    finally:
        _cleanup(db_conn)


def test_pitching_game_degrades_without_retrosheet_event(db_conn):
    _cleanup(db_conn)
    with db_conn.cursor() as cur:
        cur.execute("DROP TABLE IF EXISTS raw.retrosheet_event")
    db_conn.commit()
    assert (
        report._build_backbone_relation(db_conn, "gold.pitching_game", report._PITCHING_GAME_SQL)
        == 0
    )
    with db_conn.cursor() as cur:
        cur.execute("SELECT 1")
        assert cur.fetchone() == (1,)


def test_report_health_check_includes_pitching_game(db_conn):
    _cleanup(db_conn)
    _seed(db_conn)
    try:
        _build(db_conn)
        checks = {c.name: c for c in report.health_check()}
        assert any("gold.pitching_game" in n for n in checks)
        coverage = next(c for n, c in checks.items() if "get a gold.pitching_game row" in n)
        assert coverage.ok, coverage.detail
    finally:
        _cleanup(db_conn)
