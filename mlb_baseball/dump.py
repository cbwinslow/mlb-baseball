"""Comprehensive Player Dossier & Data Dump Exporter (DUMP-01, ADR-133).

Extracts and exports multi-layered, structured player intelligence packages:
1. Biographical & Identity Metadata (MLB ID, Name, Bats/Throws, Position).
2. Rate Statistics & Sabermetric Baselines (wOBA, wRC+, CSW%, Barrel%).
3. Marcel Empirical Bayes Talent Projections (Projected Win Rate, ERA, wOBA).
4. Physical Stuff+ / Location+ / Pitching+ Arsenal Breakdown.
5. Multi-Format Exporters (Hierarchical JSON and Flat Analytics CSV).

Adheres strictly to object-oriented encapsulation, polymorphic protocols, and
point-in-time correctness with zero lookahead leakage.
"""

from __future__ import annotations

import csv
import dataclasses
import io
import json
from collections.abc import Sequence
from typing import Protocol

from mlb_baseball.health import Check


@dataclasses.dataclass(frozen=True)
class PlayerDossierDump:
    """Comprehensive single-player analytical dossier packaging all model metrics."""

    player_id: str
    player_name: str
    season: int
    position_type: str  # "pitcher" or "batter"
    team_abbrev: str
    primary_metrics: dict[str, float]  # wOBA, wRC+, ERA, CSW%, etc.
    stuff_arsenal: dict[str, float]  # Fastball Velo, IVB, Stuff+, Location+, Pitching+
    projection: dict[str, float]  # Marcel talent projections
    zone_whiff_rates: dict[int, float]  # 9-quadrant whiff map
    generated_at: str = "2026-08-24T00:00:00Z"


class BaseDataDumpExporter(Protocol):
    """Polymorphic protocol for data dump serialization."""

    def export_json(self, dossiers: Sequence[PlayerDossierDump]) -> str:
        """Export collection of player dossiers as formatted JSON."""
        ...

    def export_csv(self, dossiers: Sequence[PlayerDossierDump]) -> str:
        """Export collection of player dossiers as flattened CSV."""
        ...


class PlayerDataDumpEngine:
    """Serializes structured player dossiers into JSON and CSV (DUMP-01)."""

    def export_json(self, dossiers: Sequence[PlayerDossierDump], indent: int = 2) -> str:
        """Export player dossiers as hierarchical JSON structure."""
        data_list = []
        for d in dossiers:
            data_list.append(
                {
                    "player_id": d.player_id,
                    "player_name": d.player_name,
                    "season": d.season,
                    "position_type": d.position_type,
                    "team_abbrev": d.team_abbrev,
                    "primary_metrics": d.primary_metrics,
                    "stuff_arsenal": d.stuff_arsenal,
                    "projection": d.projection,
                    "zone_whiff_rates": d.zone_whiff_rates,
                    "generated_at": d.generated_at,
                }
            )
        return json.dumps(data_list, indent=indent)

    def export_csv(self, dossiers: Sequence[PlayerDossierDump]) -> str:
        """Export player dossiers as flattened CSV rows with consistent schema headers."""
        output = io.StringIO()
        fieldnames = [
            "player_id",
            "player_name",
            "season",
            "position_type",
            "team_abbrev",
            "woba",
            "wrc_plus",
            "era",
            "csw_pct",
            "stuff_plus",
            "location_plus",
            "pitching_plus",
            "projected_woba",
            "projected_era",
            "worst_zone",
        ]
        writer = csv.DictWriter(output, fieldnames=fieldnames)
        writer.writeheader()

        for d in dossiers:
            # Find worst zone if present
            worst_z = (
                max(d.zone_whiff_rates, key=lambda k: d.zone_whiff_rates[k])
                if d.zone_whiff_rates
                else 0
            )
            row = {
                "player_id": d.player_id,
                "player_name": d.player_name,
                "season": d.season,
                "position_type": d.position_type,
                "team_abbrev": d.team_abbrev,
                "woba": d.primary_metrics.get("woba", 0.0),
                "wrc_plus": d.primary_metrics.get("wrc_plus", 100.0),
                "era": d.primary_metrics.get("era", 0.0),
                "csw_pct": d.primary_metrics.get("csw_pct", 0.0),
                "stuff_plus": d.stuff_arsenal.get("stuff_plus", 100.0),
                "location_plus": d.stuff_arsenal.get("location_plus", 100.0),
                "pitching_plus": d.stuff_arsenal.get("pitching_plus", 100.0),
                "projected_woba": d.projection.get("projected_woba", 0.0),
                "projected_era": d.projection.get("projected_era", 0.0),
                "worst_zone": worst_z,
            }
            writer.writerow(row)

        return output.getvalue()


def health_check() -> list[Check]:
    """Operational health check for the Player Dossier & Data Dump Exporter (DUMP-01)."""
    checks: list[Check] = []
    try:
        engine = PlayerDataDumpEngine()
        sample_dossier = PlayerDossierDump(
            player_id="660271",
            player_name="Shohei Ohtani",
            season=2024,
            position_type="batter",
            team_abbrev="LAD",
            primary_metrics={"woba": 0.425, "wrc_plus": 182.0, "barrel_pct": 0.198},
            stuff_arsenal={"stuff_plus": 115.0, "pitching_plus": 112.0},
            projection={"projected_woba": 0.405},
            zone_whiff_rates={1: 0.15, 2: 0.12, 3: 0.28},
        )

        json_out = engine.export_json([sample_dossier])
        csv_out = engine.export_csv([sample_dossier])

        if '"Shohei Ohtani"' in json_out and "Shohei Ohtani" in csv_out and "wrc_plus" in csv_out:
            checks.append(
                Check(
                    "player dossier dump engine",
                    True,
                    "Multi-format JSON and CSV serialization verified",
                )
            )
        else:
            checks.append(Check("player dossier dump engine", False, "Export format mismatch"))
    except Exception as exc:
        checks.append(Check("player dossier dump engine", False, str(exc)))
    return checks
