"""Game-grain evaluation for immutable prediction snapshots.

``gold.prediction`` intentionally keeps repeated snapshots.  This module
selects one snapshot per game and named pre-game cutoff before calculating
scores, so rerunning a model more often cannot inflate its sample size or
confidence.  Every comparison is restricted to the exact games shared by
all requested model versions.
"""

from __future__ import annotations

import math
import random
from collections.abc import Iterable, Sequence
from dataclasses import dataclass

import psycopg

from mlb_baseball.model import provenance


@dataclass(frozen=True)
class Prediction:
    game_instance_key: str
    model_version: str
    probability: float
    actual: bool


MetricValue = float | int | tuple[float, float]


_CUTOFF_SQL = {
    "open": ("", "ORDER BY p.generated_at ASC"),
    "24h": (
        "AND p.generated_at <= s.game_start - interval '24 hours'",
        "ORDER BY p.generated_at DESC",
    ),
    "6h": (
        "AND p.generated_at <= s.game_start - interval '6 hours'",
        "ORDER BY p.generated_at DESC",
    ),
    "close": ("", "ORDER BY p.generated_at DESC"),
}


def _selected_predictions(
    conn: psycopg.Connection,
    model_versions: Sequence[str],
    season: int,
    cutoff: str,
) -> list[Prediction]:
    """Return one eligible pre-game snapshot per game and model."""
    if cutoff not in _CUTOFF_SQL:
        raise ValueError(f"unknown cutoff {cutoff!r}; choose from {', '.join(_CUTOFF_SQL)}")
    if not model_versions:
        raise ValueError("at least one model version is required")

    cutoff_predicate, cutoff_order = _CUTOFF_SQL[cutoff]
    with conn.cursor() as cur:
        cur.execute(
            f"""
            WITH schedule AS (
                SELECT game_id,
                       format('mlb:%%s:%%s:%%s:%%s:%%s:%%s',
                           _season, game_date, COALESCE(NULLIF(game_num, ''), '1'),
                           home_id, away_id, game_id
                       ) AS game_instance_key,
                       min(NULLIF(game_datetime, '')::timestamptz) AS game_start
                FROM raw.mlb_schedule
                WHERE game_id IS NOT NULL AND NULLIF(game_datetime, '') IS NOT NULL
                GROUP BY game_id, _season, game_date, game_num, home_id, away_id
                HAVING count(DISTINCT NULLIF(game_datetime, '')) = 1
            ), instance_rows AS (
                SELECT game_instance_key, season, game_date
                FROM meta.game_instance
                UNION ALL
                SELECT f.game_instance_key, f.season, f.game_date
                FROM gold.game_feature f
                WHERE NOT EXISTS (
                    SELECT 1
                    FROM meta.game_instance i
                    WHERE i.game_instance_key = f.game_instance_key
                )
            ), instances AS (
                SELECT i.game_instance_key,
                       i.season,
                       -- Retrosheet's completed-game feed has no reliable
                       -- start timestamp.  Its game-date midnight boundary
                       -- is intentionally not used: a conservative next-day
                       -- cutoff excludes only impossible future snapshots,
                       -- while the report records that fallback in the
                       -- registry contract.
                       COALESCE(
                           s.game_start,
                           (i.game_date::timestamp AT TIME ZONE 'UTC') + interval '1 day'
                       ) AS game_start
                FROM instance_rows i
                LEFT JOIN schedule s ON s.game_instance_key = i.game_instance_key
                WHERE i.game_date IS NOT NULL
            ), eligible AS (
                SELECT p.game_instance_key,
                       p.model_version,
                       p.home_win_prob,
                       p.actual_home_win,
                       row_number() OVER (
                           PARTITION BY p.game_instance_key, p.model_version
                           {cutoff_order}
                       ) AS snapshot_rank
                FROM gold.prediction p
                JOIN instances s ON s.game_instance_key = p.game_instance_key
                WHERE p.model_version = ANY(%s)
                  AND s.season = %s
                  AND p.actual_home_win IS NOT NULL
                  AND p.generated_at < s.game_start
                  {cutoff_predicate}
            )
            SELECT game_instance_key, model_version, home_win_prob, actual_home_win
            FROM eligible
            WHERE snapshot_rank = 1
            ORDER BY game_instance_key, model_version
            """,
            (list(model_versions), season),
        )
        return [
            Prediction(str(game_instance_key), str(version), float(probability), bool(actual))
            for game_instance_key, version, probability, actual in cur.fetchall()
        ]


