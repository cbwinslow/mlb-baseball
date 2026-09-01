"""gold.batting_game — the first relation of the grain-complete statistic
backbone (Plan 03B). Verifies the box-score line built from
raw.retrosheet_event against hand-computed totals, plus idempotency.
"""

from mlb_baseball import report


def _seed(db_conn):
    """One regular-season game with three batters whose box lines are
    hand-verifiable, plus one baserunning event so the run-scoring path is
    exercised."""
    with db_conn.cursor() as cur:
        cur.execute("DROP TABLE IF EXISTS raw.retrosheet_event")
        cur.execute("DROP TABLE IF EXISTS raw.retrosheet_gameinfo")
        cur.execute(
            "CREATE TABLE raw.retrosheet_event ("
            "game_id text, bat_id text, resp_pit_id text, bat_home_id text, event_cd text, "
            "bat_event_fl text, ab_fl text, sf_fl text, sh_fl text, dp_fl text, "
            "battedball_cd text, rbi_ct text, bat_dest_id text, "
            "run1_dest_id text, run2_dest_id text, run3_dest_id text, "
            "base1_run_id text, base2_run_id text, base3_run_id text)"
        )
        cur.execute("CREATE TABLE raw.retrosheet_gameinfo (gid text, gametype text)")
        cur.execute("INSERT INTO raw.retrosheet_gameinfo VALUES ('BG202406010', 'regular')")

        cur.execute(
            "INSERT INTO core.team "
            "(id, retro_team_id, league, city, nickname, first_year, last_year) "
            "VALUES (7101, 'NYA', 'AL', 'New York', 'Yankees', 1903, 2026), "
            "(7102, 'BOS', 'AL', 'Boston', 'Red Sox', 1901, 2026) ON CONFLICT (id) DO NOTHING"
        )
        cur.execute(
            "INSERT INTO core.player (id, retro_id, last_name, first_name) VALUES "
            "(70001, 'judg001', 'Judge', 'Aaron'), "
            "(70002, 'stan001', 'Stanton', 'Giancarlo'), "
            "(70003, 'volp001', 'Volpe', 'Anthony') ON CONFLICT (id) DO NOTHING"
        )
        cur.execute(
            "INSERT INTO core.game (id, retro_game_id, season, game_date, game_number, "
            "home_team_id, away_team_id, game_type) "
            "VALUES (7800001, 'BG202406010', 2024, '2024-06-01', 0, 7101, 7102, 'regular') "
            "ON CONFLICT (id) DO NOTHING"
        )

        # One dict per event. Blank string = not applicable, matching cwevent
        # output. bat_home_id '1' -> all three batters are Yankees (team 7101).
        _cols = (
            "bat_id",
            "event_cd",
            "bat_event_fl",
            "ab_fl",
            "sf_fl",
            "sh_fl",
            "dp_fl",
            "battedball_cd",
            "rbi_ct",
            "bat_dest_id",
            "run1_dest_id",
            "base1_run_id",
        )
        _blank = {c: "" for c in _cols}
        events = [
            # judge: HR (1 RBI, scores self), 1B, BB, K, sac fly (1 RBI)
            {
                **_blank,
                "bat_id": "judg001",
                "event_cd": "23",
                "bat_event_fl": "T",
                "ab_fl": "T",
                "rbi_ct": "1",
                "bat_dest_id": "6",
            },
            {
                **_blank,
                "bat_id": "judg001",
                "event_cd": "20",
                "bat_event_fl": "T",
                "ab_fl": "T",
                "bat_dest_id": "1",
            },
            {
                **_blank,
                "bat_id": "judg001",
                "event_cd": "14",
                "bat_event_fl": "T",
                "ab_fl": "F",
                "bat_dest_id": "1",
            },
            {
                **_blank,
                "bat_id": "judg001",
                "event_cd": "3",
                "bat_event_fl": "T",
                "ab_fl": "T",
                "bat_dest_id": "0",
            },
            {
                **_blank,
                "bat_id": "judg001",
                "event_cd": "2",
                "bat_event_fl": "T",
                "ab_fl": "F",
                "sf_fl": "T",
                "rbi_ct": "1",
                "bat_dest_id": "0",
            },
            # stanton: grounded into DP (out), then a double
            {
                **_blank,
                "bat_id": "stan001",
                "event_cd": "2",
                "bat_event_fl": "T",
                "ab_fl": "T",
                "dp_fl": "T",
                "battedball_cd": "G",
                "bat_dest_id": "0",
            },
            {
                **_blank,
                "bat_id": "stan001",
                "event_cd": "21",
                "bat_event_fl": "T",
                "ab_fl": "T",
                "bat_dest_id": "2",
            },
            # volpe: single that scores judge from first (judge's 2nd run)
            {
                **_blank,
                "bat_id": "volp001",
                "event_cd": "20",
                "bat_event_fl": "T",
                "ab_fl": "T",
                "bat_dest_id": "1",
                "run1_dest_id": "4",
                "base1_run_id": "judg001",
            },
        ]
        for e in events:
            cur.execute(
                "INSERT INTO raw.retrosheet_event "
                "(game_id, bat_home_id, " + ", ".join(_cols) + ") "
                "VALUES ('BG202406010', '1', " + ", ".join(["%s"] * len(_cols)) + ")",
                tuple(e[c] for c in _cols),
            )
    db_conn.commit()


