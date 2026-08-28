"""Batter In-Zone Whiff vs Chase Swing Vulnerability Matrix (ZONE-SWING-01, ADR-171).

Provides 4-zone plate discipline decomposition and swing efficiency modeling:
1. In-Zone Contact Rate vs League Baseline (Zone Contact Deficit, ZCD).
2. Out-of-Zone Chase Aggression Balance (Chase Efficiency Ratio, CER).
3. Whiff Run Loss and Exploitable Pitch Vulnerability Detection.
4. Batter Discipline Archetypes (In-Zone Punisher, Chase Vulnerable, Zone Whiff Prone).

Adheres strictly to object-oriented encapsulation, polymorphic protocols, and
point-in-time correctness with zero lookahead leakage.
"""

from __future__ import annotations

import dataclasses
from typing import Protocol

from mlb_baseball.health import Check


@dataclasses.dataclass(frozen=True)
class BatterZoneSwingMetrics:
    """Observed in-zone and out-of-zone swing and contact rates for a batter."""

    batter_id: str
    batter_name: str
    z_swing_pct: float = 0.68  # Swing rate on in-zone pitches
    z_contact_pct: float = 0.84  # Contact rate on in-zone swings
    o_swing_pct: float = 0.28  # Chase rate on out-of-zone pitches
    o_contact_pct: float = 0.58  # Contact rate on out-of-zone swings


@dataclasses.dataclass(frozen=True)
class ZoneSwingEvaluationResult:
    """Evaluated swing efficiency, zone contact deficit, and vulnerability."""

    batter_name: str
    zone_contact_deficit: float  # League Z-Contact (0.820) - Batter Z-Contact
    chase_efficiency_ratio: float  # O-Swing% / Z-Swing%
    vulnerability_archetype: (
        str  # "IN_ZONE_PUNISHER", "CHASE_VULNERABLE", "ZONE_WHIFF_PRONE", "BALANCED"
    )
    is_exploitable_whiff_target: bool


class BaseZoneSwingEngine(Protocol):
    """Polymorphic protocol for zone swing vulnerability engines."""

    def evaluate_discipline(
        self,
        metrics: BatterZoneSwingMetrics,
        league_z_contact: float = 0.820,
    ) -> ZoneSwingEvaluationResult:
        """Calculate zone contact deficit and vulnerability archetype."""
        ...


class ZoneSwingVulnerabilityEngine:
    """Evaluates batter zone contact deficit and swing efficiency (ZONE-SWING-01)."""

    def evaluate_discipline(
        self,
        metrics: BatterZoneSwingMetrics,
        league_z_contact: float = 0.820,
    ) -> ZoneSwingEvaluationResult:
        """Compute ZCD, CER, and exploitable vulnerability."""
        # 1. Zone Contact Deficit: Positive indicates worse contact than league average
        zcd = round(league_z_contact - metrics.z_contact_pct, 3)

        # 2. Chase Efficiency Ratio: O-Swing% / Z-Swing%
        cer = round(metrics.o_swing_pct / max(0.01, metrics.z_swing_pct), 2)

        # 3. Exploitable target flag
        is_target = zcd >= 0.050 or (cer >= 0.52 and metrics.o_swing_pct >= 0.35)

        # 4. Archetype Classification
        if zcd <= -0.035 and cer <= 0.42:
            archetype = "IN_ZONE_PUNISHER"
        elif cer >= 0.52 or metrics.o_swing_pct >= 0.36:
            archetype = "CHASE_VULNERABLE"
        elif zcd >= 0.050:
            archetype = "ZONE_WHIFF_PRONE"
        else:
            archetype = "BALANCED"

        return ZoneSwingEvaluationResult(
            batter_name=metrics.batter_name,
            zone_contact_deficit=zcd,
            chase_efficiency_ratio=cer,
            vulnerability_archetype=archetype,
            is_exploitable_whiff_target=is_target,
        )


def health_check() -> list[Check]:
    """Operational health check for Zone Swing Vulnerability Engine (ZONE-SWING-01)."""
    checks: list[Check] = []
    try:
        engine = ZoneSwingVulnerabilityEngine()
        punisher = BatterZoneSwingMetrics(
            "b1",
            "Juan Soto Archetype",
            z_swing_pct=0.68,
            z_contact_pct=0.88,
            o_swing_pct=0.20,
            o_contact_pct=0.65,
        )
        chaser = BatterZoneSwingMetrics(
            "b2",
            "Free Swinger",
            z_swing_pct=0.72,
            z_contact_pct=0.74,
            o_swing_pct=0.42,
            o_contact_pct=0.50,
        )

        r_pun = engine.evaluate_discipline(punisher)
        r_cha = engine.evaluate_discipline(chaser)

        if (
            r_pun.vulnerability_archetype == "IN_ZONE_PUNISHER"
            and r_cha.is_exploitable_whiff_target
        ):
            checks.append(
                Check(
                    "zone swing engine",
                    True,
                    f"Discipline verified (ZCD: {r_pun.zone_contact_deficit:>+5.3f})",
                )
            )
        else:
            checks.append(
                Check("zone swing engine", False, f"Unexpected zone swing output: {r_pun}, {r_cha}")
            )
    except Exception as exc:
        checks.append(Check("zone swing engine", False, str(exc)))
    return checks
