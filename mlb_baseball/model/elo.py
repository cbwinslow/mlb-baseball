"""Elo -- the second classical baseline (ADR-032, docs/RESEARCH.md).
Unlike log5/Pythagenpat, a team's rating depends on every prior game's
*outcome*, not just a rolling aggregate computable independently per row --
that's a genuinely sequential, cross-team-dependent walk (each game
updates two teams' ratings, and later games depend on the current state
of every team, not just one team's own history), which window functions
don't fit well. compute_ratings() does this as one straightforward,
boring Python loop over gold.game_feature ordered by date instead of
forcing it into a recursive CTE.

Parameters, and which ones are actually sourced vs chosen:
- HOME_ADVANTAGE = 24: FiveThirtyEight's published MLB value (see
  docs/RESEARCH.md).
- MOV_MULTIPLIER: 538's general cross-sport margin-of-victory formula,
  used as published -- no MLB-specific tuning of its constants was found
  published anywhere, see docs/RESEARCH.md.
- K_FACTOR = 4 and REVERSION_WEIGHT = 0.25 are NOT sourced from anywhere
  -- 538 doesn't publish an MLB-specific K-factor, so this starts at a
  low value appropriate for a 162-game season (much slower-moving than
  the NBA/NFL K-factors 538 does publish) and 0.25 is a common,
  unremarkable season-transition reversion weight, not a derived number.
  Both are real, open, revisit-with-backtesting-evidence choices, not
  facts -- flagged here so nobody mistakes them for researched constants
  later.
"""

from decimal import Decimal

import psycopg

from mlb_baseball.model import provenance

MODEL_VERSION = "elo-v1"
STARTING_ELO = 1500.0
HOME_ADVANTAGE = 24.0
K_FACTOR = 4.0
REVERSION_WEIGHT = 0.25


def expected_win_prob(home_elo: float, away_elo: float) -> float:
    """Standard Elo win-probability formula, home-advantage-adjusted."""
    return 1.0 / (1.0 + 10 ** ((away_elo - (home_elo + HOME_ADVANTAGE)) / 400.0))


def _mov_multiplier(score_diff: int, winner_elo: float, loser_elo: float) -> float:
    elo_diff = max(winner_elo - loser_elo, 0.0)
    return ((abs(score_diff) + 3) ** 0.8) / (7.5 + 0.006 * elo_diff)


def compute_ratings(conn: psycopg.Connection) -> int:
    """Walks every regular-season row in gold.game_feature in true
    calendar order (across season boundaries, not partitioned by season
    the way win_pct is -- Elo ratings carry over between seasons, with
    reversion applied lazily the first time a team is seen in a new
    season) and fills in home_elo/away_elo. Every row -- decided or still
    upcoming -- gets the current pre-game rating; only decided games
    (home_win IS NOT NULL) actually update anyone's rating afterward."""
    with conn.cursor() as cur:
        # gold.game_feature's own home_run_diff/away_run_diff are each
        # team's *pre-game cumulative* rolling stat (see features.py) --
        # not this game's own margin. The actual score only exists on
        # core.game, joined here via game_id (populated for every decided
        # game; NULL for upcoming ones, where score is never used below
        # anyway since home_win is also NULL for those).
        #
        # Ordered by (game_date, id) -- gold.game_feature has no game_number
        # column, so a doubleheader's two games can land in either order
        # here. Accepted as-is: it only affects which of that same day's two
        # games updates a team's rating first, a negligible, self-correcting
        # effect on the overall rating trajectory -- not worth a schema
        # change to fix.
        cur.execute(
            "SELECT gf.id, gf.season, gf.home_team_id, gf.away_team_id, gf.home_win, "
            "g.home_score, g.away_score "
            "FROM gold.game_feature gf "
            "LEFT JOIN core.game g ON g.id = gf.game_id "
            "ORDER BY gf.game_date, gf.id"
        )
        rows = cur.fetchall()

        ratings: dict[int, float] = {}
        rating_season: dict[int, int] = {}
        updates: list[tuple[float, float, int]] = []

        for game_id, season, home_id, away_id, home_win, home_score, away_score in rows:
            for team_id in (home_id, away_id):
                if rating_season.get(team_id) not in (None, season):
                    ratings[team_id] = (
                        ratings[team_id] * (1 - REVERSION_WEIGHT) + STARTING_ELO * REVERSION_WEIGHT
                    )
                rating_season[team_id] = season

            home_elo = ratings.get(home_id, STARTING_ELO)
            away_elo = ratings.get(away_id, STARTING_ELO)
            updates.append((home_elo, away_elo, game_id))

            if home_win is None:
                continue
            home_score_diff = int(home_score) - int(away_score)
            expected_home = expected_win_prob(home_elo, away_elo)
            if home_win:
                mult = _mov_multiplier(home_score_diff, home_elo + HOME_ADVANTAGE, away_elo)
                ratings[home_id] = home_elo + K_FACTOR * mult * (1 - expected_home)
                ratings[away_id] = away_elo + K_FACTOR * mult * (expected_home - 1)
            else:
                mult = _mov_multiplier(home_score_diff, away_elo, home_elo + HOME_ADVANTAGE)
                ratings[home_id] = home_elo + K_FACTOR * mult * (0 - expected_home)
                ratings[away_id] = away_elo + K_FACTOR * mult * (expected_home - 0)

        cur.executemany(
            "UPDATE gold.game_feature SET home_elo = %s, away_elo = %s WHERE id = %s",
            updates,
        )
        return len(updates)


def predict(conn: psycopg.Connection) -> int:
    """Same scope as log5.predict() -- only games not yet decided, only
    once both teams have a real (non-starting-default) rating recorded.
    Ratings are floats in Python but numeric in Postgres; the WHERE
    clause below only needs home_elo/away_elo to be present, the actual
    probability computation happens in Python via expected_win_prob()."""
    model_id = provenance.register_model(
        conn,
        name="elo",
        target="home_win",
        model_version=MODEL_VERSION,
        feature_set_version="game-feature-v1",
        status="baseline",
        parameters={"k_factor": K_FACTOR, "home_advantage": HOME_ADVANTAGE},
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
                "SELECT id, mlb_game_pk, home_elo, away_elo FROM gold.game_feature "
                "WHERE home_win IS NULL AND mlb_game_pk IS NOT NULL "
                "AND home_elo IS NOT NULL AND away_elo IS NOT NULL"
            )
            rows = cur.fetchall()
        predictions = []
        for _, mlb_game_pk, home_elo, away_elo in rows:
            prob = expected_win_prob(float(home_elo), float(away_elo))
            predictions.append(
                (
                    mlb_game_pk,
                    MODEL_VERSION,
                    Decimal(str(prob)),
                    model_id,
                    run_id,
                    data_cutoff,
                    feature_snapshot_id,
                )
            )
        with conn.cursor() as cur:
            cur.executemany(
                "INSERT INTO gold.prediction "
                "(mlb_game_pk, model_version, home_win_prob, model_id, model_run_id, "
                "data_cutoff, feature_snapshot_id) VALUES (%s, %s, %s, %s, %s, %s, %s)",
                predictions,
            )
        provenance.finish_run(conn, run_id)
        return len(predictions)
    except Exception as error:
        provenance.finish_run(conn, run_id, error=error)
        raise
