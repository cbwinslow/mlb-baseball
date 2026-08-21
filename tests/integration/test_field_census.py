"""Real-Postgres coverage for the read-only source-field census."""

# ruff: noqa: E501

from mlb_baseball import field_census


def test_census_is_deterministic_and_does_not_mutate_raw(db_conn, tmp_path):
    with db_conn.cursor() as cur:
        cur.execute("CREATE TABLE raw.census_candidate (season integer, metric numeric)")
        cur.execute("INSERT INTO raw.census_candidate VALUES (2024, 1.5), (2025, NULL)")
    db_conn.commit()

    before = db_conn.execute("SELECT count(*) FROM raw.census_candidate").fetchone()
    first = field_census.collect(db_conn, exact=True)
    second = field_census.collect(db_conn, exact=True)
    after = db_conn.execute("SELECT count(*) FROM raw.census_candidate").fetchone()

    assert before == after == (2,)
    assert first == second
    candidate = next(
        field
        for field in first["fields"]
        if field["raw_relation"] == "raw.census_candidate" and field["field"] == "metric"
    )
    assert candidate["classification"] == "needs_research"
    assert candidate["null_count"] == 1
    assert candidate["null_fraction"] == 0.5
    assert candidate["distinct_count"] == 1
    assert candidate["season_min"] == "2024"
    assert candidate["season_max"] == "2025"

    json_path = tmp_path / "census.json"
    markdown_path = tmp_path / "census.md"
    field_census.write_outputs(first, json_path=json_path, markdown_path=markdown_path)
    assert json_path.read_text().endswith("\n")
    assert "Raw → core → gold field census" in markdown_path.read_text()

    db_conn.execute("DROP TABLE raw.census_candidate")
    db_conn.commit()


def test_census_classification_keeps_raw_only_data_distinct_from_candidates():
    assert field_census._classification("mlb_schedule", "game_id").classification == "canonical_core"
    assert field_census._classification("bref_war_batting", "war").classification == "existing_gold"
    assert field_census._classification("retrosheet_event", "_scope").classification == "raw_only_by_design"
    assert field_census._classification("bref_batting", "ops").classification == "raw_only_by_design"
    assert field_census._classification("mlb_probable", "pitcher_id").classification == "needs_research"
    assert field_census._classification("mlb_team_history", "id").classification == "unconformed_candidate"
    assert field_census._classification("statcast_pitch", "spin_rate_deprecated").classification == "invalid_or_low_value"
