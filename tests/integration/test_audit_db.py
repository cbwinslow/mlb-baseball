"""Real-Postgres coverage for the read-only game-data audit."""

from datetime import UTC, datetime

from mlb_baseball import audit


def _find(findings, name: str):
    return next(finding for finding in findings if finding.name == name)


def _seed_game_audit_data(db_conn):
    with db_conn.cursor() as cur:
        cur.execute("CREATE TABLE raw.mlb_schedule (game_id text)")
        cur.execute("INSERT INTO raw.mlb_schedule VALUES ('900001'), ('900001'), ('900002')")
        cur.execute("CREATE TABLE raw.statcast_pitch (game_pk text, game_year text)")
        cur.execute(
            "INSERT INTO raw.statcast_pitch VALUES "
            "('900001', '2025'), ('999999', '2025'), (NULL, '2025')"
        )
        cur.execute(
            "INSERT INTO core.game (retro_game_id, season, game_date, game_number, game_pk) "
            "VALUES ('AUD202504010', 2025, '2025-04-01', 1, '900001'), "
            "('AUD202504011', 2025, '2025-04-01', 2, '900002'), "
            "('AUD202504020', 2025, '2025-04-02', 1, NULL) RETURNING id, game_pk"
        )
        game_rows = {game_pk: game_id for game_id, game_pk in cur.fetchall() if game_pk is not None}
        cur.execute("SELECT id FROM core.game WHERE retro_game_id = 'AUD202504020'")
        retrosheet_game_id = cur.fetchone()[0]
        cur.execute(
            "INSERT INTO core.pitch (game_id, source_game_pk, season) "
            "VALUES (%s, '900001', 2025), (NULL, '999999', 2025)",
            (game_rows['900001'],),
        )
        cur.execute(
            "INSERT INTO gold.game_feature "
            "(game_id, mlb_game_pk, season, game_date, home_win, game_instance_key) VALUES "
            "(%s, '900001', 2025, '2025-04-01', true, 'audit:completed'), "
            "(NULL, '900003', 2025, '2025-04-02', NULL, 'audit:upcoming'), "
            "(%s, NULL, 2025, '2025-04-02', true, 'audit:retrosheet')",
            (game_rows['900001'], retrosheet_game_id),
        )
        cur.execute(
            "INSERT INTO gold.prediction "
            "(mlb_game_pk, model_version, generated_at, home_win_prob, game_instance_key) "
            "VALUES ('900003', 'audit-v1', %s, 0.5, 'audit:prediction')",
            (datetime(2025, 4, 1, tzinfo=UTC),),
        )
    db_conn.commit()


def _cleanup_game_audit_data(db_conn):
    db_conn.rollback()
    with db_conn.cursor() as cur:
        cur.execute("DELETE FROM gold.prediction WHERE game_instance_key = 'audit:prediction'")
        cur.execute(
            "DELETE FROM gold.game_feature "
            "WHERE game_instance_key IN "
            "('audit:completed', 'audit:upcoming', 'audit:retrosheet', 'audit:bad')"
        )
        cur.execute("DELETE FROM core.play WHERE source = 'audit-invalid'")
        cur.execute("DELETE FROM core.pitch WHERE season = 2025")
        cur.execute("DELETE FROM core.game WHERE retro_game_id LIKE 'AUD%'")
        cur.execute("DROP TABLE IF EXISTS raw.statcast_pitch")
        cur.execute("DROP TABLE IF EXISTS raw.mlb_schedule")
    db_conn.commit()


