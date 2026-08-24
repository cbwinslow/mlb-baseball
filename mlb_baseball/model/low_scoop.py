"""Catcher Low-Pitch Scoop & Bottom-Zone Framing Lift Engine (LOW-SCOOP-01, ADR-225).

Provides borderline low-pitch framing conversion, upward glove scoop velocity, and run value:
1. Bottom-Zone Scoop Framing Rating (BZSFR score measuring low shadow strike theft).
2. Low-Zone Framing Surplus Runs (LZFS net runs saved from converted low strikes).
3. Framing Archetypes (Elite Low-Zone Lifter, Stab-Down Glove-Dropping Liability).

Adheres strictly to object-oriented encapsulation, polymorphic protocols, and
point-in-time correctness with zero lookahead leakage.
"""

from __future__ import annotations

import dataclasses
from typing import Protocol

from mlb_baseball.health import Check


@dataclasses.dataclass(frozen=True)
class CatcherLowScoopMetrics:
    """Observed catcher low-shadow strike rate, upward scoop speed, and glove drop %."""

    catcher_id: str
    catcher_name: str
    low_zone_called_strike_pct: float = 48.0  # Strike % at z in [1.4, 1.7] ft (benchmark ~48.0%)
    upward_scoop_speed_fps: float = 3.5  # Glove upward receiving velocity (benchmark ~3.5 ft/s)
    glove_drop_rate_pct: float = 20.0  # Glove drop before catch % (benchmark ~20.0%)
    low_zone_opportunities: int = 200


@dataclasses.dataclass(frozen=True)
class LowScoopEvaluationResult:
    """Evaluated bottom-zone framing score, surplus strikes, and LZFS runs saved."""

    catcher_name: str
    bzsfr_score: float  # Bottom-Zone Scoop Framing Rating (0 to 160)
    extra_strikes_created: float  # Extra strikes won above 48.0% benchmark
    lzfs_runs_saved: float  # Net defensive runs saved from low framing
    framing_tier: str  # e.g. "ELITE_LOW_ZONE_LIFTER", "STAB_DOWN_GLOVE_DROPPING_LIABILITY"
    is_elite_lifter: bool


class BaseLowScoopEngine(Protocol):
    """Polymorphic protocol for bottom-zone scoop framing engines."""

    def evaluate_low_scoop(
        self,
        metrics: CatcherLowScoopMetrics,
    ) -> LowScoopEvaluationResult:
        """Calculate BZSFR rating, extra strikes, and LZFS runs."""
        ...


class CatcherLowScoopEngine:
    """Calculates bottom-zone scoop framing conversion, scoop speed, and LZFS (LOW-SCOOP-01)."""

    def evaluate_low_scoop(
        self,
        metrics: CatcherLowScoopMetrics,
    ) -> LowScoopEvaluationResult:
        """Compute BZSFR score and low-zone defensive runs saved."""
        # BZSFR Score: benchmark 48.0% strike, 3.5 ft/s scoop, 20.0% glove drop
        strike_bonus = (metrics.low_zone_called_strike_pct - 48.0) * 2.2
        speed_bonus = (metrics.upward_scoop_speed_fps - 3.5) * 12.0
        drop_saving = (20.0 - metrics.glove_drop_rate_pct) * 1.1
        bzsfr = round(max(0.0, 100.0 + strike_bonus + speed_bonus + drop_saving), 1)

        # Extra strikes & LZFS runs (~0.125 runs per strike converted)
        opps = max(1, metrics.low_zone_opportunities)
        extra_strikes = round(((metrics.low_zone_called_strike_pct - 48.0) / 100.0) * opps, 1)
        lzfs = round(extra_strikes * 0.125, 2)

        is_lifter = (
            bzsfr >= 116.0
            and metrics.low_zone_called_strike_pct >= 57.0
            and metrics.upward_scoop_speed_fps >= 4.2
        )

        # Tiers
        if is_lifter:
            tier = "ELITE_LOW_ZONE_LIFTER"
        elif metrics.low_zone_called_strike_pct <= 38.0 or metrics.glove_drop_rate_pct >= 32.0:
            tier = "STAB_DOWN_GLOVE_DROPPING_LIABILITY"
        elif metrics.low_zone_called_strike_pct >= 53.0:
            tier = "SOLID_LOW_PITCH_FRAMER"
        else:
            tier = "AVERAGE_LOW_ZONE_FRAMER"

        return LowScoopEvaluationResult(
            catcher_name=metrics.catcher_name,
            bzsfr_score=bzsfr,
            extra_strikes_created=extra_strikes,
            lzfs_runs_saved=lzfs,
            framing_tier=tier,
            is_elite_lifter=is_lifter,
        )


def health_check() -> list[Check]:
    """Operational health check for Catcher Low Scoop Engine (LOW-SCOOP-01)."""
    checks: list[Check] = []
    try:
        engine = CatcherLowScoopEngine()
        lifter = CatcherLowScoopMetrics("c1", "Patrick Bailey", 65.0, 4.8, 8.0, 240)
        stabber = CatcherLowScoopMetrics("c2", "Poor Low Receiver", 36.0, 2.4, 35.0, 180)

        r_lif = engine.evaluate_low_scoop(lifter)
        r_sta = engine.evaluate_low_scoop(stabber)

        if (
            r_lif.framing_tier == "ELITE_LOW_ZONE_LIFTER"
            and r_sta.framing_tier == "STAB_DOWN_GLOVE_DROPPING_LIABILITY"
        ):
            checks.append(
                Check(
                    "low scoop engine",
                    True,
                    f"Low Scoop verified (Bailey BZSFR: {r_lif.bzsfr_score:.1f})",
                )
            )
        else:
            checks.append(
                Check("low scoop engine", False, f"Unexpected low scoop output: {r_lif}, {r_sta}")
            )
    except Exception as exc:
        checks.append(Check("low scoop engine", False, str(exc)))
    return checks