def _common_sample(
    rows: Iterable[Prediction], model_versions: Sequence[str]
) -> dict[str, list[Prediction]]:
    by_game: dict[str, dict[str, Prediction]] = {}
    for row in rows:
        by_game.setdefault(row.game_instance_key, {})[row.model_version] = row
    required = set(model_versions)
    common_games = sorted(game_pk for game_pk, values in by_game.items() if set(values) == required)
    return {
        version: [by_game[game_pk][version] for game_pk in common_games]
        for version in model_versions
    }


def _scores(rows: Sequence[Prediction]) -> dict[str, float | int]:
    if not rows:
        return {"games": 0, "log_loss": math.nan, "brier": math.nan, "accuracy": math.nan}
    epsilon = 1e-15
    probabilities = [min(max(row.probability, epsilon), 1 - epsilon) for row in rows]
    actuals = [1.0 if row.actual else 0.0 for row in rows]
    return {
        "games": len(rows),
        "log_loss": -sum(
            y * math.log(p) + (1 - y) * math.log(1 - p)
            for p, y in zip(probabilities, actuals, strict=True)
        )
        / len(rows),
        "brier": sum((p - y) ** 2 for p, y in zip(probabilities, actuals, strict=True)) / len(rows),
        "accuracy": sum((p >= 0.5) == bool(y) for p, y in zip(probabilities, actuals, strict=True))
        / len(rows),
    }


def _bootstrap_interval(
    rows: Sequence[Prediction], metric: str, samples: int, seed: int = 0
) -> tuple[float, float]:
    if not rows or samples <= 0:
        return math.nan, math.nan
    rng = random.Random(seed)
    estimates = sorted(
        float(_scores([rng.choice(rows) for _ in rows])[metric]) for _ in range(samples)
    )
    low = estimates[int(0.025 * (samples - 1))]
    high = estimates[int(0.975 * (samples - 1))]
    return low, high


def evaluate(
    conn: psycopg.Connection,
    model_versions: Sequence[str],
    season: int,
    cutoff: str = "close",
    bootstrap_samples: int = 1000,
) -> dict:
    """Evaluate requested models on their exact common game sample."""
    data_cutoff, feature_snapshot_id = provenance.feature_snapshot(conn)
    run_id = provenance.start_run(
        conn,
        run_type="evaluate",
        data_cutoff=data_cutoff,
        source_snapshot=feature_snapshot_id,
        prediction_cutoff=cutoff,
        feature_snapshot_id=feature_snapshot_id,
    )
    try:
        rows = _selected_predictions(conn, model_versions, season, cutoff)
        coverage = {
            version: sum(row.model_version == version for row in rows) for version in model_versions
        }
        common = _common_sample(rows, model_versions)
        metrics: dict[str, dict[str, MetricValue]] = {}
        for index, version in enumerate(model_versions):
            model_scores: dict[str, MetricValue] = {
                metric: value for metric, value in _scores(common[version]).items()
            }
            model_scores["log_loss_95ci"] = _bootstrap_interval(
                common[version], "log_loss", bootstrap_samples, seed=index
            )
            model_scores["brier_95ci"] = _bootstrap_interval(
                common[version], "brier", bootstrap_samples, seed=10_000 + index
            )
            metrics[version] = model_scores
        common_games = len(next(iter(common.values()), []))
        report = {
            "season": season,
            "cutoff": cutoff,
            "coverage": coverage,
            "common_games": common_games,
            "models": metrics,
        }
        report["evaluation_id"] = provenance.record_evaluation(
            conn,
            run_id=run_id,
            model_versions=list(model_versions),
            season=season,
            prediction_cutoff=cutoff,
            common_games=common_games,
            coverage=coverage,
            metrics=metrics,
        )
        provenance.finish_run(conn, run_id)
        return report
    except Exception as error:
        provenance.finish_run(conn, run_id, error=error)
        raise
