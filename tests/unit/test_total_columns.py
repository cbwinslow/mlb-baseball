"""Pure-logic coverage for mlb_baseball.model.total's small helpers --
the DB-facing train()/predict()/backfill_outcomes() are integration-tested
against a real database in tests/integration/test_model_total.py, matching
this project's own "mock the network, not the database" testing discipline
(CLAUDE.md "Testing").
"""

import math

from mlb_baseball.model import total


def test_feature_columns_is_required_plus_optional_with_no_overlap():
    assert total.FEATURE_COLUMNS == total.REQUIRED_COLUMNS + total.OPTIONAL_COLUMNS
    assert len(set(total.FEATURE_COLUMNS)) == len(total.FEATURE_COLUMNS)


def test_win_loss_columns_deliberately_excluded():
    # Confirmed via real-data correlation against total runs (see this
    # module's own docstring / docs/RESEARCH.md) -- these carry no
    # consistent-sign signal for a run-total target, unlike win/loss.
    excluded = {
        "home_win_pct", "away_win_pct", "home_win_pct_10", "away_win_pct_10",
        "home_run_diff", "away_run_diff", "home_pyth_wpct", "away_pyth_wpct",
        "home_elo", "away_elo", "home_oaa_prior", "away_oaa_prior",
        "home_speed_prior", "away_speed_prior", "home_framing_prior",
        "away_framing_prior", "home_war_prior", "away_war_prior",
        "temp_f", "wind_speed_mph", "wind_dir", "sky", "precip",
    }
    assert excluded.isdisjoint(total.FEATURE_COLUMNS)


def test_required_not_null_sql_ands_every_required_column():
    sql = total._required_not_null_sql()
    assert sql == "f.park_factor IS NOT NULL"


def test_feature_columns_sql_prefixes_every_column_with_alias():
    sql = total._feature_columns_sql()
    columns = sql.split(", ")
    assert len(columns) == len(total.FEATURE_COLUMNS)
    assert columns == [f"f.{c}" for c in total.FEATURE_COLUMNS]


def test_to_float_row_converts_none_to_nan_not_a_crash():
    row = total._to_float_row((1, None, 3.5, None))
    assert row[0] == 1.0
    assert math.isnan(row[1])
    assert row[2] == 3.5
    assert math.isnan(row[3])


def test_train_sql_template_formats_without_error():
    # Regression guard for the {placeholder} shape -- a typo'd or missing
    # format key here would only surface at DB-call time otherwise (and
    # only if that exact code path happened to run), not at import time.
    sql = total._TRAIN_SQL_TEMPLATE.format(
        needed_seasons_sql="SELECT 1",
        columns=total._feature_columns_sql(),
        required_not_null=total._required_not_null_sql(),
        season_filter="f.season <= 2023",
    )
    assert "gold.game_feature" in sql
    assert "baseline_total" in sql


def test_predict_sql_template_formats_without_error():
    sql = total._PREDICT_SQL_TEMPLATE.format(
        needed_seasons_sql="SELECT 1",
        columns=total._feature_columns_sql(),
        required_not_null=total._required_not_null_sql(),
    )
    assert "home_win IS NULL" in sql
    assert "baseline_total" in sql
