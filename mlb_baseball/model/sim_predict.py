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
import logging
import random
from datetime import date
from decimal import Decimal

import psycopg

from mlb_baseball.db import fetch_one, get_connection
from mlb_baseball.health import Check
from mlb_baseball.model import markov, provenance

logger = logging.getLogger(__name__)

MODEL_VERSION = "markov-v1"
LOOKBACK_SEASONS = 2
SIM_GAMES = 5000
MIN_STARTER_PA = 50

# Distribution keyed by (lookback seasons, cutoff date) — one league prior
# per point-in-time slice, reused across a slate. Callers own the dict.
Distribution = dict[markov.BaseOutState, dict[markov.Outcome, float]]
LeagueCache = dict[tuple[tuple[int, ...], date], Distribution]

# The eight per-game fields :func:`simulate_matchup` needs, in the order
# it (and ``predict``'s loop) unpacks them. Shared with the holdout eval
# so both resolve retro team codes / starter ids the same way. A caller
# that needs more columns SELECTs ``GAME_FIELDS + ", <extra>"`` and
# unpacks the extras after these eight.
GAME_FIELDS = (
    "gf.mlb_game_pk, gf.game_instance_key, gf.season, gf.game_date, "
    "ht.retro_team_id, at.retro_team_id, hsp.retro_id, asp.retro_id"
)
GAME_FROM = (
    " FROM gold.game_feature gf "
    "JOIN core.team ht ON ht.id = gf.home_team_id "
    "JOIN core.team at ON at.id = gf.away_team_id "
    "LEFT JOIN core.player hsp ON hsp.id = gf.home_starter_id "
    "LEFT JOIN core.player asp ON asp.id = gf.away_starter_id "
)


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


def _league_prior(
    conn: psycopg.Connection,
    cache: LeagueCache,
    seasons: list[int],
    cutoff: date,
) -> Distribution:
    """Cutoff-scoped league outcome distribution, memoized per
    ``(seasons, cutoff)`` so a full slate builds it once.

    Not split by batting half-inning: ADR-080's home/away per-PA
    scoring difference is a proven *league-level* effect, but scoping
    the sparse team/starter matchup sample to one half as well is an
    unproven refinement that halves the data. Deferred to a follow-up
    with a real holdout check (PRODUCT_DIRECTION Layer 2 "Next").
    """
    key = (tuple(seasons), cutoff)
    if key not in cache:
        rows, _n = markov.fetch_matchup_transition_counts(conn, seasons, before_date=cutoff)
        cache[key] = markov.build_outcome_distribution(rows) if rows else {}
    return cache[key]


def _side_distribution(
    conn: psycopg.Connection,
    seasons: list[int],
    *,
    batting_team: str,
    pitching_team: str,
    pit_id: str | None,
    before_date: date,
    league: Distribution,
) -> Distribution:
    """One batting side of one game: this team batting against the
    opposing starter, shrunk toward the same-cutoff league prior. Falls
    back to team-vs-team when the starter has faced this batting team
    for fewer than ``MIN_STARTER_PA`` plate appearances."""
    return markov.estimate_matchup_distribution(
        conn,
        seasons,
        batting_team=batting_team,
        pitching_team=pitching_team,
        pit_id=pit_id or None,
        pitcher_min_pa=MIN_STARTER_PA,
        before_date=before_date,
        league=league,
    )


