"""Unit tests for Interactive REST API Gateway (API-01, ADR-150)."""

import json

from mlb_baseball.api import (
    MLBApiRouter,
    health_check,
)


def test_api_routes_get_forecasts_and_health():
    """Verify API router returns structured JSON responses for health and daily forecasts."""
    router = MLBApiRouter()

    r_health = router.route_request("/api/v1/health", "GET")
    assert r_health.status_code == 200
    assert r_health.content_type == "application/json"
    h_data = json.loads(r_health.body_data)
    assert "status" in h_data

    r_fc = router.route_request("/api/v1/forecasts/daily", "GET", {"date": "2026-08-24"})
    assert r_fc.status_code == 200
    fc_data = json.loads(r_fc.body_data)
    assert fc_data["forecast_date"] == "2026-08-24"
    assert len(fc_data["games"]) == 2


def test_api_post_tool_hedge():
    """Verify API router processes POST calculation for live hedging tool."""
    router = MLBApiRouter()

    payload = json.dumps({"stake": 100.0, "odds_initial": 2.50, "odds_hedge": 2.20}).encode("utf-8")
    r_hedge = router.route_request("/api/v1/tools/hedge", "POST", body=payload)

    assert r_hedge.status_code == 200
    h_res = json.loads(r_hedge.body_data)
    assert h_res["hedge_stake"] > 0
    assert h_res["guaranteed_profit"] > 0


def test_api_404_on_unknown_endpoint():
    """Verify API returns 404 on nonexistent endpoints."""
    router = MLBApiRouter()
    r_404 = router.route_request("/api/v1/unknown", "GET")
    assert r_404.status_code == 404


def test_api_health_check():
    """Verify API health check passes."""
    checks = health_check()
    assert len(checks) == 1
    assert checks[0].ok is True
    assert "REST API routes verified" in checks[0].detail
