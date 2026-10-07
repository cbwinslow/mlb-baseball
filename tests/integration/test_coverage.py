"""`mlb coverage` against a real PostgreSQL database: seeded gaps are listed with the
exact fix command, source gaps recorded in the ledger are not missing, an empty table
says so, and the JSON output is valid and stable."""

import json

import pytest

from mlb_baseball import cli, coverage, manifest
from mlb_baseball.coverage.model import (
    SCHEDULE_SETTLED_LABEL,
    Dataset,
    Games,
    NoExpectation,
    Referenced,
    Seasons,
)

SEASON = "1962"  # inside the 1950+ analytics range, absent from every other test


def _exec(db_conn, sql, params=None):
    with db_conn.cursor() as cur:
        cur.execute(sql, params)
    db_conn.commit()


def _ensure_table(db_conn, created, name, columns):
    """Create ``raw.<name>`` if no other test did; remember it so teardown drops only ours."""
    with db_conn.cursor() as cur:
        cur.execute("SELECT to_regclass(%s)", (f"raw.{name}",))
        (exists,) = cur.fetchone()
        if exists is None:
            cur.execute(f"CREATE TABLE raw.{name} ({columns})")
            created.append(name)
    db_conn.commit()


@pytest.fixture
def seeded(db_conn):
    """Six final games and one not-yet-played game in 1962: two have win probability
    rows, one is a recorded source gap (ledger ``unavailable``), three have neither."""
    created: list[str] = []
    _ensure_table(
        db_conn,
        created,
        "mlb_schedule",
        "game_id text, status text, _season text, game_type text, game_date text",
    )
    _ensure_table(db_conn, created, "mlb_win_prob", "game_pk text, _season text")
    games = [f"96200{n}" for n in range(1, 7)]
    _exec(db_conn, "DELETE FROM raw.mlb_schedule WHERE _season = %s", (SEASON,))
    _exec(db_conn, "DELETE FROM raw.mlb_win_prob WHERE _season = %s", (SEASON,))
    _exec(
        db_conn,
        "DELETE FROM meta.ingestion_item WHERE source = 'mlb_api' AND item_key LIKE %s",
        (f"{SEASON}:%",),
    )
    for game in games:
        _exec(
            db_conn,
            "INSERT INTO raw.mlb_schedule (game_id, status, _season) VALUES (%s, 'Final', %s)",
            (game, SEASON),
        )
    _exec(
        db_conn,
        "INSERT INTO raw.mlb_schedule (game_id, status, _season) VALUES ('9620099', "
        "'Scheduled', %s)",
        (SEASON,),
    )
    for game in games[:2]:
        _exec(
            db_conn,
            "INSERT INTO raw.mlb_win_prob (game_pk, _season) VALUES (%s, %s)",
            (game, SEASON),
        )
    _exec(
        db_conn,
        "INSERT INTO meta.ingestion_item (source, dataset, item_key, status, http_status) "
        "VALUES ('mlb_api', 'win_probability', %s, 'unavailable', 404)",
        (f"{SEASON}:{games[2]}",),
    )
    yield games
    db_conn.rollback()
    _exec(db_conn, "DELETE FROM raw.mlb_schedule WHERE _season = %s", (SEASON,))
    _exec(db_conn, "DELETE FROM raw.mlb_win_prob WHERE _season = %s", (SEASON,))
    _exec(
        db_conn,
        "DELETE FROM meta.ingestion_item WHERE source = 'mlb_api' AND item_key LIKE %s",
        (f"{SEASON}:%",),
    )
    for name in created:
        _exec(db_conn, f"DROP TABLE raw.{name}")


def _group(report, table, label):
    row = next(t for t in report.tables if t.table == table)
    return row, next(g for g in row.groups if g.label == label)


