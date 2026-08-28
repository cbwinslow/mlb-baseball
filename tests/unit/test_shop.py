"""Unit tests for Multi-Book Line Shopping & Value Scanner (SHOP-01, ADR-146)."""

from mlb_baseball.model.shop import (
    OddsLineShoppingEngine,
    SportsbookQuote,
    health_check,
)


def test_line_shopping_discovers_best_prices_and_arbitrage():
    """Verify scanning across books finds best odds and detects near-zero synthetic hold."""
    engine = OddsLineShoppingEngine()

    quotes = [
        SportsbookQuote("DK", home_decimal_odds=2.20, away_decimal_odds=1.72, vig_pct=4.1),
        SportsbookQuote("FD", home_decimal_odds=2.05, away_decimal_odds=1.85, vig_pct=4.0),
        SportsbookQuote("Pinny", home_decimal_odds=2.15, away_decimal_odds=1.78, vig_pct=2.2),
    ]

    res = engine.find_best_lines("g1", "NYY", "BOS", quotes, model_home_prob=0.48)

    assert res.best_home_sportsbook == "DK"
    assert res.best_home_odds == 2.20
    assert res.best_away_sportsbook == "FD"
    assert res.best_away_odds == 1.85
    assert res.synthetic_market_hold_pct < 1.0  # (1/2.20 + 1/1.85 - 1) = -0.49% (arbitrage)
    assert res.is_pure_arbitrage is True
    assert res.best_value_side == "HOME"  # 0.48 * 2.20 - 1 = +5.6% EV


def test_negative_ev_no_bet_recommendation():
    """Verify when model finds no edge on either side, best_value_side is None."""
    engine = OddsLineShoppingEngine()

    quotes = [
        SportsbookQuote("DK", home_decimal_odds=1.90, away_decimal_odds=1.90, vig_pct=5.0),
    ]

    res = engine.find_best_lines("g2", "LAD", "SD", quotes, model_home_prob=0.50)

    assert res.home_ev_pct < 0.0
    assert res.away_ev_pct < 0.0
    assert res.best_value_side is None


def test_shop_health_check():
    """Verify shopping health check passes."""
    checks = health_check()
    assert len(checks) == 1
    assert checks[0].ok is True
    assert "Line shopping verified" in checks[0].detail
