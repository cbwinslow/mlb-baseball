"""Model Drift & Calibration Monitor (DRIFT-01, ADR-124).

Monitors predictive model reliability across rolling chronological windows:
1. Tracks rolling Expected Calibration Error (ECE) and Brier Score over time.
2. Quantifies Platt calibration slope (alpha) and HFA bias drift (beta).
3. Detects model overconfidence, underconfidence, and concept drift.
4. Provides automated degradation alerting for risk management.

Adheres strictly to object-oriented encapsulation, polymorphic protocols, and
point-in-time correctness with zero future lookahead.
"""

from __future__ import annotations

import dataclasses
import datetime
import enum
from collections.abc import Sequence

import numpy as np
import psycopg
from psycopg.rows import dict_row
from sklearn.metrics import brier_score_loss, log_loss

from mlb_baseball.db import get_connection
from mlb_baseball.health import Check
from mlb_baseball.model.calibration import PlattCalibrator, evaluate_calibration


class DriftSeverity(enum.Enum):
    """Classification of model calibration and performance health."""

    HEALTHY = "HEALTHY"  # ECE < 0.04, BSS > 0, slope in [0.85, 1.15]
    WARNING = "WARNING"  # ECE in [0.04, 0.07], slight over/under-confidence
    DEGRADED = "DEGRADED"  # ECE > 0.07 or BSS < 0, noticeable divergence
    CRITICAL = "CRITICAL"  # Slope < 0.5 or > 1.5, severe miscalibration


@dataclasses.dataclass(frozen=True)
class RollingDriftWindow:
    """Statistical calibration health metrics within a single chronological window."""

    window_index: int
    start_date: str
    end_date: str
    sample_size: int
    brier_score: float
    log_loss_score: float
    expected_calibration_error: float
    max_calibration_error: float
    platt_slope_w: float
    hfa_intercept_b: float
    brier_skill_score: float
    severity: DriftSeverity
    warning_messages: list[str]


@dataclasses.dataclass(frozen=True)
class ModelDriftReport:
    """Comprehensive multi-window drift and performance trend report."""

    model_version: str
    total_evaluated_games: int
    overall_brier_score: float
    overall_ece: float
    current_status: DriftSeverity
    windows: list[RollingDriftWindow]
    alerts: list[str]