def _cleanup(db_conn):
    db_conn.rollback()
    with db_conn.cursor() as cur:
        cur.execute("DELETE FROM gold.batting_game WHERE game_id = 7800001")
        cur.execute("DELETE FROM core.game WHERE id = 7800001")
        cur.execute("DELETE FROM core.player WHERE id IN (70001, 70002, 70003)")
        cur.execute("DELETE FROM core.team WHERE id IN (7101, 7102)")
        cur.execute("DROP TABLE IF EXISTS raw.retrosheet_event")
        cur.execute("DROP TABLE IF EXISTS raw.retrosheet_gameinfo")
    db_conn.commit()


def _line(db_conn, player_id):
    with db_conn.cursor() as cur:
        cur.execute(
            "SELECT pa, ab, r, h, b1, b2, b3, hr, tb, rbi, bb, ibb, hbp, sf, sh, so, gidp, team_id "
            "FROM gold.batting_game WHERE game_id = 7800001 AND player_id = %s",
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
    ]
    return dict(zip(keys, row, strict=True)) if row else None


def test_batting_game_box_lines_match_hand_math(db_conn):
    _cleanup(db_conn)
    _seed(db_conn)
    try:
        report._build_backbone_relation(db_conn, "gold.batting_game", report._BATTING_GAME_SQL)
        db_conn.commit()

        judge = _line(db_conn, 70001)
        assert judge == {
            "pa": 5,
            "ab": 3,
            "r": 2,
            "h": 2,
            "b1": 1,
            "b2": 0,
            "b3": 0,
            "hr": 1,
            "tb": 5,
            "rbi": 2,
            "bb": 1,
            "ibb": 0,
            "hbp": 0,
            "sf": 1,
            "sh": 0,
            "so": 1,
            "gidp": 0,
            "team_id": 7101,
        }
        stanton = _line(db_conn, 70002)
        assert stanton == {
            "pa": 2,
            "ab": 2,
            "r": 0,
            "h": 1,
            "b1": 0,
            "b2": 1,
            "b3": 0,
            "hr": 0,
            "tb": 2,
            "rbi": 0,
            "bb": 0,
            "ibb": 0,
            "hbp": 0,
            "sf": 0,
            "sh": 0,
            "so": 0,
            "gidp": 1,
            "team_id": 7101,
        }
        volpe = _line(db_conn, 70003)
        assert volpe["pa"] == 1 and volpe["h"] == 1 and volpe["b1"] == 1 and volpe["tb"] == 1
    finally:
        _cleanup(db_conn)


def test_batting_game_rebuild_is_idempotent(db_conn):
    _cleanup(db_conn)
    _seed(db_conn)
    try:
        report._build_backbone_relation(db_conn, "gold.batting_game", report._BATTING_GAME_SQL)
        db_conn.commit()
        first = _line(db_conn, 70001)
        report._build_backbone_relation(db_conn, "gold.batting_game", report._BATTING_GAME_SQL)
        db_conn.commit()
        assert _line(db_conn, 70001) == first
        with db_conn.cursor() as cur:
            cur.execute("SELECT count(*) FROM gold.batting_game WHERE game_id = 7800001")
            assert cur.fetchone()[0] == 3
    finally:
        _cleanup(db_conn)


def test_batting_game_skips_postseason_games(db_conn):
    _cleanup(db_conn)
    _seed(db_conn)
    with db_conn.cursor() as cur:
        cur.execute("UPDATE core.game SET game_type = 'wildcard' WHERE id = 7800001")
    db_conn.commit()
    try:
        report._build_backbone_relation(db_conn, "gold.batting_game", report._BATTING_GAME_SQL)
        db_conn.commit()
        with db_conn.cursor() as cur:
            cur.execute("SELECT count(*) FROM gold.batting_game WHERE game_id = 7800001")
            assert cur.fetchone()[0] == 0
    finally:
        _cleanup(db_conn)


def test_build_batting_game_degrades_without_retrosheet_event(db_conn):
    _cleanup(db_conn)  # no raw.retrosheet_event
    with db_conn.cursor() as cur:
        cur.execute("DROP TABLE IF EXISTS raw.retrosheet_event")
    db_conn.commit()
    assert (
        report._build_backbone_relation(db_conn, "gold.batting_game", report._BATTING_GAME_SQL) == 0
    )
    # connection still usable
    with db_conn.cursor() as cur:
        cur.execute("SELECT 1")
        assert cur.fetchone() == (1,)


def test_report_health_check_includes_batting_game(db_conn):
    _cleanup(db_conn)
    _seed(db_conn)
    try:
        report._build_backbone_relation(db_conn, "gold.batting_game", report._BATTING_GAME_SQL)
        db_conn.commit()
        names = [c.name for c in report.health_check()]
        assert any("gold.batting_game" in n for n in names)
        assert any("get a gold.batting_game row" in n for n in names)
        coverage = next(c for c in report.health_check() if "get a gold.batting_game row" in c.name)
        assert coverage.ok, coverage.detail
    finally:
        _cleanup(db_conn)
