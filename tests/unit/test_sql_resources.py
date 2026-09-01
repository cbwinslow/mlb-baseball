import pytest

from mlb_baseball.sql import read_sql


def test_reads_named_park_factor_transformation():
    sql = read_sql("park_factor_update.sql")

    assert "UPDATE gold.game_feature" in sql
    assert "%(trailing_seasons)s" in sql


def test_reads_named_venue_conformance_transformations():
    assert "INSERT INTO core.venue" in read_sql("conform_venue_insert.sql")
    assert "UPDATE core.venue" in read_sql("conform_venue_enrich.sql")


def test_reads_named_player_conformance_transformation():
    assert "INSERT INTO core.player" in read_sql("conform_player_insert.sql")


def test_reads_named_team_conformance_transformation():
    sql = read_sql("conform_team_insert.sql")

    assert "INSERT INTO core.team" in sql
    assert "THEN 9999" in sql


def test_reads_named_team_speed_transformation():
    assert "UPDATE gold.game_feature" in read_sql("team_speed_update.sql")


def test_reads_named_team_oaa_transformation():
    assert "UPDATE gold.game_feature" in read_sql("team_oaa_update.sql")


def test_reads_named_team_framing_transformation():
    assert "UPDATE gold.game_feature" in read_sql("team_framing_update.sql")


def test_reads_named_team_war_transformation():
    assert "UPDATE gold.game_feature" in read_sql("team_war_update.sql")


def test_reads_named_game_feature_rebuild_transformation():
    sql = read_sql("game_feature_rebuild.sql")

    assert "INSERT INTO gold.game_feature" in sql
    assert "feature_cutoff_at" in sql
    assert "raw.mlb_schedule" in sql


def test_reads_named_markov_matchup_transition_counts():
    sql = read_sql("markov_transition_counts_matchup.sql")

    assert "gi.hometeam" in sql
    assert "gi.visteam" in sql
    assert "resp_pit_id" in sql
    assert "exclude_game_id" in sql
    assert "before_date" in sql
    assert "n_pa" in sql
    assert "bat_event_fl" in sql


def test_reads_named_market_prediction_transformations():
    assert "sportsmarkettype = 'moneyline'" in read_sql("market_polymarket_prediction_insert.sql")
    assert "m.source = 'kalshi'" in read_sql("market_kalshi_prediction_insert.sql")
    upcoming = read_sql("market_upcoming_games.sql")
    assert "home_win IS NULL" in upcoming
    assert "raw.mlb_schedule" in upcoming


def test_reads_named_retrosheet_woba_transformation():
    assert "UPDATE gold.game_feature" in read_sql("team_woba_retrosheet_update.sql")


def test_reads_named_retrosheet_wrc_plus_transformation():
    assert "home_wrc_plus" in read_sql("team_wrc_plus_retrosheet_update.sql")


def test_reads_named_live_wrc_plus_transformation():
    assert "home_wrc_plus" in read_sql("team_wrc_plus_live_update.sql")


def test_reads_named_live_woba_transformation():
    assert "home_woba" in read_sql("team_woba_live_update.sql")


def test_reads_named_retrosheet_starter_transformation():
    assert "home_starter_era" in read_sql("team_starter_retrosheet_update.sql")


def test_reads_named_retrosheet_bullpen_transformation():
    sql = read_sql("team_bullpen_retrosheet_update.sql")
    assert "UPDATE gold.game_feature" in sql
    assert "%(fip_constant)s" in sql
    assert "%(fatigue_days)s" in sql
    assert "home_bullpen_fatigue" in sql


def test_reads_named_live_bullpen_transformation():
    sql = read_sql("team_bullpen_live_update.sql")
    assert "UPDATE gold.game_feature" in sql
    assert "%(fip_constant)s" in sql
    assert "%(fatigue_days)s" in sql
    assert "home_bullpen_fatigue" in sql
    assert "WHERE f.game_id = rg.game_id AND f.home_bullpen_fip IS NULL" in sql


def test_reads_named_upcoming_bullpen_transformation():
    sql = read_sql("team_bullpen_upcoming_update.sql")
    assert "UPDATE gold.game_feature" in sql
    assert "%(fip_constant)s" in sql
    assert "%(fatigue_days)s" in sql
    assert "home_bullpen_fatigue" in sql
    assert "r.game_date < t.game_date" in sql
    assert "r.game_date >= t.game_date - %(fatigue_days)s" in sql
    assert (
        "WHERE f.home_win IS NULL AND f.mlb_game_pk IS NOT NULL AND f.home_bullpen_fip IS NULL"
        in sql
    )


def test_reads_named_live_starter_transformation():
    assert "home_starter_era" in read_sql("team_starter_live_update.sql")


def test_reads_named_probable_starter_transformation():
    sql = read_sql("team_starter_probable_update.sql")
    assert "latest_probable" in sql
    assert "UPDATE gold.game_feature" in sql
    assert "%(fip_constant)s" in sql


@pytest.mark.parametrize("name", ["../secret.sql", "subdir/query.sql", ".hidden.sql"])
def test_rejects_non_resource_sql_names(name):
    with pytest.raises(ValueError, match="invalid SQL resource"):
        read_sql(name)
