"""Real-PostgreSQL contract tests for the first strict MLB game feature family."""

# ruff: noqa: E501

import pytest

from mlb_baseball.model import features


def _reset(db_conn):
    # raw.mlb_schedule is DROPped, not DELETEd (issue #9 item 5): this
    # table is never created by a migration, only ad-hoc by whichever
    # test_model_*.py file's tests run first in a given pytest session.
    # _seed() below already recreates it with the correct schema from
    # scratch when it's missing, so a DROP here is safe and prevents a
    # stale, narrower schema from an earlier test/file lingering for the
    # rest of the run.
    db_conn.rollback()
    with db_conn.cursor() as cur:
        cur.execute("DROP TABLE IF EXISTS raw.mlb_schedule")
        cur.execute("DELETE FROM gold.prediction")
        cur.execute("DELETE FROM gold.game_feature")
        cur.execute("DELETE FROM core.game")
        cur.execute("DELETE FROM core.team")
    db_conn.commit()


@pytest.fixture(autouse=True)
def _clean(db_conn):
    # Issue #9 item 5: an autouse fixture's teardown runs regardless of
    # pass/fail, unlike the per-test trailing _reset(db_conn) call this
    # replaces, which never ran if a test failed partway through -- see
    # test_model_offense.py's identical fixture for the full explanation.
    _reset(db_conn)
    yield
    _reset(db_conn)


def _seed(db_conn):
    with db_conn.cursor() as cur:
        cur.execute(
            "INSERT INTO core.team (retro_team_id, city, nickname, first_year, last_year, mlb_team_id) "
            "VALUES ('ATL', 'Atlanta', 'Braves', 1966, 2030, 144), "
            "('NYA', 'New York', 'Yankees', 1913, 2030, 147) RETURNING id, retro_team_id"
        )
        teams = {retro: ident for ident, retro in cur.fetchall()}
        cur.execute("SELECT to_regclass('raw.mlb_schedule')")
        if cur.fetchone()[0] is None:
            cur.execute(
                "CREATE TABLE raw.mlb_schedule (game_id text, game_datetime text, game_date text, "
                "game_type text, status text, home_id text, away_id text, game_num text, venue_id text, "
                "_season text, _loaded_at timestamptz)"
            )
        else:
            for column in ("game_datetime", "_loaded_at", "venue_id"):
                cur.execute(f"ALTER TABLE raw.mlb_schedule ADD COLUMN IF NOT EXISTS {column} text")
            cur.execute(
                "ALTER TABLE raw.mlb_schedule ALTER COLUMN _loaded_at TYPE timestamptz USING _loaded_at::timestamptz"
            )
    db_conn.commit()
    return teams


def _game(db_conn, teams, retro, pk, date, game_no, home_score, away_score):
    with db_conn.cursor() as cur:
        cur.execute(
            "INSERT INTO core.game (retro_game_id, game_pk, season, game_date, game_number, home_team_id, "
            "away_team_id, home_score, away_score, game_type) VALUES (%s, %s, 2024, %s, %s, %s, %s, %s, %s, 'regular')",
            (retro, pk, date, game_no, teams["ATL"], teams["NYA"], home_score, away_score),
        )


def _schedule(db_conn, pk, date, start, status="Final", game_no="1", loaded="2024-01-01T00:00:00Z"):
    with db_conn.cursor() as cur:
        cur.execute(
            "INSERT INTO raw.mlb_schedule (game_id, game_datetime, game_date, game_type, status, home_id, away_id, game_num, _season, _loaded_at) "
            "VALUES (%s, %s, %s, 'R', %s, '144', '147', %s, '2024', %s)",
            (pk, start, date, status, game_no, loaded),
        )


