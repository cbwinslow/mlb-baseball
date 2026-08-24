"""Unit tests for operational health checks in doctor suite (DOCTOR-01, ADR-114)."""

from mlb_baseball.model import portfolio, props, season, simulate


def test_simulate_health_check():
    """Verify simulate engine health check returns clean pass."""
    checks = simulate.health_check()
    assert len(checks) == 1
    assert checks[0].ok is True
    assert "bijection" in checks[0].name


def test_props_health_check():
    """Verify player props engine health check returns clean pass."""
    checks = props.health_check()
    assert len(checks) == 1
    assert checks[0].ok is True
    assert "player props" in checks[0].name


def test_season_health_check():
    """Verify season projection engine health check returns clean pass."""
    checks = season.health_check()
    assert len(checks) == 1
    assert checks[0].ok is True
    assert "season projection" in checks[0].name


def test_portfolio_health_check():
    """Verify portfolio allocator health check returns clean pass."""
    checks = portfolio.health_check()
    assert len(checks) == 1
    assert checks[0].ok is True
    assert "kelly allocator" in checks[0].name
