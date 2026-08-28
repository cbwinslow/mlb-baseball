"""Batter Contact Quality & Damage Rate Engine (DAMAGE-01, ADR-159).

Provides Statcast launch ballistics classification and true extra-base damage modeling:
1. Statcast 2D Batted Ball Classification (Barrel Blast, Solid Contact, Flare/Burner, Topper, Pop).
2. Damage Rate Metric (% of contact producing xSLG >= 1.500 or extra-base run value).
3. Expected Damage Value (EDV) per Batted Ball Event.
4. Hitter Power Archetypes (Elite Slugger, Solid Extra-Base Threat, Slap Contact Hitter).

Adheres strictly to object-oriented encapsulation, polymorphic protocols, and
point-in-time correctness with zero lookahead leakage.
"""

from __future__ import annotations

import dataclasses
from typing import Protocol

from mlb_baseball.health import Check


@dataclasses.dataclass(frozen=True)
class BattedBallContact:
    """Individual Statcast launch speed and launch angle measurement."""

    bbe_id: str
    exit_velocity_mph: float
    launch_angle_deg: float


@dataclasses.dataclass(frozen=True)
class BatterContactProfile:
    """Aggregated sample of batted ball events for a hitter."""

    batter_id: str
    batter_name: str
    contacts: list[BattedBallContact]


@dataclasses.dataclass(frozen=True)
class DamageEvaluationResult:
    """Evaluated contact quality metrics and damage capacity."""

    batter_name: str
    total_bbe: int
    barrel_count: int
    solid_count: int
    damage_rate_pct: float  # (Barrels + 0.6 * Solid) / Total BBE * 100
    expected_damage_value: float  # Run value per BBE
    damage_tier: str  # "ELITE_SLUGGER", "SOLID_THREAT", "CONTACT_SLAP_HITTER"


class BaseDamageEngine(Protocol):
    """Polymorphic protocol for contact damage evaluation engines."""

    def evaluate_damage(
        self,
        profile: BatterContactProfile,
    ) -> DamageEvaluationResult:
        """Calculate contact damage rates and expected damage run value."""
        ...


class ContactDamageEngine:
    """Calculates Statcast contact quality, barrel rates, and damage value (DAMAGE-01)."""

    def classify_contact(self, ev: float, la: float) -> tuple[str, float]:
        """Classify single contact into bucket and run value."""
        # 1. Barrel: EV >= 98.0 mph and LA in dynamic sweet spot [22-32 range around 100mph]
        if ev >= 98.0 and 22.0 <= la <= 32.0:
            return "BARREL_BLAST", 1.40
        # 2. Solid Contact: EV >= 95.0 mph in extended launch window
        if ev >= 95.0 and (10.0 <= la < 22.0 or 32.0 < la <= 38.0):
            return "SOLID_CONTACT", 0.80
        # 3. Flare / Burner: EV 75-95 mph in line drive zone
        if 75.0 <= ev < 95.0 and 10.0 <= la <= 25.0:
            return "FLARE_BURNER", 0.45
        # 4. Pop-up
        if la > 45.0:
            return "POPUP", 0.02
        # 5. Weak Grounder / Topper
        return "WEAK_TOPPER", 0.15

    def evaluate_damage(
        self,
        profile: BatterContactProfile,
    ) -> DamageEvaluationResult:
        """Compute aggregate damage rate and expected damage value."""
        if not profile.contacts:
            return DamageEvaluationResult(
                batter_name=profile.batter_name,
                total_bbe=0,
                barrel_count=0,
                solid_count=0,
                damage_rate_pct=0.0,
                expected_damage_value=0.0,
                damage_tier="CONTACT_SLAP_HITTER",
            )

        n = len(profile.contacts)
        barrels = 0
        solids = 0
        total_rv = 0.0

        for c in profile.contacts:
            cat, rv = self.classify_contact(c.exit_velocity_mph, c.launch_angle_deg)
            if cat == "BARREL_BLAST":
                barrels += 1
            elif cat == "SOLID_CONTACT":
                solids += 1
            total_rv += rv

        damage_rate = round(((barrels + 0.6 * solids) / n) * 100.0, 1)
        edv = round(total_rv / n, 3)

        if damage_rate >= 18.0 or edv >= 0.50:
            tier = "ELITE_SLUGGER"
        elif damage_rate >= 12.0:
            tier = "SOLID_THREAT"
        else:
            tier = "CONTACT_SLAP_HITTER"

        return DamageEvaluationResult(
            batter_name=profile.batter_name,
            total_bbe=n,
            barrel_count=barrels,
            solid_count=solids,
            damage_rate_pct=damage_rate,
            expected_damage_value=edv,
            damage_tier=tier,
        )


def health_check() -> list[Check]:
    """Operational health check for the Contact Damage Engine (DAMAGE-01)."""
    checks: list[Check] = []
    try:
        engine = ContactDamageEngine()
        slugger_hits = [
            BattedBallContact("c1", 108.0, 26.0),  # Barrel
            BattedBallContact("c2", 104.0, 28.0),  # Barrel
            BattedBallContact("c3", 99.0, 18.0),  # Solid
            BattedBallContact("c4", 88.0, 12.0),  # Flare
            BattedBallContact("c5", 72.0, -5.0),  # Weak
        ]
        profile = BatterContactProfile("b1", "Power Hitter", slugger_hits)
        res = engine.evaluate_damage(profile)

        if res.barrel_count == 2 and res.damage_tier == "ELITE_SLUGGER":
            checks.append(
                Check(
                    "contact damage engine",
                    True,
                    f"Damage verified (Rate: {res.damage_rate_pct:.1f}%)",
                )
            )
        else:
            checks.append(Check("contact damage engine", False, f"Unexpected damage output: {res}"))
    except Exception as exc:
        checks.append(Check("contact damage engine", False, str(exc)))
    return checks
