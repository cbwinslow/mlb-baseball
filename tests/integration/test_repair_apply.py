"""`apply` against real PostgreSQL: runs only planned actions, records each attempt, a dry run
writes nothing, and a second run after the gap is closed changes nothing."""

from datetime import UTC, datetime

from mlb_baseball.coverage.engine import TableReport
from mlb_baseball.coverage.model import Group
from mlb_baseball.repair import apply, load_attempts, plan, record_attempt

TABLE = "raw.statcast_pitch"


def _now():
    return datetime.now(UTC)


def _gap():
    return TableReport(
        "statcast", TABLE, "game", "missing", "x", 10, [Group("2026", 10, 8)], "mlb ingest statcast"
    )


def _clean(db_conn):
    with db_conn.cursor() as cur:
        cur.execute("DELETE FROM meta.repair_attempt WHERE table_name = %s", (TABLE,))
    db_conn.commit()


def _count(db_conn):
    with db_conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM meta.repair_attempt WHERE table_name = %s", (TABLE,))
        return cur.fetchone()[0]


def test_apply_runs_the_command_and_records_one_attempt(db_conn):
    _clean(db_conn)
    calls = []

    def runner(argv, timeout):
        calls.append(argv)
        return 0

    results = apply(plan([_gap()], load_attempts(db_conn), _now()), db_conn, runner)
    assert calls == [("mlb", "ingest", "statcast")]
    assert [r.outcome for r in results] == ["ok"]
    assert _count(db_conn) == 1
    _clean(db_conn)


def test_a_failing_command_is_recorded_as_failed(db_conn):
    _clean(db_conn)
    results = apply(plan([_gap()], {}, _now()), db_conn, lambda argv, timeout: 3)
    assert [r.outcome for r in results] == ["failed"]
    assert load_attempts(db_conn)[TABLE][0].outcome == "failed"
    _clean(db_conn)


def test_second_run_the_same_night_changes_nothing(db_conn):
    _clean(db_conn)
    calls = []
    runner = lambda argv, timeout: calls.append(argv) or 0  # noqa: E731
    apply(plan([_gap()], load_attempts(db_conn), _now()), db_conn, runner)
    apply(plan([_gap()], load_attempts(db_conn), _now()), db_conn, runner)
    assert len(calls) == 1
    assert _count(db_conn) == 1
    _clean(db_conn)


def test_plan_alone_writes_nothing(db_conn):
    _clean(db_conn)
    plan([_gap()], load_attempts(db_conn), _now())
    assert _count(db_conn) == 0


def test_a_hung_command_is_a_failure_not_a_crash(db_conn):
    _clean(db_conn)

    def runner(argv, timeout):
        raise TimeoutError("too slow")

    results = apply(plan([_gap()], {}, _now()), db_conn, runner)
    assert [r.outcome for r in results] == ["failed"]
    assert "too slow" in results[0].detail
    _clean(db_conn)


def test_reset_is_recorded_and_visible(db_conn):
    _clean(db_conn)
    record_attempt(db_conn, TABLE, "reset", "owner reviewed")
    assert load_attempts(db_conn)[TABLE][0].outcome == "reset"
    _clean(db_conn)


def test_tables_sharing_one_command_run_it_once_and_all_get_the_outcome(db_conn):
    tables = ("raw.mlb_linescore", "raw.mlb_umpire")
    with db_conn.cursor() as cur:
        cur.execute("DELETE FROM meta.repair_attempt WHERE table_name = ANY(%s)", (list(tables),))
    db_conn.commit()
    gaps = [
        TableReport(
            "mlb_api", t, "game", "missing", "x", 10, [Group("2026", 10, 8)], "mlb ingest mlb_api"
        )
        for t in tables
    ]
    calls = []
    results = apply(plan(gaps, {}, _now()), db_conn, lambda a, t: calls.append(a) or 0)
    assert len(calls) == 1
    assert [(r.table, r.outcome) for r in results] == [(t, "ok") for t in tables]
    with db_conn.cursor() as cur:
        cur.execute("DELETE FROM meta.repair_attempt WHERE table_name = ANY(%s)", (list(tables),))
    db_conn.commit()


def test_apply_ignores_actions_that_are_not_planned(db_conn):
    from mlb_baseball.repair import Action

    calls = []
    skipped = [
        Action(TABLE, "capped", ("mlb", "ingest", "statcast")),
        Action(TABLE, "suspended", ("mlb", "ingest", "statcast")),
        Action(TABLE, "report_only"),
    ]
    assert apply(skipped, db_conn, lambda a, t: calls.append(a) or 0) == []
    assert calls == []
