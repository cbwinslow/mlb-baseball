"""Pure logic — no database. TableStatusCollector's own DB access is a thin
wrapper over inventory.py (already integration-tested there), so it's
tested here with inventory.tables()/last_runs() monkeypatched rather than
a real connection."""

from mlb_baseball import inventory, progress_table
from mlb_baseball.progress_table import (
    AsciiBarStyle,
    BlockBarStyle,
    HasDataStrategy,
    RunStatusStrategy,
    SeasonCoverageStrategy,
    StatusTableReport,
    TableStatus,
    TableStatusCollector,
)


def test_is_populated_reflects_row_count():
    assert TableStatus(schema="raw", table="x", rows=5).is_populated is True
    assert TableStatus(schema="raw", table="x", rows=0).is_populated is False


def test_full_name_joins_schema_and_table():
    assert TableStatus(schema="raw", table="widgets", rows=0).full_name == "raw.widgets"


def test_has_data_strategy_is_binary():
    strategy = HasDataStrategy()
    assert strategy.compute(TableStatus(schema="raw", table="x", rows=1)) == 100.0
    assert strategy.compute(TableStatus(schema="raw", table="x", rows=0)) == 0.0


def test_run_status_strategy_uses_matching_source_status():
    status = TableStatus(
        schema="raw",
        table="retrosheet_event",
        rows=100,
        last_run={"source": "retrosheet_event", "status": "running"},
    )
    assert RunStatusStrategy().compute(status) == 50.0


def test_run_status_strategy_falls_back_to_has_data_when_source_unmatched():
    # core/gold tables never match a raw-source prefix -- must fall back
    # cleanly, not crash or silently report 0% for a populated table.
    status = TableStatus(schema="core", table="player", rows=42, last_run=None)
    assert RunStatusStrategy().compute(status) == 100.0


def test_run_status_strategy_prefers_the_longest_matching_source():
    # "retrosheet_event" and "retrosheet" both prefix-match -- must pick
    # the longer, more specific one, not whichever CONNECTORS happens to
    # iterate first.
    status = TableStatus(
        schema="raw",
        table="retrosheet_event",
        rows=10,
        last_run={"source": "retrosheet_event", "status": "failed"},
    )
    assert RunStatusStrategy().compute(status) == 0.0


def test_ascii_bar_style_fills_proportionally():
    rendered = AsciiBarStyle().render(50.0, width=10)
    assert rendered == "[#####-----]  50.0%"


def test_ascii_bar_style_clamps_out_of_range_percent():
    assert AsciiBarStyle().render(150.0, width=4) == "[####] 150.0%"
    assert AsciiBarStyle().render(-10.0, width=4) == "[----] -10.0%"


def test_block_bar_style_uses_unicode_blocks():
    rendered = BlockBarStyle().render(100.0, width=4)
    assert rendered == "████ 100.0%"


def test_report_renders_one_line_per_table_grouped_by_schema():
    statuses = [
        TableStatus(schema="raw", table="a", rows=5, percent=100.0),
        TableStatus(schema="gold", table="b", rows=0, percent=0.0),
    ]
    output = StatusTableReport(group_by_schema=True).render(statuses)

    assert "raw" in output
    assert "gold" in output
    assert "raw.a" in output
    assert "gold.b" in output


def test_report_populated_only_excludes_empty_tables():
    statuses = [
        TableStatus(schema="raw", table="has_rows", rows=5, percent=100.0),
        TableStatus(schema="raw", table="empty", rows=0, percent=0.0),
    ]
    output = StatusTableReport(populated_only=True).render(statuses)

    assert "raw.has_rows" in output
    assert "raw.empty" not in output


def test_report_handles_no_tables_without_crashing():
    assert StatusTableReport().render([]) == "No tables found."


def test_collector_builds_statuses_from_inventory_and_applies_strategy(monkeypatch):
    monkeypatch.setattr(
        inventory,
        "tables",
        lambda: [{"schema": "raw", "table": "lahman_batting", "rows": 7}],
    )
    monkeypatch.setattr(inventory, "last_runs", lambda: [])

    statuses = TableStatusCollector().collect()

    assert len(statuses) == 1
    assert statuses[0].full_name == "raw.lahman_batting"
    assert statuses[0].rows == 7
    assert statuses[0].percent == 100.0  # HasDataStrategy default, 7 rows -> populated


def test_collector_attaches_matching_last_run_by_source(monkeypatch):
    monkeypatch.setattr(
        inventory,
        "tables",
        lambda: [{"schema": "raw", "table": "lahman_batting", "rows": 7}],
    )
    monkeypatch.setattr(
        inventory,
        "last_runs",
        lambda: [{"source": "lahman", "status": "success", "mode": "bootstrap"}],
    )

    statuses = TableStatusCollector(progress_table.RunStatusStrategy()).collect()

    assert statuses[0].last_run is not None
    assert statuses[0].last_run["source"] == "lahman"
    assert statuses[0].percent == 100.0


def test_season_coverage_strategy_computes_a_real_fraction():
    # 10 of 20 possible years covered -- a genuine 50%, not a guess.
    status = TableStatus(
        schema="raw",
        table="statcast_pitch",
        rows=1,
        max_season=2026,
        first_year=2008,
        seasons_loaded=10,
    )
    assert SeasonCoverageStrategy(current_year=2027).compute(status) == 50.0


def test_season_coverage_strategy_falls_back_when_table_not_registered():
    status = TableStatus(schema="core", table="player", rows=42)  # no max_season/first_year
    assert SeasonCoverageStrategy(current_year=2026).compute(status) == 100.0


def test_season_coverage_strategy_clamps_to_100_when_fully_current():
    status = TableStatus(
        schema="raw",
        table="statcast_pitch",
        rows=1,
        max_season=2026,
        first_year=2008,
        seasons_loaded=19,
    )
    assert SeasonCoverageStrategy(current_year=2026).compute(status) == 100.0


def test_has_season_coverage_requires_first_year_and_exact_count():
    assert (
        TableStatus(schema="raw", table="x", rows=1, seasons_loaded=1).has_season_coverage is False
    )
    assert (
        TableStatus(schema="raw", table="x", rows=1, first_year=2008).has_season_coverage is False
    )
    assert (
        TableStatus(
            schema="raw", table="x", rows=1, first_year=2008, seasons_loaded=1
        ).has_season_coverage
        is True
    )


def test_estimated_total_rows_projects_from_observed_density():
    # 100 rows across 5 covered years (2008-2012) -> 20 rows/year, times
    # 19 total expected years (2008-2026) -> 380.
    status = TableStatus(
        schema="raw",
        table="statcast_pitch",
        rows=100,
        max_season=2012,
        first_year=2008,
        seasons_loaded=5,
    )
    assert status.estimated_total_rows(current_year=2026) == 380


def test_estimated_total_rows_none_without_season_coverage():
    status = TableStatus(schema="core", table="player", rows=100)
    assert status.estimated_total_rows(current_year=2026) is None


def test_estimated_total_rows_none_when_genuinely_empty():
    status = TableStatus(
        schema="raw",
        table="statcast_pitch",
        rows=0,
        max_season=2012,
        first_year=2008,
        seasons_loaded=5,
    )
    assert status.estimated_total_rows(current_year=2026) is None
