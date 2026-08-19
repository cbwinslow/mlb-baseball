"""Phase 2 modeling (ADR-032/033/034, docs/RESEARCH.md). Deliberately not
a plugin framework -- features/elo/starter build up gold.game_feature's
columns, log5/elo/gbm are the models that consume them; this just calls
each directly, in order, inside one transaction. Extract real structure
once a piece actually needs something the others don't fit into this same
shape, not before -- same reasoning as this project's connector registry,
which came after multiple real connectors, not in anticipation of one.

backfill_outcomes lives here, not inside any one model, because it isn't
model-specific -- it fills in the actual result for *every* model's
predictions once a game is decided, regardless of which model made them.

gbm.train() is deliberately NOT called from run() -- training is a
distinct, occasional operation (see gbm.py's own docstring and ADR-033),
triggered separately via `mlb train`. run() (mlb predict) only ever loads
whatever model train() last saved -- which means gbm-v1 won't use the new
starter-quality columns until it's retrained against them (a real,
separate follow-up, not automatic just because the columns now exist).
"""

import psycopg

from mlb_baseball.db import get_connection
from mlb_baseball.health import (
    DAILY_FRESHNESS_THRESHOLD_MINUTES,
    Check,
    check_last_run,
    check_recent_run,
)
from mlb_baseball.ingest import track_run
from mlb_baseball.model import (
    bullpen,
    elo,
    evaluation,
    features,
    framing,
    gbm,
    log5,
    market,
    oaa,
    offense,
    park,
    speed,
    starter,
    starter_workload,
    team_rate,
    war,
)

SOURCE = "model"
FRESHNESS_THRESHOLD_MINUTES = DAILY_FRESHNESS_THRESHOLD_MINUTES


def backfill_outcomes(conn: psycopg.Connection) -> int:
    """Fills in actual_home_win for any gold.prediction row whose game is
    now final -- without this, prediction history never accumulates a
    calibration record (the whole reason gold.prediction exists, see
    ADR-032). Joined via game_pk, not game_id -- a prediction made while a
    game was still upcoming has no core.game row to key on until conform
    picks it up after the game finishes."""
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE gold.prediction p "
            "SET actual_home_win = (g.home_score > g.away_score) "
            "FROM gold.game_feature f "
            "JOIN core.game g ON g.id = f.game_id "
            "WHERE f.game_instance_key = p.game_instance_key "
            "  AND p.actual_home_win IS NULL "
            "  AND g.home_score IS NOT NULL AND g.away_score IS NOT NULL"
        )
        return cur.rowcount


def build_feature_stage(conn: psycopg.Connection) -> dict[str, int]:
    """Rebuild the audited base ``gold.game_feature`` family without predictions.

    This is deliberately connection-scoped and does not commit.  It lets
    :func:`run_features` expose a separately auditable CLI stage while
    preserving ``mlb predict``'s historic all-in-one transaction.
    """
    feature_count = features.build(conn, strict=True)
    return {"gold.game_feature": feature_count}


def run_features() -> dict[str, int]:
    """Run only the reusable feature stage, in one tracked transaction."""
    with (
        get_connection() as conn,
        track_run(conn, SOURCE, "features", workflow="exclusive") as result,
    ):
        counts = build_feature_stage(conn)
        conn.commit()
        result["rows"] = counts["gold.game_feature"]
    return counts


def enrich_feature_stage(conn: psycopg.Connection) -> dict[str, int]:
    """Repopulate every enrichment column on ``gold.game_feature`` after a
    base rebuild.

    ``features.build()`` (called by ``build_feature_stage()``) TRUNCATEs
    ``gold.game_feature`` and rebuilds only the base family (win%/Elo/
    outcome) -- every enrichment module here writes UPDATE statements
    against rows that already exist, so this must run strictly after
    ``build_feature_stage()``, never before or concurrently with it.

    Found missing from ``run()`` during PR review of the 2026-08-19
    production incident (see plans/PROGRESS.md "Production incident found
    and fixed" and issue #48): every enrichment module was run once by
    hand, but none was ever wired into the path `mlb predict` (this
    module's own ``run()``) actually takes -- the same path the daily cron
    (``scripts/mlb_daily_update.sh``, 06:00 UTC) calls every day. Without
    this, the next scheduled rebuild silently truncates every enrichment
    column back to NULL again, recurring indefinitely, not a one-time
    incident. Order matches the manual backfill script that fixed
    production the same day: park first (zero-leakage, no raw.retrosheet_*
    dependency), then every Retrosheet-derived module, live/upcoming/
    probable variants immediately after each historical path.
    """
    return {
        "gold.game_feature (park_factor)": park.compute(conn),
        "gold.game_feature (team_rate)": team_rate.compute(conn),
        "gold.game_feature (team_rate run environment)": team_rate.compute_run_environment(conn),
        "gold.game_feature (offense)": offense.compute(conn),
        "gold.game_feature (wrc_plus)": offense.compute_wrc_plus(conn),
        "gold.game_feature (offense live)": offense.compute_live(conn),
        "gold.game_feature (wrc_plus live)": offense.compute_wrc_plus_live(conn),
        "gold.game_feature (starter)": starter.compute(conn),
        "gold.game_feature (starter live)": starter.compute_live(conn),
        "gold.game_feature (starter probable)": starter.compute_probable(conn),
        "gold.game_feature (starter workload)": starter_workload.compute(conn),
        "gold.game_feature (starter workload live)": starter_workload.compute_live(conn),
        "gold.game_feature (starter workload probable)": starter_workload.compute_probable(conn),
        "gold.game_feature (bullpen)": bullpen.compute(conn),
        "gold.game_feature (bullpen live)": bullpen.compute_live(conn),
        "gold.game_feature (bullpen upcoming)": bullpen.compute_upcoming(conn),
        "gold.game_feature (oaa)": oaa.compute(conn),
        "gold.game_feature (speed)": speed.compute(conn),
        "gold.game_feature (framing)": framing.compute(conn),
        "gold.game_feature (war)": war.compute(conn),
    }


