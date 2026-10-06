"""Registry and rendering contracts for `mlb coverage` that need no database."""

import re
from pathlib import Path

import pytest

from mlb_baseball import cli, coverage
from mlb_baseball.coverage.engine import TableReport
from mlb_baseball.coverage.model import Group
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