def test_strict_feature_contract_is_pit_safe_for_doubleheader_and_schedule_history(db_conn):
    teams = _seed(db_conn)
    _game(db_conn, teams, "G1", "1001", "2024-04-01", 1, 5, 3)
    _game(db_conn, teams, "DH1", "1002", "2024-04-02", 1, 2, 1)
    _game(db_conn, teams, "DH2", "1003", "2024-04-02", 2, 1, 4)
    _schedule(db_conn, "1001", "2024-04-01", "2024-04-01T18:00:00Z")
    _schedule(db_conn, "1002", "2024-04-02", "2024-04-02T17:00:00Z", game_no="1")
    _schedule(db_conn, "1003", "2024-04-02", "2024-04-02T21:00:00Z", game_no="2")
    # Older postponed schedule history is preserved raw but cannot make a second feature row.
    _schedule(
        db_conn,
        "1003",
        "2024-04-01",
        "2024-04-01T17:00:00Z",
        "Postponed",
        "2",
        "2024-01-01T00:00:00Z",
    )
    # A later schedule observation under the same provider key belongs to a
    # different source-history date. The completed game must select its own
    # canonical-date observation, not whichever history row landed last.
    _schedule(
        db_conn,
        "1002",
        "2024-04-05",
        "2024-04-05T18:00:00Z",
        "Final",
        "1",
        "2024-02-01T00:00:00Z",
    )
    _schedule(db_conn, "1004", "2024-04-03", "2024-04-03T18:00:00Z", "Scheduled")
    db_conn.commit()

    raw_before = db_conn.execute("SELECT count(*) FROM raw.mlb_schedule").fetchone()[0]
    core_before = db_conn.execute("SELECT count(*) FROM core.game").fetchone()[0]
    assert features.build(db_conn, strict=True) == 4
    db_conn.commit()
    assert db_conn.execute("SELECT count(*) FROM raw.mlb_schedule").fetchone()[0] == raw_before
    assert db_conn.execute("SELECT count(*) FROM core.game").fetchone()[0] == core_before

    rows = db_conn.execute(
        "SELECT mlb_game_pk, feature_cutoff_at, home_wins, home_losses, home_runs_for, home_runs_allowed, home_win "
        "FROM gold.game_feature ORDER BY mlb_game_pk"
    ).fetchall()
    assert len(rows) == 4
    assert len({row[0] for row in rows}) == 4
    by_key = {row[0]: row[1:] for row in rows}
    assert by_key["1001"][1:6] == (None, None, None, None, True)
    # Second game sees G1 only; it cannot see either target-game final score.
    assert by_key["1002"][1:6] == (1, 0, 5, 3, True)
    assert by_key["1002"][0].timestamp() == 1712077200
    # Second doubleheader game sees the first; order comes from cutoff/game number.
    assert by_key["1003"][1:6] == (2, 0, 7, 4, False)
    assert by_key["1004"][1:6] == (2, 1, 8, 8, None)
    assert by_key["1004"][0].timestamp() == 1712167200
    assert (
        db_conn.execute(
            "SELECT count(*) FROM gold.game_feature WHERE home_field IS TRUE"
        ).fetchone()[0]
        == 4
    )

    first = db_conn.execute(
        "SELECT mlb_game_pk, home_wins, away_wins, feature_cutoff_at FROM gold.game_feature ORDER BY mlb_game_pk"
    ).fetchall()
    assert features.build(db_conn, strict=True) == 4
    db_conn.commit()
    second = db_conn.execute(
        "SELECT mlb_game_pk, home_wins, away_wins, feature_cutoff_at FROM gold.game_feature ORDER BY mlb_game_pk"
    ).fetchall()
    assert second == first


def test_strict_feature_contract_excludes_non_mlb_and_nonterminal_schedule_rows(db_conn):
    teams = _seed(db_conn)
    _game(db_conn, teams, "RETRO_ONLY", None, "2024-04-01", 1, 3, 2)
    _schedule(db_conn, "2001", "2024-04-04", "2024-04-04T18:00:00Z", "Live")
    _schedule(db_conn, "2002", "2024-04-05", "2024-04-05T18:00:00Z", "Cancelled")
    _schedule(db_conn, "2003", "2024-04-06", "2024-04-06T18:00:00Z", "Scheduled")
    db_conn.commit()

    assert features.build(db_conn, strict=True) == 1
    db_conn.commit()
    row = db_conn.execute(
        "SELECT mlb_game_pk, game_id, home_win, home_win_pct, venue_id FROM gold.game_feature"
    ).fetchone()
    assert row == ("2003", None, None, None, None)


def test_strict_feature_contract_uses_numeric_team_identity_across_name_drift(db_conn):
    _seed(db_conn)
    with db_conn.cursor() as cur:
        cur.execute(
            "INSERT INTO core.team (retro_team_id, city, nickname, first_year, last_year, mlb_team_id) "
            "VALUES ('TBA', 'Tampa Bay', 'Rays', 2008, 2030, 139)"
        )
        cur.execute(
            "INSERT INTO raw.mlb_schedule "
            "(game_id, game_datetime, game_date, game_type, status, home_id, away_id, game_num, _season, _loaded_at) "
            "VALUES ('3001', '2024-04-07T18:00:00Z', '2024-04-07', 'R', 'Scheduled', '139', '147', '1', '2024', now())"
        )
    db_conn.commit()

    assert features.build(db_conn, strict=True) == 1
    db_conn.commit()
    assert (
        db_conn.execute(
            "SELECT home_team_id FROM gold.game_feature WHERE mlb_game_pk = '3001'"
        ).fetchone()
        == db_conn.execute("SELECT id FROM core.team WHERE retro_team_id = 'TBA'").fetchone()
    )