def run() -> dict[str, int]:
    """Build features, enrich them, derive sequential Elo, then write
    legacy predictions.

    ``mlb features`` is intentionally only the reusable, audited base feature
    stage.  Elo is not part of that base because it is model-specific and
    sequential.  The backwards-compatible ``mlb predict`` command does need
    it before the Elo and GBM predictors run, however.  Keeping the step here
    makes that dependency explicit and prevents a silently empty Elo output.

    ``enrich_feature_stage()`` runs here, not inside ``build_feature_stage()``
    -- ``mlb features`` (``run_features()``) stays scoped to exactly the base
    family it always has been (a separately auditable stage other tooling
    may call standalone); ``mlb predict`` is the one path the daily cron
    actually calls, so it's the one that must keep enrichment populated.
    """
    with (
        get_connection() as conn,
        track_run(conn, SOURCE, "bootstrap", workflow="exclusive") as result,
    ):
        feature_counts = build_feature_stage(conn)
        enrich_counts = enrich_feature_stage(conn)
        elo_rows = elo.compute_ratings(conn)
        # market.record() runs before backfill_outcomes(), not after --
        # unlike log5/elo/gbm's own predictions (made for still-upcoming
        # games, where actual_home_win is legitimately unknown yet), every
        # market prediction is for a game that's already decided by
        # construction (see market.py's own docstring). Recording it after
        # backfill_outcomes() would leave a real, already-known outcome
        # sitting NULL for a full extra cron cycle for no reason -- found
        # running this against production, not hypothetical.
        market_count = market.record(conn)
        backfilled = backfill_outcomes(conn)
        log5_count = log5.predict(conn)
        elo_count = elo.predict(conn)
        gbm_count = gbm.predict(conn)
        conn.commit()
        result["rows"] = (
            feature_counts["gold.game_feature"] + log5_count + elo_count + gbm_count + market_count
        )
    return {
        **feature_counts,
        **enrich_counts,
        "gold.prediction (log5)": log5_count,
        "gold.prediction (elo)": elo_count,
        "gold.prediction (gbm)": gbm_count,
        "gold.prediction (market)": market_count,
        "gold.prediction (outcomes backfilled)": backfilled,
        "gold.game_feature (Elo ratings)": elo_rows,
    }


def train() -> dict:
    # Training reads the rebuilt feature relation.  It must not observe a
    # concurrent TRUNCATE/rebuild half-way through a feature or predict run.
    with (
        get_connection() as conn,
        track_run(conn, SOURCE, "train", workflow="exclusive") as result,
    ):
        metrics = gbm.train(conn)
        result["rows"] = metrics["train_rows"]
    return metrics


def evaluate(model_versions: list[str], season: int, cutoff: str, bootstrap_samples: int) -> dict:
    # Evaluation joins predictions to feature/provenance state and has the
    # same consistency requirement as training.
    with (
        get_connection() as conn,
        track_run(conn, SOURCE, "evaluate", workflow="exclusive") as result,
    ):
        report = evaluation.evaluate(conn, model_versions, season, cutoff, bootstrap_samples)
        result["rows"] = report["common_games"]
    return report


def health_check() -> list[Check]:
    return [
        check_last_run(SOURCE),
        # mode="bootstrap" -- run()'s own track_run mode, confusingly named
        # but is in fact `mlb predict`, the daily-cron-scheduled one.
        # Unscoped, a manual run_features()/train()/evaluate() call (modes
        # "features"/"train"/"evaluate") would mask a genuinely stale daily
        # predict run -- the same blind spot this check exists to close.
        check_recent_run(SOURCE, FRESHNESS_THRESHOLD_MINUTES, mode="bootstrap"),
    ] + (
        features.health_check()
        + log5.health_check()
        + gbm.health_check()
        + starter.health_check()
        + park.health_check()
        + offense.health_check()
        + team_rate.health_check()
        + war.health_check()
        + bullpen.health_check()
        + oaa.health_check()
        + speed.health_check()
        + framing.health_check()
        + market.health_check()
        + starter_workload.health_check()
    )
