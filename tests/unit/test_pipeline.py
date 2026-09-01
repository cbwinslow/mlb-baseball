"""Unit tests for Master End-to-End Daily Pipeline (PIPE-02, ADR-130)."""

from mlb_baseball.pipeline import MasterDailyPipeline, health_check


def test_master_daily_pipeline_execution():
    """Verify MasterDailyPipeline executes full 8 phases cleanly and produces complete report."""
    pipeline = MasterDailyPipeline(run_preflight_doctor=False)
    report = pipeline.execute_daily_cycle(
        target_date="2026-08-24", n_sims=500, bankroll_usd=10000.0
    )

    assert report.overall_success is True
    assert report.target_date == "2026-08-24"
    assert len(report.phases) == 8
    assert report.total_duration_seconds > 0.0

    phase_names = [p.phase_name for p in report.phases]
    assert any("Stacking" in name for name in phase_names)
    assert any("Stuff+" in name for name in phase_names)
    assert any("KDE" in name for name in phase_names)
    assert any("SGP" in name for name in phase_names)
    assert any("Kelly" in name for name in phase_names)
    assert any("Export" in name for name in phase_names)


def test_pipeline_health_check():
    """Verify master pipeline health check passes."""
    checks = health_check()
    assert len(checks) == 1
    assert checks[0].ok is True
    assert "Full 8-phase execution verified" in checks[0].detail
