"""End-to-end plumbing for scripts/eval_markov_holdout.py. Uses mlb_test.

The script is not a package module, so it is loaded by path (same
pattern as tests/unit/test_verify_markov_calibration.py).
"""

import importlib.util
from pathlib import Path

import pytest

from mlb_baseball.model.evaluation import _common_sample, _scores, _selected_predictions

_SCRIPT_PATH = Path(__file__).parents[2] / "scripts" / "eval_markov_holdout.py"
_spec = importlib.util.spec_from_file_location("eval_markov_holdout", _SCRIPT_PATH)
assert _spec is not None and _spec.loader is not None
eval_markov_holdout = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(eval_markov_holdout)


def _reset(db_conn):
    db_conn.rollback()
    with db_conn.cursor() as cur:
        cur.execute("DROP TABLE IF EXISTS raw.retrosheet_event")
        cur.execute("DROP TABLE IF EXISTS raw.retrosheet_gameinfo")
        cur.execute("DELETE FROM gold.prediction")
        cur.execute("DELETE FROM gold.game_feature")
        cur.execute("DELETE FROM meta.game_instance")
        cur.execute("DELETE FROM core.player")
        cur.execute("DELETE FROM core.team")
    db_conn.commit()


@pytest.fixture(autouse=True)
def _clean(db_conn):
    _reset(db_conn)
    yield
    _reset(db_conn)


def _seed(db_conn):
    """One completed 2024 game (ATL home, beat NYA), a pre-2024 Retrosheet
    game to feed the cutoff league prior, and a stored elo-v1 snapshot."""
    with db_conn.cursor() as cur:
        cur.execute(
            "CREATE TABLE raw.retrosheet_event ("
            "game_id text, inn_ct text, bat_home_id text, outs_ct text, "
            "event_outs_ct text, event_cd text, base1_run_id text, base2_run_id text, "
            "base3_run_id text, bat_dest_id text, run1_dest_id text, run2_dest_id text, "
            "run3_dest_id text, resp_pit_id text, bat_event_fl text)"
        )
        cur.execute(
            "CREATE TABLE raw.retrosheet_gameinfo ("
            "gid text, gametype text, _season text, visteam text, hometeam text, date text)"
        )
        cur.execute(
            "INSERT INTO raw.retrosheet_gameinfo "
            "(gid, gametype, _season, visteam, hometeam, date) "
            "VALUES ('NYA202304010', 'regular', '2023', 'ATL', 'NYA', '20230401')"
        )
        for bat_home_id, bat_dest, event_cd in (("0", "4", "23"), ("1", "0", "2")):
            cur.execute(
                "INSERT INTO raw.retrosheet_event "
                "(game_id, inn_ct, bat_home_id, outs_ct, event_outs_ct, event_cd, "
                "bat_dest_id, run1_dest_id, run2_dest_id, run3_dest_id, bat_event_fl) "
                "VALUES ('NYA202304010', '1', %s, '0', '3', %s, %s, '0', '0', '0', 'T')",
                (bat_home_id, event_cd, bat_dest),
            )
        cur.execute(
            "INSERT INTO core.team "
            "(retro_team_id, city, nickname, first_year, last_year, mlb_team_id) "
            "VALUES ('ATL', 'Atlanta', 'Braves', 1966, 2025, 144), "
            "('NYA', 'New York', 'Yankees', 1913, 2025, 147) RETURNING id, retro_team_id"
        )
        teams = {retro: tid for tid, retro in cur.fetchall()}
        cur.execute(
            "INSERT INTO gold.game_feature "
            "(mlb_game_pk, game_instance_key, season, game_date, "
            "home_team_id, away_team_id, home_win) "
            "VALUES ('718100', 'mlb:718100', 2024, '2024-07-01', %s, %s, TRUE)",
            (teams["ATL"], teams["NYA"]),
        )
        cur.execute(
            "INSERT INTO gold.prediction "
            "(mlb_game_pk, game_instance_key, model_version, generated_at, "
            "home_win_prob, actual_home_win) "
            "VALUES ('718100', 'mlb:718100', 'elo-v1', '2024-07-01T12:00:00Z', 0.55, TRUE)"
        )
    db_conn.commit()


