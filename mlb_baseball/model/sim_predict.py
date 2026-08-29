"""Write matchup-Markov win probabilities for upcoming games (ADR-272).

Layer 2 of the prediction ladder: for each still-undecided
``gold.game_feature`` row, estimate home and away PA/state distributions
(this pitching side vs that batting side, Empirical Bayes toward league),
simulate games, and append ``markov-v1`` to ``gold.prediction``.

Scoped to upcoming games only — the same cheap daily window log5/Elo use.
Historical backfill is a separate command later, not this function.
"""

from __future__ import annotations

import hashlib
import random
from datetime import date
from decimal import Decimal

import psycopg

from mlb_baseball.db import fetch_one, get_connection
from mlb_baseball.health import Check
from mlb_baseball.model import markov, provenance

MODEL_VERSION = "markov-v1"
LOOKBACK_SEASONS = 2
SIM_GAMES = 5000
MIN_STARTER_PA = 50


def seasons_for(game_season: int) -> list[int]:
    """Inclusive lookback ending at the game's own season.

    A 2026 game uses 2025–2026. Retrosheet 2026 is empty today; the
    2025 slice still supplies a prior. ``before_date`` then drops any
    same-season games on or after the target.
    """
    if game_season < 1:
        raise markov.MarkovError(f"game_season must be positive, got {game_season}")
    start = game_season - LOOKBACK_SEASONS + 1
    return list(range(start, game_season + 1))


def rng_for(mlb_game_pk: str) -> random.Random:
    seed = int(hashlib.sha256(mlb_game_pk.encode()).hexdigest()[:16], 16)
    return random.Random(seed)


def _side_distribution(
    conn: psycopg.Connection,
    seasons: list[int],
    *,
    batting_team: str,
    pitching_team: str,
    pit_id: str | None,
    before_date: date,
    league: dict[markov.BaseOutState, dict[markov.Outcome, float]],
) -> dict[markov.BaseOutState, dict[markov.Outcome, float]]:
    if pit_id:
        _rows, n_pa = markov._fetch_matchup_transition_counts(
            conn,
            seasons,
            batting_team=batting_team,
            pitching_team=pitching_team,
            pit_id=pit_id,
            before_date=before_date,
        )
        if n_pa >= MIN_STARTER_PA:
            return markov.estimate_matchup_distribution(
                conn,
                seasons,
                batting_team=batting_team,
                pitching_team=pitching_team,
                pit_id=pit_id,
                before_date=before_date,
                league=league,
            )
    return markov.estimate_matchup_distribution(
        conn,
        seasons,
        batting_team=batting_team,
        pitching_team=pitching_team,
        before_date=before_date,
        league=league,
    )


