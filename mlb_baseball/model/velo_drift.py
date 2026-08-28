"""Starting Pitcher Fastball Velocity Drift & Arm Fatigue Engine (VELO-DRIFT-01, ADR-188).

Provides intra-game velocity decay, spin loss, and late-game fatigue modeling:
1. Intra-Game Fastball Velocity Drift (Late Inning Velo - Early Inning Velo).
2. Fastball Velocity Retention Index (FVRI score out of 100).
3. Late-Game Home Run Vulnerability Multiplier (power surge from degraded fastball shape).
4. Fatigue Resistance Tiers (Elite Velo Preservation, Moderate Velo Fade, Severe Velo Cliff).

Adheres strictly to object-oriented encapsulation, polymorphic protocols, and
point-in-time correctness with zero lookahead leakage.
"""

from __future__ import annotations

import dataclasses
from typing import Protocol

from mlb_baseball.health import Check


@dataclasses.dataclass(frozen=True)
class PitcherVeloProfile:
    """Observed early-game and late-game fastball velocity and spin measurements."""

    pitcher_id: str
    pitcher_name: str
    early_game_velo_mph: float = 96.0  # Innings 1-2 avg 4-seam velo
    late_game_velo_mph: float = 94.5  # Innings 5+ avg 4-seam velo
    pitch_count_total: int = 90
    early_spin_rpm: float = 2380.0
    late_spin_rpm: float = 2320.0


@dataclasses.dataclass(frozen=True)
class VeloDriftEvaluationResult:
    """Evaluated velocity drift, FVRI score, and late-game vulnerability."""

    pitcher_name: str
    velo_drift_mph: float  # Late Velo - Early Velo (e.g. -1.5 mph)
    fvri_score: float  # Fastball Velocity Retention Index (0 to 100)
    hr_vulnerability_multiplier: float  # Multiplier on expected HR/9
    fatigue_tier: (
        str  # "ELITE_VELO_PRESERVATION", "MODERATE_VELO_FADE", "SEVERE_VELO_CLIFF", "AVERAGE"
    )
    is_severe_hook_candidate: bool


class BaseVeloDriftEngine(Protocol):
    """Polymorphic protocol for velocity drift engines."""

    def evaluate_velo_drift(
        self,
        profile: PitcherVeloProfile,
    ) -> VeloDriftEvaluationResult:
        """Calculate velocity drift, FVRI, and fatigue tier."""
        ...


class FastballVeloDriftEngine:
    """Calculates intra-game velocity degradation and late-game fatigue (VELO-DRIFT-01)."""

    def evaluate_velo_drift(
        self,
        profile: PitcherVeloProfile,
    ) -> VeloDriftEvaluationResult:
        """Compute velo delta, retention index, and HR vulnerability."""
        drift = round(profile.late_game_velo_mph - profile.early_game_velo_mph, 2)
        spin_drift = round(profile.late_spin_rpm - profile.early_spin_rpm, 1)

        # FVRI Retention Score (0 to 100)
        velo_loss = max(0.0, -drift)
        spin_loss = max(0.0, -spin_drift)
        fvri = max(0.0, 100.0 - (velo_loss / 0.5) * 12.0 - (spin_loss / 50.0) * 6.0)
        fvri = round(min(100.0, fvri), 1)

        # Late-Game Home Run Multiplier
        hr_mult = round(1.0 + velo_loss * 0.20, 2)

        # Severe Hook Flag
        is_hook = drift <= -2.00 or fvri <= 50.0

        # Fatigue Tier
        if drift >= -0.70 and fvri >= 85.0:
            tier = "ELITE_VELO_PRESERVATION"
        elif drift <= -2.00 or fvri <= 50.0:
            tier = "SEVERE_VELO_CLIFF"
        elif drift <= -1.20:
            tier = "MODERATE_VELO_FADE"
        else:
            tier = "AVERAGE"

        return VeloDriftEvaluationResult(
            pitcher_name=profile.pitcher_name,
            velo_drift_mph=drift,
            fvri_score=fvri,
            hr_vulnerability_multiplier=hr_mult,
            fatigue_tier=tier,
            is_severe_hook_candidate=is_hook,
        )


def health_check() -> list[Check]:
    """Operational health check for Fastball Velocity Drift Engine (VELO-DRIFT-01)."""
    checks: list[Check] = []
    try:
        engine = FastballVeloDriftEngine()
        verlander = PitcherVeloProfile(
            "p1", "Justin Verlander Archetype", 96.5, 96.1, 100, 2450, 2430
        )
        fatigued = PitcherVeloProfile("p2", "Fatigued Arm", 95.5, 92.8, 85, 2380, 2220)

        r_ver = engine.evaluate_velo_drift(verlander)
        r_fat = engine.evaluate_velo_drift(fatigued)

        if (
            r_ver.fatigue_tier == "ELITE_VELO_PRESERVATION"
            and r_fat.fatigue_tier == "SEVERE_VELO_CLIFF"
        ):
            checks.append(
                Check(
                    "velo drift engine",
                    True,
                    f"Velo drift verified (FVRI: {r_ver.fvri_score:.1f})",
                )
            )
        else:
            checks.append(
                Check("velo drift engine", False, f"Unexpected velo drift output: {r_ver}, {r_fat}")
            )
    except Exception as exc:
        checks.append(Check("velo drift engine", False, str(exc)))
    return checks