def test_seeded_gap_is_listed_and_fix_command_names_the_season(seeded):
    report = coverage.collect(source="mlb_api", table="mlb_win_prob")

    row, group = _group(report, "raw.mlb_win_prob", SEASON)
    assert (group.expected, group.held, group.accounted, group.missing) == (6, 2, 1, 3)
    assert row.status == "missing"
    assert f"--start-year {SEASON} --end-year {SEASON}" in row.fix
    assert row.fix.startswith("mlb ingest mlb_api --stage analytics")
    assert f"{SEASON}: 3 games" in coverage.render_text(report)


def test_game_with_unavailable_ledger_item_is_not_missing(seeded):
    # Only the ledger item distinguishes game 3 (source returned 404) from games 4-6.
    report = coverage.collect(source="mlb_api", table="mlb_win_prob")
    _, group = _group(report, "raw.mlb_win_prob", SEASON)
    assert group.accounted == 1
    assert group.missing == 3


def test_ledger_item_for_another_dataset_does_not_hide_a_gap(seeded, db_conn):
    # Context-metrics says game 4 is unavailable; that says nothing about win probability.
    _exec(
        db_conn,
        "INSERT INTO meta.ingestion_item (source, dataset, item_key, status) "
        "VALUES ('mlb_api', 'context_metrics', %s, 'unavailable')",
        (f"{SEASON}:{seeded[3]}",),
    )
    report = coverage.collect(source="mlb_api", table="mlb_win_prob")
    _, group = _group(report, "raw.mlb_win_prob", SEASON)
    assert group.missing == 3


def test_empty_table_says_so(db_conn):
    created: list[str] = []
    _ensure_table(db_conn, created, "test_cov_empty", "_season text")
    try:
        dataset = Dataset(
            "mlb_api", "raw.test_cov_empty", Seasons(first=2000, through="prior"), "mlb ingest x"
        )
        report = coverage.collect(datasets=[dataset])
        row = report.tables[0]
        assert row.status == "empty"
        assert row.rows == 0
        assert row.held == 0 and row.missing == row.expected > 0
        assert "EMPTY" in coverage.render_text(report)
    finally:
        for name in created:
            _exec(db_conn, f"DROP TABLE raw.{name}")


def test_absent_table_says_so():
    dataset = Dataset(
        "mlb_api", "raw.test_cov_never_created", Seasons(first=2000, through="prior"), "mlb x"
    )
    row = coverage.collect(datasets=[dataset]).tables[0]
    assert row.status == "table_absent"
    assert row.fix == "mlb x"
    assert "does not exist" in coverage.render_text(coverage.Report([row]))


def test_game_expectation_with_no_games_in_the_schedule_is_reported_not_passed(db_conn):
    created: list[str] = []
    _ensure_table(
        db_conn,
        created,
        "mlb_schedule",
        "game_id text, status text, _season text, game_type text, game_date text",
    )
    _ensure_table(db_conn, created, "test_cov_games", "game_pk text, _season text")
    try:
        dataset = Dataset(
            "mlb_api", "raw.test_cov_games", Games(first=3000, ledger="x"), "mlb ingest mlb_api"
        )
        row = coverage.collect(datasets=[dataset]).tables[0]
        assert row.status == "no_basis"
        assert "no final games" in row.expectation
    finally:
        for name in created:
            _exec(db_conn, f"DROP TABLE raw.{name}")


def test_table_without_expectation_says_why():
    dataset = Dataset("mlb_api", "raw.mlb_venue", NoExpectation("whole-catalog reload"), "mlb x")
    report = coverage.collect(datasets=[dataset])
    assert report.tables[0].status == "no_expectation"
    assert "no expectation defined: whole-catalog reload" in coverage.render_text(report)