def test_completed_games_returns_the_holdout_season_row(db_conn):
    _seed(db_conn)
    games = eval_markov_holdout._completed_games(db_conn, 2024, limit=0)
    assert len(games) == 1
    assert games[0][0] == "718100"  # mlb_game_pk
    assert games[0][-1] is True  # home_win

    assert eval_markov_holdout._completed_games(db_conn, 2023, limit=0) == []


def test_markov_predictions_scores_the_game_and_pairs_with_elo(db_conn):
    _seed(db_conn)
    games = eval_markov_holdout._completed_games(db_conn, 2024, limit=0)
    markov_rows, skipped, degenerate = eval_markov_holdout._markov_predictions(
        db_conn, games, 25, use_starters=False
    )

    assert skipped == 0
    assert degenerate == 0
    assert len(markov_rows) == 1
    row = markov_rows[0]
    assert row.model_version == "markov-v1"
    assert row.game_instance_key == "mlb:718100"
    assert row.actual is True
    assert 0.0 <= row.probability <= 1.0

    stored = _selected_predictions(db_conn, ["elo-v1"], 2024, "close")
    pair = _common_sample(markov_rows + stored, ["markov-v1", "elo-v1"])
    assert len(pair["markov-v1"]) == 1
    assert len(pair["elo-v1"]) == 1
    assert _scores(pair["markov-v1"])["log_loss"] is not None
    assert _scores(pair["elo-v1"])["log_loss"] is not None


def test_markov_predictions_skips_when_no_cutoff_league_prior(db_conn):
    _seed(db_conn)
    # A 2019 holdout: lookback is 2018-2019, the only Retrosheet game is
    # 2023, so seasons filter leaves no rows -> no league prior -> skipped.
    with db_conn.cursor() as cur:
        cur.execute("UPDATE gold.game_feature SET season = 2019, game_date = '2019-07-01'")
    db_conn.commit()
    games = eval_markov_holdout._completed_games(db_conn, 2019, limit=0)
    markov_rows, skipped, degenerate = eval_markov_holdout._markov_predictions(
        db_conn, games, 25, use_starters=False
    )
    assert markov_rows == []
    assert skipped == 1
    assert degenerate == 0


def test_markov_predictions_excludes_a_degenerate_game_instead_of_crashing(db_conn, monkeypatch):
    """A game whose recomputed distribution can't resolve a tie raises
    MarkovError inside simulate_matchup; the harness must count it as
    degenerate and keep going, not abort the whole evaluation."""
    _seed(db_conn)
    games = eval_markov_holdout._completed_games(db_conn, 2024, limit=0)

    def _boom(*_args, **_kwargs):
        raise eval_markov_holdout.markov.MarkovError(
            "game still tied after 30 innings -- the distribution may be degenerate"
        )

    monkeypatch.setattr(eval_markov_holdout.sim_predict, "simulate_matchup", _boom)
    markov_rows, skipped, degenerate = eval_markov_holdout._markov_predictions(
        db_conn, games, 25, use_starters=False
    )
    assert markov_rows == []
    assert skipped == 0
    assert degenerate == 1


def test_markov_predictions_reraises_a_non_degenerate_markov_error(db_conn, monkeypatch):
    """A MarkovError that is NOT the tie/degenerate case (e.g. a bad
    parameter) is a harness bug, not a per-game model failure -- it must
    propagate, not be silently counted as a degenerate game."""
    _seed(db_conn)
    games = eval_markov_holdout._completed_games(db_conn, 2024, limit=0)

    def _boom(*_args, **_kwargs):
        raise eval_markov_holdout.markov.MarkovError("n_games must be positive, got 0")

    monkeypatch.setattr(eval_markov_holdout.sim_predict, "simulate_matchup", _boom)
    with pytest.raises(eval_markov_holdout.markov.MarkovError, match="n_games must be positive"):
        eval_markov_holdout._markov_predictions(db_conn, games, 25, use_starters=False)