def test_game_audit_reports_expected_nulls_and_statcast_gap(db_conn):
    _cleanup_game_audit_data(db_conn)
    _seed_game_audit_data(db_conn)
    try:
        findings = audit.run("statcast")
    finally:
        _cleanup_game_audit_data(db_conn)

    schedule = _find(findings, "raw.mlb_schedule game ID")
    assert schedule.status == "PASS"
    assert "0/3 (0.0%) missing game_id" in schedule.detail
    assert "1 repeated game IDs" in _find(findings, "raw.mlb_schedule schedule history").detail
    assert _find(findings, "core.game MLB identity").status == "PASS"
    assert _find(findings, "core.game doubleheader identity").status == "PASS"
    pitch = _find(findings, "core.pitch.game_id referential integrity")
    assert pitch.status == "PASS"
    assert "1 unresolved" in pitch.detail
    unresolved = _find(findings, "core.pitch unresolved-key coverage")
    assert unresolved.status == "WARN"
    assert "0 unresolved rows missing source_game_pk" in unresolved.detail
    coverage = _find(findings, "raw.statcast.pitch to core.game coverage (2025)")
    assert coverage.status == "WARN"
    assert "1 missing source game_pk" in coverage.detail
    assert "1 have no matching canonical game" in coverage.detail
    schedule_coverage = _find(findings, "raw.statcast.pitch to raw.schedule coverage (2025)")
    assert schedule_coverage.status == "WARN"
    assert "1 missing source game_pk" in schedule_coverage.detail
    assert "1 have no matching schedule record" in schedule_coverage.detail
    feature = _find(findings, "gold.game_feature identity")
    assert feature.status == "PASS"
    assert "1 expected upcoming rows" in feature.detail
    assert "1 Retrosheet-native completed rows" in feature.detail
    assert _find(findings, "gold.prediction immutable identity").status == "PASS"


def test_game_audit_flags_a_missing_required_schedule_key(db_conn):
    _cleanup_game_audit_data(db_conn)
    with db_conn.cursor() as cur:
        cur.execute("CREATE TABLE raw.mlb_schedule (game_id text)")
        cur.execute("INSERT INTO raw.mlb_schedule VALUES (NULL)")
    db_conn.commit()
    try:
        findings = audit.run()
    finally:
        _cleanup_game_audit_data(db_conn)

    schedule = _find(findings, "raw.mlb_schedule game ID")
    assert schedule.status == "FAIL"
    assert "1/1 (100.0%) missing game_id" in schedule.detail


def test_audit_is_read_only(db_conn):
    _cleanup_game_audit_data(db_conn)
    _seed_game_audit_data(db_conn)
    try:
        with db_conn.cursor() as cur:
            cur.execute("SELECT count(*) FROM raw.mlb_schedule")
            before = cur.fetchone()[0]
        audit.run("database")
        with db_conn.cursor() as cur:
            cur.execute("SELECT count(*) FROM raw.mlb_schedule")
            after = cur.fetchone()[0]
    finally:
        _cleanup_game_audit_data(db_conn)

    assert after == before == 3


def test_database_audit_flags_exact_duplicate_indexes(db_conn):
    with db_conn.cursor() as cur:
        cur.execute("CREATE TABLE raw.audit_duplicate_index (value text)")
        cur.execute("CREATE INDEX audit_duplicate_one ON raw.audit_duplicate_index (value)")
        cur.execute("CREATE INDEX audit_duplicate_two ON raw.audit_duplicate_index (value)")
    db_conn.commit()
    try:
        duplicate = _find(audit.run("database"), "database duplicate indexes")
    finally:
        with db_conn.cursor() as cur:
            cur.execute("DROP TABLE raw.audit_duplicate_index")
        db_conn.commit()

    assert duplicate.status == "WARN"
    assert "raw.audit_duplicate_index" in duplicate.detail


def test_game_audit_flags_invalid_values_and_missing_mlb_feature_key(db_conn):
    _cleanup_game_audit_data(db_conn)
    _seed_game_audit_data(db_conn)
    try:
        with db_conn.cursor() as cur:
            cur.execute("SELECT id FROM core.game WHERE retro_game_id = 'AUD202504010'")
            game_id = cur.fetchone()[0]
            cur.execute(
                "INSERT INTO core.play (game_id, season, source, play_index, inning) "
                "VALUES (%s, 2025, 'audit-invalid', 1, 0)",
                (game_id,),
            )
            cur.execute(
                "INSERT INTO core.game (retro_game_id, season, game_date, game_number, game_pk) "
                "VALUES ('AUD202504030', 2025, '2025-04-03', 1, '900004') RETURNING id"
            )
            missing_key_game_id = cur.fetchone()[0]
            cur.execute(
                "INSERT INTO gold.game_feature "
                "(game_id, mlb_game_pk, season, game_date, home_win, game_instance_key) VALUES "
                "(%s, NULL, 2025, '2025-04-01', true, 'audit:bad')",
                (missing_key_game_id,),
            )
        db_conn.commit()
        findings = audit.run()
    finally:
        _cleanup_game_audit_data(db_conn)

    assert _find(findings, "core.play controlled values").status == "FAIL"
    feature = _find(findings, "gold.game_feature identity")
    assert feature.status == "FAIL"
    assert "1 missing MLB keys" in feature.detail