def test_json_is_valid_and_stable(seeded):
    first = coverage.render_json(coverage.collect(source="mlb_api", table="mlb_win_prob"))
    second = coverage.render_json(coverage.collect(source="mlb_api", table="mlb_win_prob"))
    assert first == second
    payload = json.loads(first)
    table = payload["sources"][0]["tables"][0]
    assert payload["sources"][0]["source"] == "mlb_api"
    assert table["table"] == "raw.mlb_win_prob"
    assert set(table) >= {
        "table",
        "unit",
        "status",
        "expectation",
        "expected",
        "held",
        "accounted",
        "missing",
        "rows",
        "missing_groups",
        "fix",
    }
    assert {"group": SEASON, "missing": 3} in table["missing_groups"]


def test_every_registered_table_is_reported_and_none_is_silent(db_conn):
    report = coverage.collect()
    with db_conn.cursor() as cur:
        cur.execute(
            "SELECT 'raw.' || relname FROM pg_class c "
            "JOIN pg_namespace n ON n.oid = c.relnamespace "
            "WHERE n.nspname = 'raw' AND c.relkind IN ('r', 'p')"
        )
        live = {name for (name,) in cur.fetchall()}
    reported = {t.table for t in report.tables}
    assert live <= reported
    assert all(t.status for t in report.tables)


def test_coverage_never_writes(seeded, db_conn):
    def counts():
        with db_conn.cursor() as cur:
            cur.execute("SELECT count(*) FROM meta.ingestion_item")
            (ledger,) = cur.fetchone()
            cur.execute("SELECT count(*) FROM raw.mlb_schedule")
            (schedule,) = cur.fetchone()
            cur.execute("SELECT count(*) FROM meta.ingestion_run")
            (runs,) = cur.fetchone()
        db_conn.rollback()
        return ledger, schedule, runs

    before = counts()
    coverage.collect()
    assert counts() == before


def test_kalshi_candles_use_the_market_catalog_and_the_ledger(db_conn):
    created: list[str] = []
    _ensure_table(db_conn, created, "kalshi_market", "ticker text, open_time text, close_time text")
    tickers = [f"KXCOV-{n}" for n in range(4)]
    try:
        for ticker in tickers:
            _exec(
                db_conn,
                "INSERT INTO raw.kalshi_market (ticker, open_time, close_time) "
                "VALUES (%s, '2031-04-01T00:00:00Z', '2031-04-02T00:00:00Z')",
                (ticker,),
            )
        for ticker, status in (
            (tickers[0], "loaded"),
            (tickers[1], "unavailable"),
            (tickers[2], "failed"),
        ):
            _exec(
                db_conn,
                "INSERT INTO meta.ingestion_item (source, dataset, item_key, status) "
                "VALUES ('kalshi', 'candles', %s, %s)",
                (ticker, status),
            )
        report = coverage.collect(source="kalshi", table="kalshi_candle")
        _, group = _group(report, "raw.kalshi_candle", "2031")
        assert (group.expected, group.held, group.accounted, group.missing) == (4, 1, 1, 2)
    finally:
        _exec(db_conn, "DELETE FROM raw.kalshi_market WHERE ticker LIKE 'KXCOV-%'")
        _exec(db_conn, "DELETE FROM meta.ingestion_item WHERE item_key LIKE 'KXCOV-%'")
        for name in created:
            _exec(db_conn, f"DROP TABLE raw.{name}")


@pytest.fixture
def schedule_1963(db_conn):
    """Schedule rows of 1963 with the columns the settled check reads."""
    created: list[str] = []
    _ensure_table(
        db_conn,
        created,
        "mlb_schedule",
        "game_id text, status text, _season text, game_type text, game_date text",
    )
    _exec(db_conn, "DELETE FROM raw.mlb_schedule WHERE _season = '1963'")
    yield db_conn
    _exec(db_conn, "DELETE FROM raw.mlb_schedule WHERE _season = '1963'")
    for name in created:
        _exec(db_conn, f"DROP TABLE raw.{name}")


def _add_game(db_conn, game_id, status, game_date, game_type="R"):
    _exec(
        db_conn,
        "INSERT INTO raw.mlb_schedule (game_id, status, _season, game_type, game_date) "
        "VALUES (%s, %s, '1963', %s, %s)",
        (game_id, status, game_type, game_date),
    )


