"""Unit tests for Model Drift & Calibration Tracking Monitor (DRIFT-01, ADR-124)."""

from unittest.mock import MagicMock

from mlb_baseball.model.drift import (
    DriftSeverity,
    ModelDriftMonitor,
    health_check,
)


def test_model_drift_monitor_healthy_series():
    """Verify ModelDriftMonitor classifies well-calibrated sequence as HEALTHY."""
    monitor = ModelDriftMonitor(window_size_games=20, step_size_games=10)

    # 40 games where 60% probability has 60% empirical wins and 40% has 40% empirical wins
    dates = [f"2024-06-{i:02d}" for i in range(1, 41)]
    # 20 games with p=0.60 (12 wins, 8 losses) and 20 games with p=0.40 (8 wins, 12 losses)
    y_true = ([1] * 6 + [0] * 4 + [1] * 4 + [0] * 6) * 2
    y_prob = ([0.60] * 10 + [0.40] * 10) * 2

    report = monitor.evaluate_predictions("gbm-v2", dates, y_true, y_prob)

    assert report.total_evaluated_games == 40
    assert len(report.windows) >= 2
    assert report.current_status == DriftSeverity.HEALTHY
    assert report.overall_ece < 0.05
    for w in report.windows:
        assert w.sample_size == 20
        assert w.expected_calibration_error < 0.06


def test_model_drift_monitor_detects_overconfidence_and_degradation():
    """Verify ModelDriftMonitor detects extreme overconfidence."""
    monitor = ModelDriftMonitor(
        window_size_games=20,
        step_size_games=10,
        ece_warning_threshold=0.04,
        ece_critical_threshold=0.08,
    )

    # 30 games with 50/50 outcomes but overconfident predictions (p=0.90, 0.10)
    dates = [f"2024-07-{i:02d}" for i in range(1, 31)]
    y_true = [1, 0] * 15
    y_prob = [0.90, 0.10] * 15

    report = monitor.evaluate_predictions("overconfident_model", dates, y_true, y_prob)

    assert report.current_status in (
        DriftSeverity.DEGRADED,
        DriftSeverity.CRITICAL,
        DriftSeverity.WARNING,
    )
    assert any(
        "overconfidence" in msg.lower() or "ece" in msg.lower()
        for w in report.windows
        for msg in w.warning_messages
    )


def test_model_drift_monitor_with_mock_db():
    """Verify evaluate_model_from_db executes query and processes rows cleanly."""
    mock_conn = MagicMock()
    mock_cur = MagicMock()
    mock_conn.cursor.return_value.__enter__.return_value = mock_cur

    mock_rows = [
        {"game_date": "2024-05-01", "actual_home_win": True, "home_win_prob": 0.55},
        {"game_date": "2024-05-02", "actual_home_win": False, "home_win_prob": 0.45},
        {"game_date": "2024-05-03", "actual_home_win": True, "home_win_prob": 0.60},
        {"game_date": "2024-05-04", "actual_home_win": False, "home_win_prob": 0.40},
    ]
    mock_cur.fetchall.return_value = mock_rows

    monitor = ModelDriftMonitor(window_size_games=4, step_size_games=2)
    report = monitor.evaluate_model_from_db("log5-v1", conn=mock_conn)

    assert report.model_version == "log5-v1"
    assert report.total_evaluated_games == 4


def test_drift_health_check():
    """Verify drift monitor health check passes."""
    checks = health_check()
    assert len(checks) == 1
    assert checks[0].ok is True
    assert "Rolling ECE" in checks[0].detail
