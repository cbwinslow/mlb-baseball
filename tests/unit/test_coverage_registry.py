"""Registry and rendering contracts for `mlb coverage` that need no database."""

import re
from pathlib import Path

import pytest

from mlb_baseball import cli, coverage
from mlb_baseball.connectors import statcast_leaderboard
from mlb_baseball.coverage.engine import TableReport
from mlb_baseball.coverage.model import Group
from mlb_baseball.coverage.registry import DATASETS
from mlb_baseball.coverage.render import missing_text
from mlb_baseball.registry import CONNECTORS

INVENTORY = Path(__file__).resolve().parents[2] / "docs" / "RAW_INVENTORY.md"


def test_every_table_in_the_raw_inventory_has_an_expectation_or_a_stated_reason():
    documented = set(re.findall(r"^\| `(raw\.[a-z0-9_]+)` \|", INVENTORY.read_text(), re.M))
    registered = {d.table for d in coverage.DATASETS}
    assert documented
    assert documented <= registered, sorted(documented - registered)


def test_registry_has_no_duplicate_tables_and_only_known_sources():
    tables = [d.table for d in coverage.DATASETS]
    assert len(tables) == len(set(tables))
    assert {d.source for d in coverage.DATASETS} <= set(CONNECTORS)


def test_every_fix_command_names_a_real_ingest_source():
    for dataset in coverage.DATASETS:
        if dataset.fix:
            assert dataset.fix.startswith(f"mlb ingest {dataset.source}"), dataset.table


def _season_report(*missing_years: int) -> TableReport:
    groups = [Group(str(y), 1, 0) for y in missing_years]
    return TableReport("s", "raw.t", "season", "missing", "x", 0, groups, "fix")


def test_missing_seasons_collapse_into_ranges():
    assert missing_text(_season_report(1999, 2000, 2001, 2005, 2008, 2009)) == (
        "1999-2001 (3 seasons); 2005 (1 season); 2008-2009 (2 seasons)"
    )


def test_missing_games_list_per_group():
    groups = [Group("1999", 5, 2), Group("2000", 4, 4), Group("2001", 3, 2, 0)]
    table = TableReport("s", "raw.t", "game", "missing", "x", 1, groups, "fix")
    assert missing_text(table) == "1999: 3 games; 2001: 1 game"


def test_cli_coverage_dispatches_options(monkeypatch):
    seen = {}
    monkeypatch.setattr(cli.coverage, "run", lambda **kwargs: seen.update(kwargs))

    cli.main(["coverage", "--source", "mlb_api", "--table", "mlb_win_prob", "--json"])

    assert seen == {
        "source": "mlb_api",
        "table": "mlb_win_prob",
        "as_json": True,
        "as_markdown": False,
        "missing_only": False,
        "probe": False,
        "unexplained_only": False,
    }


def test_cli_coverage_fail_on_gap_sets_the_exit_code(monkeypatch):
    monkeypatch.setattr(cli.coverage, "run", lambda **kwargs: True)
    with pytest.raises(SystemExit) as exc:
        cli.main(["coverage", "--fail-on-gap", "--missing-only"])
    assert exc.value.code == 1

    monkeypatch.setattr(cli.coverage, "run", lambda **kwargs: False)
    cli.main(["coverage", "--fail-on-gap"])


def test_cli_coverage_rejects_unknown_source():
    with pytest.raises(SystemExit):
        cli.main(["coverage", "--source", "nope"])


def test_every_declared_date_column_is_a_real_column_of_its_table():
    from pathlib import Path

    from mlb_baseball.coverage.registry import DATE_COLUMNS

    text = Path("docs/RAW_INVENTORY.md").read_text()
    for table, column in DATE_COLUMNS.items():
        marker = f"<summary><code>{table}</code> columns</summary>"
        assert marker in text, f"{table} is not in docs/RAW_INVENTORY.md"
        block = text.split(marker, 1)[1].split("</details>", 1)[0]
        assert f"- `{column}` " in block, f"{table} has no column {column}"


def test_late_starting_leaderboards_are_expected_from_their_own_first_year():
    by_table = {d.table: d for d in coverage.DATASETS}
    for table, first in statcast_leaderboard.FIRST_SERVED_YEAR.items():
        assert by_table[table].spec.first == first, table
    assert by_table["raw.statcast_sprint_speed"].spec.first == statcast_leaderboard.FIRST_YEAR


def test_live_schedule_check_includes_next_season_only_when_published(monkeypatch):
    from datetime import date

    from mlb_baseball.coverage import live

    next_year = date.today().year + 1
    published = {"value": 100}

    def fake_total(year, league_ids):
        return published["value"] if year == next_year else 0 if year > next_year else 50

    class Cur:
        def execute(self, *args):
            pass

        def fetchall(self):
            return []

    monkeypatch.setattr(live.MlbScheduleTotals, "_total", staticmethod(fake_total))
    monkeypatch.setattr(live, "REQUEST_PAUSE_SECONDS", 0)
    check = live.MlbScheduleTotals(first=next_year - 1)
    with_next = check.measure(Cur(), "raw.mlb_schedule")
    assert [g.label.split()[0] for g in with_next.groups] == [str(next_year - 1), str(next_year)]
    published["value"] = 0
    without = check.measure(Cur(), "raw.mlb_schedule")
    assert [g.label.split()[0] for g in without.groups] == [str(next_year - 1)]


def _report(status: str, groups: list[Group], table: str = "raw.x", **extra) -> TableReport:
    return TableReport("s", table, "person", status, "e", 1, groups, "fix", **extra)


def test_accepted_gap_file_names_registered_tables_and_has_reasons():
    from mlb_baseball.coverage import load_accepted_gaps

    tables = {d.table for d in DATASETS}
    entries = load_accepted_gaps()
    assert entries
    for entry in entries:
        assert entry.table in tables
        assert entry.reason and entry.owner and entry.max_missing > 0


def test_a_gap_within_its_accepted_ceiling_is_explained_and_above_it_is_not():
    from mlb_baseball.coverage import AcceptedGap

    accepted = [AcceptedGap("raw.x", "a", 5, "why", "owner")]
    assert not _report("missing", [Group("a", 10, 5)]).unexplained(accepted)
    assert _report("missing", [Group("a", 10, 4)]).unexplained(accepted)
    # a different group in the same table is still unexplained
    assert _report("missing", [Group("a", 10, 5), Group("b", 3, 2)]).unexplained(accepted)
    # a whole-table entry caps the table total
    whole = [AcceptedGap("raw.x", None, 6, "why", "owner")]
    assert not _report("missing", [Group("a", 10, 5), Group("b", 3, 2)]).unexplained(whole)


def test_an_empty_or_unmeasurable_table_is_never_accepted():
    from mlb_baseball.coverage import AcceptedGap

    whole = [AcceptedGap("raw.x", None, 10**9, "why", "owner")]
    for status in ("empty", "table_absent", "inputs_absent", "no_basis"):
        assert _report(status, []).unexplained(whole)
    assert not _report("complete", [Group("a", 1, 1)]).unexplained(whole)
