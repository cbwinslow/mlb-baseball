"""Unit tests for Player Dossier & Data Dump Exporter (DUMP-01, ADR-133)."""

import json

from mlb_baseball.dump import PlayerDataDumpEngine, PlayerDossierDump, health_check


def test_player_data_dump_json_serialization():
    """Verify export_json produces structured, valid JSON with all fields."""
    engine = PlayerDataDumpEngine()
    dossier = PlayerDossierDump(
        player_id="12345",
        player_name="Test Ace",
        season=2024,
        position_type="pitcher",
        team_abbrev="ATL",
        primary_metrics={"era": 2.85, "csw_pct": 0.32},
        stuff_arsenal={"stuff_plus": 122.0, "location_plus": 105.0, "pitching_plus": 115.2},
        projection={"projected_era": 3.10},
        zone_whiff_rates={1: 0.20, 2: 0.15, 3: 0.40},
    )

    json_str = engine.export_json([dossier])
    parsed = json.loads(json_str)

    assert len(parsed) == 1
    assert parsed[0]["player_name"] == "Test Ace"
    assert parsed[0]["stuff_arsenal"]["stuff_plus"] == 122.0
    assert parsed[0]["zone_whiff_rates"]["3"] == 0.40


def test_player_data_dump_csv_serialization():
    """Verify export_csv produces clean tabular CSV with header."""
    engine = PlayerDataDumpEngine()
    dossier = PlayerDossierDump(
        player_id="12345",
        player_name="Test Slugger",
        season=2024,
        position_type="batter",
        team_abbrev="NYY",
        primary_metrics={"woba": 0.380, "wrc_plus": 145.0},
        stuff_arsenal={},
        projection={"projected_woba": 0.365},
        zone_whiff_rates={5: 0.10, 9: 0.35},
    )

    csv_str = engine.export_csv([dossier])
    lines = csv_str.strip().split("\n")

    assert len(lines) == 2  # Header + 1 row
    assert "player_id,player_name,season" in lines[0]
    assert "Test Slugger,2024,batter,NYY" in lines[1]
    assert ",145.0," in lines[1]


def test_dump_health_check():
    """Verify dump health check passes."""
    checks = health_check()
    assert len(checks) == 1
    assert checks[0].ok is True
    assert "Multi-format JSON and CSV serialization verified" in checks[0].detail
