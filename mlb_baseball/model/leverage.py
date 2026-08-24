"""Bullpen High-Leverage Win Probability Preservation & Volatility Engine (LEV-01, ADR-154).

Provides high-leverage reliever evaluation, win probability preservation, and closer volatility:
1. Leverage Index (LI) Context Weighting (Low, Medium, High, Extreme).
2. Win Probability Added per Leverage Index (WPA/LI clutch efficiency).
3. Closer Blown-Save Volatility Index (quantifies variance in 9th inning save spots).
4. Bullpen Lockdown vs High-Variance Volatile Pitcher Tiers.

Adheres strictly to object-oriented encapsulation, polymorphic protocols, and
point-in-time correctness with zero lookahead leakage.
"""

from __future__ import annotations

import dataclasses
from typing import Protocol

import numpy as np

from mlb_baseball.health import Check


@dataclasses.dataclass(frozen=True)
class RelieverLeverageProfile:
    """Reliever performance stats in high-leverage situations."""

    reliever_id: str
    reliever_name: str
    k_pct: float = 0.28  # Strikeout rate (e.g. 28%)
    bb_pct: float = 0.08  # Walk rate (e.g. 8%)
    hr_per_9: float = 0.85  # Home runs per 9 IP
    high_leverage_wpa: float = 1.25  # Win Probability Added in high-leverage spots (LI >= 1.5)
    save_opportunities: int = 25


@dataclasses.dataclass(frozen=True)
class CloserVolatilityEvaluation:
    """Evaluated closer volatility score, blown-save probability, and lockdown grade."""

    reliever_name: str
    volatility_index: float  # 0 to 100 (lower = more reliable/lockdown, higher = cardiac/volatile)
    expected_save_conversion_pct: float  # e.g. 92.5%
    wpa_per_leverage_efficiency: float
    closer_tier: str  # "LOCKDOWN_ELITE", "SOLID", "CARDIAC_HIGH_VOLATILITY"
    is_lockdown_closer: bool


class BaseLeverageEngine(Protocol):
    """Polymorphic protocol for bullpen leverage engines."""

    def evaluate_closer_reliability(
        self,
        profile: RelieverLeverageProfile,
    ) -> CloserVolatilityEvaluation:
        """Calculate blown save volatility score and save conversion rate."""
        ...


class BullpenLeverageEngine:
    """Calculates reliever leverage win probability preservation and closer volatility (LEV-01)."""

    def evaluate_closer_reliability(
        self,
        profile: RelieverLeverageProfile,
    ) -> CloserVolatilityEvaluation:
        """Compute closer volatility index and expected save conversion."""
        # 1. Volatility Index Formulation:
        # High K% suppresses balls in play and baserunners -> reduces volatility
        # High BB% and HR/9 create sudden blown leads -> expands volatility
        k_factor = max(0.10, profile.k_pct)
        risk_components = (profile.bb_pct * 2.2) + (profile.hr_per_9 * 0.08)
        raw_volatility = (risk_components / (k_factor * 1.5)) * 50.0
        volatility_score = float(np.clip(raw_volatility, 10.0, 95.0))

        # 2. Expected Save Conversion Rate in 1-run 9th inning leads:
        # Baseline elite closer ~ 92-95%, volatile closer ~ 78-83%
        save_pct = float(np.clip(96.0 - (volatility_score * 0.20), 75.0, 98.0))

        # 3. WPA efficiency per unit leverage
        wpa_eff = round(profile.high_leverage_wpa / max(5, profile.save_opportunities), 3)

        # 4. Closer tier
        if volatility_score <= 35.0 and save_pct >= 90.0:
            tier = "LOCKDOWN_ELITE"
            is_lockdown = True
        elif volatility_score >= 60.0:
            tier = "CARDIAC_HIGH_VOLATILITY"
            is_lockdown = False
        else:
            tier = "SOLID"
            is_lockdown = False

        return CloserVolatilityEvaluation(
            reliever_name=profile.reliever_name,
            volatility_index=round(volatility_score, 1),
            expected_save_conversion_pct=round(save_pct, 1),
            wpa_per_leverage_efficiency=wpa_eff,
            closer_tier=tier,
            is_lockdown_closer=is_lockdown,
        )


def health_check() -> list[Check]:
    """Operational health check for the Bullpen Leverage Engine (LEV-01)."""
    checks: list[Check] = []
    try:
        engine = BullpenLeverageEngine()
        lockdown = RelieverLeverageProfile(
            "r1", "Lockdown Closer", k_pct=0.36, bb_pct=0.05, hr_per_9=0.50
        )
        volatile = RelieverLeverageProfile(
            "r2", "Wild Reliever", k_pct=0.20, bb_pct=0.14, hr_per_9=1.40
        )

        r_lock = engine.evaluate_closer_reliability(lockdown)
        r_vol = engine.evaluate_closer_reliability(volatile)

        if r_lock.is_lockdown_closer and r_vol.volatility_index > r_lock.volatility_index:
            checks.append(
                Check(
                    "bullpen leverage engine",
                    True,
                    f"Leverage verified (Vol: {r_lock.volatility_index:.1f})",
                )
            )
        else:
            checks.append(
                Check(
                    "bullpen leverage engine",
                    False,
                    f"Unexpected leverage evaluation: {r_lock}, {r_vol}",
                )
            )
    except Exception as exc:
        checks.append(Check("bullpen leverage engine", False, str(exc)))
    return checks
