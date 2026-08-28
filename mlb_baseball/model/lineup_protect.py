"""Batter Lineup Protection & On-Deck Advantage Engine (LINEUP-PROTECT-01, ADR-255).

Provides lineup position protection modeling, on-deck threat influence on pitcher
approach, and lineup construction run value:
1. Protection Influence Index (PII) scoring how much the on-deck hitter changes
   the quality of pitches thrown to the current batter.
2. Lineup Protection Run Value (LPRV) estimating runs created by on-deck threat.
3. Protection tiers classifying protection quality.

Mathematical foundation:
    Pitchers adjust approach when a dangerous hitter is on deck, avoiding walks
    and throwing more hittable pitches. When weak hitters follow, pitchers nibble
    more aggressively and issue fewer mistakes.

    PII = max(0, 100 + (on_deck_woba - 0.320) * 120.0
              + (zone_pct - 45.0) * 0.8
              + (first_pitch_strike_pct - 60.0) * 0.5)

    LPRV_runs = (PII - 100.0) * (PA * 0.0022)

References:
    - Tango, Lichtman, Dolphin (2007). The Book: Playing the Percentages in
      Baseball. Ch. 3 "Protection in the Batting Order".
    - Lindsey (1963). "An Investigation of Strategies in Baseball."
    - Albert & Bennett (2001). Curve Ball: Baseball, Statistics, and the Role
      of Chance in the Game.

Adheres strictly to object-oriented encapsulation, polymorphic protocols, and
point-in-time correctness with zero lookahead leakage.
"""

from __future__ import annotations

import dataclasses
from typing import Protocol

from mlb_baseball.health import Check


@dataclasses.dataclass(frozen=True)
class BatterProtectionMetrics:
    """Observed batter/on-deck hitter metrics for lineup protection evaluation."""

    batter_id: str
    batter_name: str
    on_deck_woba: float = 0.320
    zone_pct: float = 45.0
    first_pitch_strike_pct: float = 60.0
    pa_count: int = 120
    intentional_walk_pct: float = 1.5


@dataclasses.dataclass(frozen=True)
class ProtectionEvaluationResult:
    """Output of lineup protection evaluation."""

    batter_name: str
    pii_score: float
    lprv_runs: float
    protection_tier: str
    is_heavily_protected: bool


class ProtectionEvaluator(Protocol):
    """Protocol for lineup protection evaluators."""

    def evaluate_protection(
        self,
        metrics: BatterProtectionMetrics,
    ) -> ProtectionEvaluationResult:
        """Calculate PII rating, LPRV runs, and protection tier."""
        ...


class BatterLineupProtectionEngine:
    """Calculates lineup protection influence and run value (LINEUP-PROTECT-01)."""

    def evaluate_protection(
        self,
        metrics: BatterProtectionMetrics,
    ) -> ProtectionEvaluationResult:
        """Compute PII score and lineup protection runs.

        PII (Protection Influence Index):
            PII = max(0, 100 + (on_deck_woba - 0.320) * 120.0
                      + (zone_pct - 45.0) * 0.8
                      + (first_pitch_strike_pct - 60.0) * 0.5)

        LPRV (Lineup Protection Run Value):
            LPRV_runs = (PII - 100.0) * (PA * 0.0022)
        """
        woba_bonus = (metrics.on_deck_woba - 0.320) * 120.0
        zone_bonus = (metrics.zone_pct - 45.0) * 0.8
        fstrike_bonus = (metrics.first_pitch_strike_pct - 60.0) * 0.5
        pii = round(max(0.0, 100.0 + woba_bonus + zone_bonus + fstrike_bonus), 1)

        pa = max(1, metrics.pa_count)
        runs = round((pii - 100.0) * (pa * 0.0022), 2)

        is_protected = (
            pii >= 115.0 and metrics.on_deck_woba >= 0.370 and metrics.intentional_walk_pct <= 2.0
        )

        if is_protected:
            tier = "ELITE_ON_DECK_PROTECTION_SHIELD"
        elif metrics.on_deck_woba <= 0.260 or metrics.zone_pct <= 38.0:
            tier = "UNPROTECTED_NIBBLE_TARGET_LIABILITY"
        elif pii >= 104.0 and metrics.on_deck_woba >= 0.330:
            tier = "SOLID_LINEUP_PROTECTION"
        else:
            tier = "AVERAGE_LINEUP_PROTECTION"

        return ProtectionEvaluationResult(
            batter_name=metrics.batter_name,
            pii_score=pii,
            lprv_runs=runs,
            protection_tier=tier,
            is_heavily_protected=is_protected,
        )


def health_check() -> list[Check]:
    """Verify lineup protection engine produces expected outputs."""
    engine = BatterLineupProtectionEngine()

    protected = BatterProtectionMetrics(
        batter_id="p1",
        batter_name="Soto Protected",
        on_deck_woba=0.400,
        zone_pct=52.0,
        first_pitch_strike_pct=68.0,
        pa_count=200,
        intentional_walk_pct=1.2,
    )
    weak = BatterProtectionMetrics(
        batter_id="p2",
        batter_name="Weak Follower",
        on_deck_woba=0.240,
        zone_pct=36.0,
        first_pitch_strike_pct=52.0,
        pa_count=180,
    )

    r_p = engine.evaluate_protection(protected)
    r_w = engine.evaluate_protection(weak)

    ok = (
        r_p.pii_score > 110.0
        and r_p.lprv_runs > 2.0
        and r_p.protection_tier == "ELITE_ON_DECK_PROTECTION_SHIELD"
        and r_p.is_heavily_protected is True
        and r_w.protection_tier == "UNPROTECTED_NIBBLE_TARGET_LIABILITY"
        and r_w.lprv_runs < 0.0
    )

    return [
        Check(
            name="lineup protection engine",
            ok=ok,
            detail=(
                f"Expected outputs: {r_p}, {r_w}"
                if ok
                else f"Unexpected lineup protection output: {r_p}, {r_w}"
            ),
        )
    ]
