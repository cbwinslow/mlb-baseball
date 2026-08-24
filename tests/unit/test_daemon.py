"""Unit tests for Daily Automation Daemon & Cache Warmer (CRON-01, ADR-142)."""

from mlb_baseball.daemon import (
    DailyAutomationDaemon,
    health_check,
)


def test_daemon_daily_cycle_execution():
    """Verify DailyAutomationDaemon executes pipeline, warms cache, and bakes vector assets."""
    daemon = DailyAutomationDaemon()

    summary = daemon.execute_daily_cycle(date_str="2026-08-24", skip_doctor=True)

    assert summary.pipeline_status == "SUCCESS"
    assert summary.pipeline_duration_s >= 0.0
    assert summary.visual_assets_baked == 2
    assert summary.cache_warming_time_ms >= 0.0


def test_cache_warmer_mock_pass():
    """Verify cache warming returns list of analytical serving marts."""
    daemon = DailyAutomationDaemon()
    warm_res = daemon.warm_serving_cache(conn=None)

    assert len(warm_res.views_warmed) == 5
    assert "serve.pitcher_arsenal" in warm_res.views_warmed
    assert "serve.ros_team_standings" in warm_res.views_warmed
    assert warm_res.status == "warm"


def test_daemon_health_check():
    """Verify daemon health check passes."""
    checks = health_check()
    assert len(checks) == 1
    assert checks[0].ok is True
    assert "Daemon cycle verified" in checks[0].detail
