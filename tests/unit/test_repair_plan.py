"""`plan` turns coverage gaps into actions: only safe-listed repairs are planned, a repair runs
at most once a night, three failures in a row suspend it, and everything else is only reported."""

from datetime import UTC, datetime

import pytest

from mlb_baseball.coverage.engine import TableReport
from mlb_baseball.coverage.model import Group
from mlb_baseball.repair import SAFE_REPAIRS, Attempt, plan

NOW = datetime(2026, 10, 8, 7, 0, tzinfo=UTC)


def _gap(table, fix, source="statcast", status="missing", missing=2):
    return TableReport(
        source, table, "game", status, "x", 10, [Group("2026", 10, 10 - missing)], fix
    )


STATCAST = _gap("raw.statcast_pitch", "mlb ingest statcast")


def test_safe_listed_gap_is_planned_with_its_exact_command():
    (action,) = plan([STATCAST], {}, NOW)
    assert action.status == "planned"
    assert action.argv == ("mlb", "ingest", "statcast")


def test_unlisted_gap_is_reported_only():
    person = _gap("raw.mlb_person", "mlb ingest mlb_api", source="mlb_api")
    (action,) = plan([person], {}, NOW)
    assert action.status == "report_only"
    assert action.argv == ()


def test_a_fix_text_that_differs_from_the_safe_command_is_not_run():
    odd = _gap("raw.statcast_pitch", "mlb ingest statcast --mode bootstrap")
    (action,) = plan([odd], {}, NOW)
    assert action.status == "report_only"


def test_complete_or_empty_tables_are_not_repaired():
    done = TableReport("statcast", "raw.statcast_pitch", "game", "complete", "x", 10, [], "")
    empty = _gap("raw.statcast_pitch", "mlb ingest statcast", status="empty")
    assert plan([done], {}, NOW) == []
    assert plan([empty], {}, NOW)[0].status == "report_only"


def test_second_attempt_on_the_same_night_is_capped():
    today = Attempt("ok", NOW.replace(hour=6))
    (action,) = plan([STATCAST], {"raw.statcast_pitch": [today]}, NOW)
    assert action.status == "capped"


def test_three_failures_in_a_row_suspend_the_repair():
    failed = [Attempt("failed", datetime(2026, 10, d, 6, tzinfo=UTC)) for d in (7, 6, 5)]
    (action,) = plan([STATCAST], {"raw.statcast_pitch": failed}, NOW)
    assert action.status == "suspended"


def test_two_failures_do_not_suspend_and_a_success_resets_the_count():
    two = [Attempt("failed", datetime(2026, 10, d, 6, tzinfo=UTC)) for d in (7, 6)]
    assert plan([STATCAST], {"raw.statcast_pitch": two}, NOW)[0].status == "planned"
    mixed = [
        Attempt("failed", datetime(2026, 10, 7, 6, tzinfo=UTC)),
        Attempt("ok", datetime(2026, 10, 6, 6, tzinfo=UTC)),
        Attempt("failed", datetime(2026, 10, 5, 6, tzinfo=UTC)),
        Attempt("failed", datetime(2026, 10, 4, 6, tzinfo=UTC)),
    ]
    assert plan([STATCAST], {"raw.statcast_pitch": mixed}, NOW)[0].status == "planned"


def test_a_reset_ends_a_suspension():
    rows = [
        Attempt("reset", datetime(2026, 10, 7, 12, tzinfo=UTC)),
        *[Attempt("failed", datetime(2026, 10, d, 6, tzinfo=UTC)) for d in (7, 6, 5)],
    ]
    assert plan([STATCAST], {"raw.statcast_pitch": rows}, NOW)[0].status == "planned"


def test_every_safe_repair_has_a_reason_a_timeout_and_a_mlb_ingest_command():
    assert SAFE_REPAIRS
    for entry in SAFE_REPAIRS:
        assert entry.reason
        assert entry.timeout_seconds > 0
        assert entry.argv[:2] == ("mlb", "ingest")


@pytest.mark.parametrize("table", ["raw.kalshi_candle", "raw.polymarket_price"])
def test_market_backfills_are_on_the_safe_list(table):
    assert table in {e.table for e in SAFE_REPAIRS}


def test_allowed_flags_are_accepted_for_the_entries_that_list_them():
    kalshi = _gap("raw.kalshi_candle", "mlb ingest kalshi --mode backfill", source="kalshi")
    assert plan([kalshi], {}, NOW)[0].status == "planned"
    analytics = _gap(
        "raw.mlb_win_prob",
        "mlb ingest mlb_api --stage analytics --start-year 1950 --end-year 2025",
        source="mlb_api",
    )
    assert plan([analytics], {}, NOW)[0].status == "planned"


@pytest.mark.parametrize(
    "fix",
    [
        "mlb ingest statcast --stage analytics",
        "mlb ingest kalshi --mode backfill --mode backfill",
        "mlb ingest kalshi --mode backfill --start-year 1",
        "mlb ingest mlb_api --start-year 19\u00b2",
        "mlb ingest statcast; rm -rf x",
        "mlb ingest kalshi --mode=backfill",
        "",
    ],
)
def test_flags_outside_the_entry_or_repeated_are_not_run(fix):
    gap = _gap("raw.kalshi_candle" if "kalshi" in fix else "raw.statcast_pitch", fix)
    if "mlb_api" in fix:
        gap = _gap("raw.mlb_win_prob", fix, source="mlb_api")
    assert plan([gap], {}, NOW)[0].status == "report_only"


def test_a_safe_table_that_is_empty_is_never_planned():
    empty = _gap("raw.statcast_pitch", "mlb ingest statcast", status="empty")
    assert plan([empty], {}, NOW)[0].status == "report_only"


def test_reset_of_an_unknown_table_is_refused(capsys):
    from mlb_baseball import repair

    assert repair.run(reset="raw.nonsense") == 2
    assert "not on the safe list" in capsys.readouterr().out


def test_children_run_as_this_pythons_entry_point_not_a_path_lookup():
    import sys

    from mlb_baseball.repair import _child_argv

    argv = _child_argv(("mlb", "ingest", "statcast"))
    assert argv[0] == sys.executable
    assert argv[-2:] == ["ingest", "statcast"]
