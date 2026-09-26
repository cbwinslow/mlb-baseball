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
    assert len(e_checks) == 3
    assert all(c.ok for c in e_checks)


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


def test_stuff_health_check():
    """Verify pitch physics rating engine health check returns clean pass."""
    from mlb_baseball.model import stuff

    s_checks = stuff.health_check()
    assert len(s_checks) == 1
    assert s_checks[0].ok is True


def test_heatmap_health_check():
    """Verify spatial heatmap engine health check returns clean pass."""
    from mlb_baseball.model import heatmap

    h_checks = heatmap.health_check()
    assert len(h_checks) == 1
    assert h_checks[0].ok is True


def test_neural_health_check():
    """Verify hierarchical neural combiner health check returns clean pass."""
    from mlb_baseball.model import neural

    n_checks = neural.health_check()
    assert len(n_checks) == 1
    assert n_checks[0].ok is True


def test_pipeline_health_check():
    """Verify master daily pipeline health check returns clean pass."""
    from mlb_baseball import pipeline

    p_checks = pipeline.health_check()
    assert len(p_checks) == 1
    assert p_checks[0].ok is True


def test_visual_and_hedge_health_checks():
    """Verify health checks for visual and hedge modules."""
    from mlb_baseball import visual
    from mlb_baseball.model import hedge

    assert visual.health_check()[0].ok is True
    assert hedge.health_check()[0].ok is True


def test_daemon_health_check():
    """Verify health check for daemon module."""
    from mlb_baseball import daemon

    assert daemon.health_check()[0].ok is True


def test_shop_health_check():
    """Verify health check for shop module."""
    from mlb_baseball.model import shop

    assert shop.health_check()[0].ok is True


def test_api_health_check():
    """Verify health check for api module."""
    from mlb_baseball import api

    assert api.health_check()[0].ok is True


def test_tunnel_health_check():
    """Verify health check for tunnel module."""
    from mlb_baseball.model import tunnel

    assert tunnel.health_check()[0].ok is True


def test_nrfi_health_check():
    """Verify health check for nrfi module."""
    from mlb_baseball.model import nrfi

    assert nrfi.health_check()[0].ok is True


def test_babip_and_vaa_health_checks():
    """Verify health checks for babip and vaa modules."""
    from mlb_baseball.model import babip, vaa

    assert babip.health_check()[0].ok is True
    assert vaa.health_check()[0].ok is True


def test_arm_slot_health_check():
    """Verify health check for arm_slot module."""
    from mlb_baseball.model import arm_slot

    assert arm_slot.health_check()[0].ok is True