def predict(conn: psycopg.Connection, *, n_games: int = SIM_GAMES) -> int:
    """Append one ``markov-v1`` snapshot per upcoming game.

    ``n_games`` is the Monte Carlo count per matchup (tests pass a small
    value). Missing Retrosheet tables, or a slate with no cutoff league
    prior, writes nothing rather than inventing a 0.5.
    """
    if n_games < 1:
        raise markov.MarkovError(f"n_games must be positive, got {n_games}")
    model_id = provenance.register_model(
        conn,
        name="markov",
        target="home_win",
        model_version=MODEL_VERSION,
        feature_set_version="game-feature-v1",
        status="candidate",
        parameters={
            "lookback_seasons": LOOKBACK_SEASONS,
            "sim_games": n_games,
            "prior_pa": markov.MATCHUP_PRIOR_PA,
            "min_starter_pa": MIN_STARTER_PA,
        },
    )
    data_cutoff, feature_snapshot_id = provenance.feature_snapshot(
        conn, where="home_win IS NULL AND mlb_game_pk IS NOT NULL"
    )
    run_id = provenance.start_run(
        conn,
        run_type="predict",
        model_id=model_id,
        data_cutoff=data_cutoff,
        source_snapshot=feature_snapshot_id,
        feature_snapshot_id=feature_snapshot_id,
    )
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT gf.mlb_game_pk, gf.game_instance_key, gf.season, gf.game_date, "
                "ht.retro_team_id, at.retro_team_id, "
                "hsp.retro_id, asp.retro_id "
                "FROM gold.game_feature gf "
                "JOIN core.team ht ON ht.id = gf.home_team_id "
                "JOIN core.team at ON at.id = gf.away_team_id "
                "LEFT JOIN core.player hsp ON hsp.id = gf.home_starter_id "
                "LEFT JOIN core.player asp ON asp.id = gf.away_starter_id "
                "WHERE gf.home_win IS NULL AND gf.mlb_game_pk IS NOT NULL"
            )
            slate = cur.fetchall()
        inserted = 0
        league_cache: dict[
            tuple[tuple[int, ...], date],
            dict[markov.BaseOutState, dict[markov.Outcome, float]],
        ] = {}
        predictions: list[tuple[object, ...]] = []
        for (
            mlb_game_pk,
            game_instance_key,
            season,
            game_date,
            home_team,
            away_team,
            home_starter,
            away_starter,
        ) in slate:
            seasons = seasons_for(int(season))
            cutoff = (
                game_date if isinstance(game_date, date) else date.fromisoformat(str(game_date))
            )
            cache_key = (tuple(seasons), cutoff)
            if cache_key not in league_cache:
                league_rows, _n = markov._fetch_matchup_transition_counts(
                    conn, seasons, before_date=cutoff
                )
                league_cache[cache_key] = (
                    markov.build_outcome_distribution(league_rows) if league_rows else {}
                )
            league = league_cache[cache_key]
            if not league:
                continue
            away_dist = _side_distribution(
                conn,
                seasons,
                batting_team=away_team,
                pitching_team=home_team,
                pit_id=home_starter,
                before_date=cutoff,
                league=league,
            )
            home_dist = _side_distribution(
                conn,
                seasons,
                batting_team=home_team,
                pitching_team=away_team,
                pit_id=away_starter,
                before_date=cutoff,
                league=league,
            )
            rate = markov.simulate_home_win_rate(
                away_dist, home_dist, rng_for(mlb_game_pk), n_games
            )
            predictions.append(
                (
                    mlb_game_pk,
                    game_instance_key,
                    MODEL_VERSION,
                    Decimal(str(round(rate, 6))),
                    model_id,
                    run_id,
                    data_cutoff,
                    feature_snapshot_id,
                )
            )
        if predictions:
            with conn.cursor() as cur:
                cur.executemany(
                    "INSERT INTO gold.prediction "
                    "(mlb_game_pk, game_instance_key, model_version, home_win_prob, "
                    "model_id, model_run_id, data_cutoff, feature_snapshot_id) "
                    "VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
                    predictions,
                )
            inserted = len(predictions)
        provenance.finish_run(conn, run_id)
        return inserted
    except Exception as error:
        provenance.finish_run(conn, run_id, error=error)
        raise


def health_check() -> list[Check]:
    with get_connection() as conn, conn.cursor() as cur:
        try:
            cur.execute(
                "SELECT count(*) FROM gold.game_feature "
                "WHERE home_win IS NULL AND mlb_game_pk IS NOT NULL"
            )
            (upcoming,) = fetch_one(cur)
            cur.execute(
                "SELECT count(DISTINCT p.mlb_game_pk) FROM gold.prediction p "
                "JOIN gold.game_feature f ON f.mlb_game_pk = p.mlb_game_pk "
                "WHERE f.home_win IS NULL AND p.model_version = %s",
                (MODEL_VERSION,),
            )
            (covered,) = fetch_one(cur)
        except psycopg.errors.UndefinedTable:
            conn.rollback()
            return [Check("markov-v1 upcoming", False, "gold tables missing")]
    return [
        Check(
            "markov-v1 upcoming",
            True,
            f"{covered}/{upcoming} upcoming games have a {MODEL_VERSION} row",
        )
    ]