def test_past_game_still_scheduled_is_a_gap_but_future_and_exhibition_are_not(schedule_1963):
    _add_game(schedule_1963, "1", "Final", "1963-04-01")
    _add_game(schedule_1963, "2", "Postponed", "1963-04-02")
    _add_game(schedule_1963, "3", "Scheduled", "1963-04-03")  # long past, never refreshed
    _add_game(schedule_1963, "4", "Scheduled", "1963-04-04", game_type="E")  # exhibition
    _add_game(schedule_1963, "5", "Scheduled", "2999-04-05")  # future: expected to be pending
    report = coverage.collect(table=SCHEDULE_SETTLED_LABEL)
    group = next(g for g in report.tables[0].groups if g.label == "1963")
    assert (group.expected, group.held, group.missing) == (3, 2, 1)
    assert report.has_gap


def test_completed_early_games_are_expected_like_final_ones(schedule_1963):
    created: list[str] = []
    _ensure_table(schedule_1963, created, "mlb_win_prob", "game_pk text, _season text")
    try:
        _add_game(schedule_1963, "11", "Final", "1963-04-01")
        _add_game(schedule_1963, "12", "Completed Early", "1963-04-02")
        _add_game(schedule_1963, "13", "Postponed", "1963-04-03")
        report = coverage.collect(source="mlb_api", table="mlb_win_prob")
        group = next(g for g in report.tables[0].groups if g.label == "1963")
        assert group.expected == 2
    finally:
        for name in created:
            _exec(schedule_1963, f"DROP TABLE raw.{name}")


def test_manifest_files_not_loaded_are_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(manifest, "DOWNLOADS_ROOT", tmp_path)
    manifest.save_manifest(
        "retrosheet_box",
        {
            "1871box.zip": {"status": "loaded"},
            "1890sbox.zip": {"status": "downloaded"},
            "TEAMABR.TXT": {"status": "reference"},
        },
    )
    report = coverage.collect(
        source="retrosheet_box", table="downloads/retrosheet_box/manifest.json"
    )
    row = report.tables[0]
    assert (row.expected, row.held, row.missing) == (2, 1, 1)
    assert row.fix == "mlb ingest retrosheet_box"


def test_manifest_missing_file_is_reported_not_silent(tmp_path, monkeypatch):
    monkeypatch.setattr(manifest, "DOWNLOADS_ROOT", tmp_path)
    report = coverage.collect(
        source="retrosheet_box", table="downloads/retrosheet_box/manifest.json"
    )
    row = report.tables[0]
    assert row.status == "inputs_absent"
    assert "does not exist" in row.expectation
    assert report.has_gap