def simulate_matchup(
    conn: psycopg.Connection,
    *,
    mlb_game_pk: str,
    season: int,
    game_date: date | str,
    home_team: str,
    away_team: str,
    home_starter: str | None,
    away_starter: str | None,
    league_cache: LeagueCache,
    n_games: int = SIM_GAMES,
) -> float | None:
    """Matchup-Markov home-win probability for one game.

    The per-game core of :func:`predict`, factored out so the holdout
    evaluation (`scripts/eval_markov_holdout.py`) scores the *same*
    computation `mlb predict` writes, not a re-derivation of it.

    Point-in-time: the cutoff is the game's own date, so only events
    strictly before it feed the league prior and the matchup samples.
    Returns ``None`` when Retrosheet has no cutoff league prior for that
    slice (too early a season) — the caller skips the game rather than
    inventing a 0.5. Seeded by ``mlb_game_pk`` so a rerun is identical.
    """
    if n_games < 1:
        raise markov.MarkovError(f"simulate_matchup: n_games must be positive, got {n_games}")
    seasons = seasons_for(season)
    cutoff = game_date if isinstance(game_date, date) else date.fromisoformat(game_date)
    league = _league_prior(conn, league_cache, seasons, cutoff)
    if not league:
        return None
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
    return markov.simulate_home_win_rate(away_dist, home_dist, rng_for(mlb_game_pk), n_games)


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
            # Recorded so a later change to the tie-breaking bound is visible
            # in run provenance (it affects the win probabilities).
            "max_innings": markov.SIM_MAX_INNINGS,
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
                "SELECT " + GAME_FIELDS + GAME_FROM + "WHERE gf.home_win IS NULL "
                "AND gf.mlb_game_pk IS NOT NULL "
                "AND gf.season IS NOT NULL AND gf.game_date IS NOT NULL"
            )
            slate = cur.fetchall()
        inserted = 0
        errored = 0
        league_cache: LeagueCache = {}
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
            try:
                rate = simulate_matchup(
                    conn,
                    mlb_game_pk=mlb_game_pk,
                    season=season,
                    game_date=game_date,
                    home_team=home_team,
                    away_team=away_team,
                    home_starter=home_starter,
                    away_starter=away_starter,
                    league_cache=league_cache,
                    n_games=n_games,
                )
            except markov.DegenerateSimulation as error:
                # ONE matchup whose estimated distribution genuinely cannot
                # break a tie (checked over the whole Monte Carlo sample, not
                # a single unlucky trial -- see simulate_home_win_rate) must
                # not cost the rest of the slate its markov-v1 rows, nor roll
                # back log5/Elo/GBM, which share this run's one transaction
                # (model/__init__.py). Skip-and-continue like the ``rate is
                # None`` case below; the count feeds the run status and the
                # health check so a systematic failure is still visible.
                #
                # A plain markov.MarkovError (e.g. "no observed outcomes for
                # state") is NOT caught here -- that is a data-contract
                # violation, not one bad matchup, and must fail the run loudly.
                logger.warning(
                    "markov-v1: skipping game %s -- degenerate distribution: %s",
                    mlb_game_pk,
                    error,
                )
                errored += 1
                continue
            if rate is None:
                continue
            predictions.append(
                (
                    mlb_game_pk,
                    game_instance_key,
                    MODEL_VERSION,
                    Decimal(str(rate)).quantize(Decimal("0.000001")),
                    model_id,
                    run_id,
                    data_cutoff,
                    feature_snapshot_id,
                )
            )
        # Log the skip count BEFORE the insert -- if executemany raises (a
        # constraint violation, say) the failure path still records how many
        # matchups were degenerate, not just the insert error.
        if errored:
            logger.warning(
                "markov-v1: %d of %d slate games skipped -- degenerate distribution",
                errored,
                len(slate),
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

    detail = f"{covered}/{upcoming} upcoming games have a {MODEL_VERSION} row"
    # A shortfall is expected in small numbers -- a matchup with no cutoff
    # league prior, or a genuinely degenerate distribution, is skipped by
    # design, and that legitimate skip rate varies with the calendar. Only
    # the unambiguous systematic failures fail this check: nothing produced
    # at all, or more than half the slate missing. (The old code returned a
    # pass even at zero coverage -- codex.)
    if upcoming == 0 or covered >= upcoming * 0.5:
        passed = True
        if 0 < covered < upcoming:
            detail += f" ({upcoming - covered} skipped -- no prior / degenerate)"
    elif covered == 0:
        passed = False
        detail += " -- markov-v1 produced NOTHING for this slate"
    else:
        passed = False
        detail += f" -- {upcoming - covered} of {upcoming} missing, a systematic failure"
    return [Check("markov-v1 upcoming", passed, detail)]