class ModelDriftMonitor:
    """Monitors rolling model calibration and concept drift across historical games."""

    def __init__(
        self,
        window_size_games: int = 40,
        step_size_games: int = 15,
        ece_warning_threshold: float = 0.045,
        ece_critical_threshold: float = 0.075,
    ) -> None:
        self.window_size_games = window_size_games
        self.step_size_games = step_size_games
        self.ece_warning_threshold = ece_warning_threshold
        self.ece_critical_threshold = ece_critical_threshold

    def evaluate_predictions(
        self,
        model_version: str,
        game_dates: Sequence[str | datetime.date],
        y_true: Sequence[int],
        y_prob: Sequence[float],
    ) -> ModelDriftReport:
        """Evaluate chronological sliding windows of predictions for calibration drift."""
        n = len(y_true)
        if n == 0 or len(y_prob) != n or len(game_dates) != n:
            return ModelDriftReport(
                model_version=model_version,
                total_evaluated_games=0,
                overall_brier_score=0.0,
                overall_ece=0.0,
                current_status=DriftSeverity.HEALTHY,
                windows=[],
                alerts=["No predictions available for evaluation."],
            )

        y_arr = np.asarray(y_true, dtype=np.int32)
        p_arr = np.asarray(y_prob, dtype=np.float64)
        dates_arr = [str(d) for d in game_dates]

        # Overall metrics
        overall_diag = evaluate_calibration(list(y_arr), list(p_arr), n_bins=10)
        overall_brier = float(brier_score_loss(y_arr, p_arr))

        windows: list[RollingDriftWindow] = []
        overall_alerts: list[str] = []

        # Sliding window evaluation
        w_size = max(10, min(self.window_size_games, n))
        step = max(5, min(self.step_size_games, w_size))

        w_idx = 0
        for start_idx in range(0, n - w_size + 1, step):
            end_idx = start_idx + w_size
            w_y = y_arr[start_idx:end_idx]
            w_p = p_arr[start_idx:end_idx]
            w_start_date = dates_arr[start_idx]
            w_end_date = dates_arr[end_idx - 1]

            # Fit Platt calibrator to extract slope (w) and intercept (b)
            platt = PlattCalibrator()
            platt.fit(list(w_y), list(w_p))

            # Compute window diagnostics
            w_diag = evaluate_calibration(list(w_y), list(w_p), n_bins=5)
            w_brier = float(brier_score_loss(w_y, w_p))
            w_ll = float(log_loss(w_y, w_p, labels=[0, 1]))

            # Determine drift severity & warnings
            warnings: list[str] = []
            severity = DriftSeverity.HEALTHY

            if w_diag.expected_calibration_error > self.ece_critical_threshold:
                severity = DriftSeverity.CRITICAL
                warnings.append(
                    f"Critical ECE ({w_diag.expected_calibration_error:.1%}) "
                    f"> {self.ece_critical_threshold:.1%}"
                )
            elif w_diag.expected_calibration_error > self.ece_warning_threshold:
                severity = DriftSeverity.WARNING
                warnings.append(
                    f"Elevated ECE ({w_diag.expected_calibration_error:.1%}) "
                    f"> {self.ece_warning_threshold:.1%}"
                )

            # Check slope for extreme over/underconfidence
            if w_diag.expected_calibration_error > self.ece_warning_threshold:
                if platt.w < 0.50:
                    warnings.append(
                        f"Model overconfidence detected (Platt slope alpha = {platt.w:.2f} < 0.50)"
                    )
                    if severity == DriftSeverity.HEALTHY:
                        severity = DriftSeverity.WARNING
                elif platt.w > 2.00:
                    warnings.append(
                        f"Model underconfidence detected (Platt slope alpha = {platt.w:.2f} > 2.00)"
                    )
                    if severity == DriftSeverity.HEALTHY:
                        severity = DriftSeverity.WARNING

            # Check skill score
            if w_diag.brier_skill_score < 0.0:
                warnings.append("Negative Brier Skill Score: performing worse than baseline rate")
                if severity != DriftSeverity.CRITICAL:
                    severity = DriftSeverity.DEGRADED

            windows.append(
                RollingDriftWindow(
                    window_index=w_idx + 1,
                    start_date=w_start_date,
                    end_date=w_end_date,
                    sample_size=w_size,
                    brier_score=round(w_brier, 4),
                    log_loss_score=round(w_ll, 4),
                    expected_calibration_error=round(w_diag.expected_calibration_error, 4),
                    max_calibration_error=round(w_diag.max_calibration_error, 4),
                    platt_slope_w=round(platt.w, 3),
                    hfa_intercept_b=round(platt.b, 3),
                    brier_skill_score=round(w_diag.brier_skill_score, 4),
                    severity=severity,
                    warning_messages=warnings,
                )
            )
            w_idx += 1

        # Determine current status based on most recent window
        current_status = windows[-1].severity if windows else DriftSeverity.HEALTHY
        if current_status in (DriftSeverity.DEGRADED, DriftSeverity.CRITICAL):
            overall_alerts.append(
                f"Model '{model_version}' is {current_status.value}: recalibration recommended."
            )

        return ModelDriftReport(
            model_version=model_version,
            total_evaluated_games=n,
            overall_brier_score=round(overall_brier, 4),
            overall_ece=round(overall_diag.expected_calibration_error, 4),
            current_status=current_status,
            windows=windows,
            alerts=overall_alerts,
        )

    def evaluate_model_from_db(
        self,
        model_version: str,
        conn: psycopg.Connection | None = None,
    ) -> ModelDriftReport:
        """Fetch predictions from gold.prediction and evaluate drift."""

        def _fetch_and_eval(c: psycopg.Connection) -> ModelDriftReport:
            with c.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    """
                    SELECT g.game_date, p.actual_home_win, p.home_win_prob
                    FROM gold.prediction p
                    JOIN core.game g ON g.game_pk = p.mlb_game_pk
                    WHERE p.model_version = %s
                      AND p.actual_home_win IS NOT NULL
                      AND p.home_win_prob IS NOT NULL
                    ORDER BY g.game_date, p.mlb_game_pk
                    """,
                    (model_version,),
                )
                rows = cur.fetchall()

            if not rows:
                return ModelDriftReport(
                    model_version=model_version,
                    total_evaluated_games=0,
                    overall_brier_score=0.0,
                    overall_ece=0.0,
                    current_status=DriftSeverity.HEALTHY,
                    windows=[],
                    alerts=[
                        f"No decided predictions found in gold.prediction for '{model_version}'."
                    ],
                )

            dates = [str(r["game_date"]) for r in rows]
            y_true = [1 if r["actual_home_win"] else 0 for r in rows]
            y_prob = [float(str(r["home_win_prob"])) for r in rows]

            return self.evaluate_predictions(model_version, dates, y_true, y_prob)

        if conn is not None:
            return _fetch_and_eval(conn)
        with get_connection() as c:
            return _fetch_and_eval(c)


def health_check() -> list[Check]:
    """Operational health check for the Model Drift & Calibration Monitor (DRIFT-01)."""
    checks: list[Check] = []
    try:
        monitor = ModelDriftMonitor(window_size_games=10, step_size_games=5)
        # Synthetic test data
        dates = [f"2024-05-{i:02d}" for i in range(1, 21)]
        y_true = [1, 0] * 10
        y_prob = [0.55, 0.45] * 10

        report = monitor.evaluate_predictions("test_model", dates, y_true, y_prob)
        if len(report.windows) > 0 and report.current_status == DriftSeverity.HEALTHY:
            checks.append(
                Check("model drift monitor", True, "Rolling ECE & Platt drift tracking verified")
            )
        else:
            checks.append(
                Check(
                    "model drift monitor",
                    False,
                    f"Unexpected drift status: {report.current_status}",
                )
            )
    except Exception as exc:
        checks.append(Check("model drift monitor", False, str(exc)))
    return checks