def test_cli_coverage_runs_through_the_real_parser(seeded, capsys):
    cli.main(["coverage", "--source", "mlb_api", "--table", "mlb_win_prob", "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert payload["sources"][0]["tables"][0]["table"] == "raw.mlb_win_prob"


def test_cli_markdown_output(seeded, capsys):
    cli.main(["coverage", "--source", "mlb_api", "--table", "mlb_win_prob", "--markdown"])
    out = capsys.readouterr().out
    assert out.startswith("# Coverage")
    assert "`raw.mlb_win_prob`" in out


def test_cli_rejects_json_with_markdown():
    with pytest.raises(SystemExit):
        cli.main(["coverage", "--json", "--markdown"])


def test_cli_missing_only_hides_clean_tables(seeded, capsys):
    cli.main(["coverage", "--source", "mlb_api", "--missing-only", "--json"])
    tables = json.loads(capsys.readouterr().out)["sources"][0]["tables"]
    assert tables
    assert all(t["status"] not in ("complete", "no_expectation") for t in tables)
    assert "raw.mlb_win_prob" in {t["table"] for t in tables}


def test_cli_fail_on_gap_exits_1_when_a_gap_exists(seeded):
    with pytest.raises(SystemExit) as exc:
        cli.main(["coverage", "--source", "mlb_api", "--table", "mlb_win_prob", "--fail-on-gap"])
    assert exc.value.code == 1


def test_only_reference_tables_is_not_a_gap():
    row = coverage.TableReport("mlb_api", "raw.x", "season", "no_expectation", "reason", 5, [], "")
    done = coverage.TableReport("mlb_api", "raw.y", "season", "complete", "all", 5, [], "")
    report = coverage.Report([row, done])
    assert not report.has_gap
    assert report.only_gaps().tables == []


@pytest.fixture
def entities(db_conn):
    """A people table holding 1, 2, 3 and two tables that mention 1, 2, 4, 5 and blanks."""
    created: list[str] = []
    for name, cols in (
        ("test_cov_person", "person_id text"),
        ("test_cov_ref_a", "pid text"),
        ("test_cov_ref_b", "pitcher text, yr text"),
    ):
        _ensure_table(db_conn, created, name, cols)
    _exec(db_conn, "INSERT INTO raw.test_cov_person VALUES ('1'), ('2'), ('3')")
    _exec(db_conn, "INSERT INTO raw.test_cov_ref_a VALUES ('1'), ('2'), ('2'), ('4'), (''), (NULL)")
    _exec(db_conn, "INSERT INTO raw.test_cov_ref_b VALUES ('1', 'x'), ('5', 'x'), ('4', 'y')")
    yield
    for name in created:
        _exec(db_conn, f"DROP TABLE raw.{name}")


def _person_dataset():
    return Dataset(
        "mlb_api",
        "raw.test_cov_person",
        Referenced(
            ("person_id",),
            (("raw.test_cov_ref_a", ("pid",)), ("raw.test_cov_ref_b", ("pitcher",))),
            "person",
        ),
        "mlb ingest mlb_api",
    )


def test_referenced_reports_one_line_per_referencing_column(entities):
    row = coverage.collect(datasets=[_person_dataset()]).tables[0]
    by_label = {g.label: (g.expected, g.held, g.missing) for g in row.groups}
    # ref_a uses 1, 2, 4 (blank and NULL are not ids; the repeated 2 counts once);
    # ref_b uses 1, 5, 4
    assert by_label == {
        "raw.test_cov_ref_a.pid": (3, 2, 1),
        "raw.test_cov_ref_b.pitcher": (3, 1, 2),
    }
    assert row.status == "missing"
    assert row.fix == "mlb ingest mlb_api"
    text = coverage.render_text(coverage.Report([row]))
    assert "raw.test_cov_ref_b.pitcher: 2 persons" in text


def test_referenced_complete_when_every_used_id_exists(entities, db_conn):
    _exec(db_conn, "INSERT INTO raw.test_cov_person VALUES ('4'), ('5')")
    row = coverage.collect(datasets=[_person_dataset()]).tables[0]
    assert row.status == "complete"


def test_referenced_with_nothing_referencing_it_is_not_a_pass(entities, db_conn):
    _exec(db_conn, "DELETE FROM raw.test_cov_ref_a")
    _exec(db_conn, "DELETE FROM raw.test_cov_ref_b")
    row = coverage.collect(datasets=[_person_dataset()]).tables[0]
    assert row.status == "no_basis"


def test_referenced_composite_key(db_conn):
    created: list[str] = []
    _ensure_table(db_conn, created, "test_cov_team", "yearid text, teamid text")
    _ensure_table(db_conn, created, "test_cov_bat", "yearid text, teamid text")
    try:
        _exec(db_conn, "INSERT INTO raw.test_cov_team VALUES ('2000', 'BOS')")
        _exec(
            db_conn,
            "INSERT INTO raw.test_cov_bat VALUES ('2000', 'BOS'), ('2000', 'NYA'), ('2001', 'BOS')",
        )
        dataset = Dataset(
            "lahman",
            "raw.test_cov_team",
            Referenced(
                ("yearid", "teamid"), (("raw.test_cov_bat", ("yearid", "teamid")),), "team-season"
            ),
            "mlb ingest lahman",
        )
        row = coverage.collect(datasets=[dataset]).tables[0]
        assert (row.expected, row.held) == (3, 1)
    finally:
        for name in created:
            _exec(db_conn, f"DROP TABLE raw.{name}")


def test_referenced_reports_a_missing_referencing_table(entities, db_conn):
    dataset = Dataset(
        "mlb_api",
        "raw.test_cov_person",
        Referenced(("person_id",), (("raw.test_cov_never_created", ("pid",)),), "person"),
        "mlb ingest mlb_api",
    )
    assert coverage.collect(datasets=[dataset]).tables[0].status == "inputs_absent"


def test_declared_date_column_reports_first_and_last_date(db_conn):
    created: list[str] = []
    _ensure_table(db_conn, created, "test_cov_dates", "d text, _season text")
    try:
        _exec(
            db_conn,
            "INSERT INTO raw.test_cov_dates VALUES "
            "('19990412','1999'), ('20010930','2001'), ('junk','2001')",
        )
        dataset = Dataset(
            "mlb_api",
            "raw.test_cov_dates",
            Seasons(first=1999, through="prior"),
            "mlb ingest x",
            date_column="d",
        )
        row = coverage.collect(datasets=[dataset]).tables[0]
        assert (row.first_date, row.last_date, row.date_not_parsed) == (
            "1999-04-12",
            "2001-09-30",
            1,
        )
        text = coverage.render_text(coverage.Report([row]))
        assert "dates (d): 1999-04-12 to 2001-09-30; 1 values not a date" in text
        assert "1999-04-12 to 2001-09-30" in coverage.render_markdown(coverage.Report([row]))
        payload = json.loads(coverage.render_json(coverage.Report([row])))
        assert payload["sources"][0]["tables"][0]["first_date"] == "1999-04-12"
    finally:
        for name in created:
            _exec(db_conn, f"DROP TABLE raw.{name}")


class _FakeLive:
    """Stands in for a publisher: the source reports 10 games in 2001 and 7 in 2002."""

    description = "fake publisher totals"

    def measure(self, cur, table):
        from mlb_baseball.coverage.live import LiveResult
        from mlb_baseball.coverage.model import Group

        return LiveResult([Group("2001", 10, 10), Group("2002", 7, 5)], ["2003: TimeoutError: x"])


def test_probe_reports_where_the_source_and_the_table_differ(db_conn):
    created: list[str] = []
    _ensure_table(db_conn, created, "test_cov_live", "_season text")
    try:
        _exec(db_conn, "INSERT INTO raw.test_cov_live VALUES ('2001')")
        dataset = Dataset(
            "mlb_api",
            "raw.test_cov_live",
            Seasons(first=2001, through="prior"),
            "mlb ingest x",
            live=_FakeLive(),
        )
        quiet = coverage.collect(datasets=[dataset]).tables[0]
        assert quiet.live == [] and not quiet.live_errors  # nothing asked without --probe
        row = coverage.collect(datasets=[dataset], probe=True).tables[0]
        assert [g.label for g in row.live_differs] == ["2002"]
        assert row.is_gap
        text = coverage.render_text(coverage.Report([row]))
        assert "2 compared, 1 differ, 1 could not be asked" in text
        assert "2002: held 5, source 7" in text
        assert "2003: TimeoutError" in text
        payload = json.loads(coverage.render_json(coverage.Report([row])))
        assert payload["sources"][0]["tables"][0]["live"][1] == {
            "group": "2002",
            "source": 7,
            "held": 5,
        }
    finally:
        for name in created:
            _exec(db_conn, f"DROP TABLE raw.{name}")
