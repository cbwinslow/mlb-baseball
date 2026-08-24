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


def test_wpa_health_check():
    """Verify wpa engine health check returns clean pass."""
    from mlb_baseball.model import wpa

    checks = wpa.health_check()
    assert len(checks) == 1
    assert checks[0].ok is True
    assert "wpa engine" in checks[0].name


def test_research_and_calibration_health_checks():
    """Verify research catalog and calibration engine health checks return clean pass."""
    from mlb_baseball import research
    from mlb_baseball.model import calibration

    r_checks = research.health_check()
    assert len(r_checks) == 1
    assert r_checks[0].ok is True

    c_checks = calibration.health_check()
    assert len(c_checks) == 1
    assert c_checks[0].ok is True


def test_backtest_health_check():
    """Verify backtesting engine health check returns clean pass."""
    from mlb_baseball.model import backtest

    b_checks = backtest.health_check()
    assert len(b_checks) == 1
    assert b_checks[0].ok is True


def test_ros_health_check():
    """Verify rest-of-season health check returns clean pass."""
    from mlb_baseball.model import ros

    r_checks = ros.health_check()
    assert len(r_checks) == 1
    assert r_checks[0].ok is True


def test_export_health_check():
    """Verify export engine health check returns clean pass."""
    from mlb_baseball import export

    e_checks = export.health_check()
    assert len(e_checks) == 1
    assert e_checks[0].ok is True


def test_stack_health_check():
    """Verify stack meta-learner health check returns clean pass."""
    from mlb_baseball.model import stack

    s_checks = stack.health_check()
    assert len(s_checks) == 1
    assert s_checks[0].ok is True


def test_drift_health_check():
    """Verify model drift monitor health check returns clean pass."""
    from mlb_baseball.model import drift

    d_checks = drift.health_check()
    assert len(d_checks) == 1
    assert d_checks[0].ok is True


def test_parlay_health_check():
    """Verify correlated parlay engine health check returns clean pass."""
    from mlb_baseball.model import parlay

    p_checks = parlay.health_check()
    assert len(p_checks) == 1
    assert p_checks[0].ok is True
