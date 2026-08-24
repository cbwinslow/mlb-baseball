"""Batter Contact-Type Expected Slugging & ISO Power Engine (XSLG-01, ADR-187).

Provides contact quality binning, expected slugging (xSLG), and isolated power (xISO) modeling:
1. Contact Type Binning (Barrels, Solid Contact, Flare/Burner, Under, Topped, Weak).
2. Expected Slugging Percentage (xSLG) and Expected Isolated Power (xISO = xSLG - xBA).
3. True Power Conversion Efficiency (TPCE = Actual ISO / Expected xISO).
4. Power Profile Tiers (Elite Barrel Slugger, Undervalued Power Ceiling, Contact Overachiever).

Adheres strictly to object-oriented encapsulation, polymorphic protocols, and
point-in-time correctness with zero lookahead leakage.
"""

from __future__ import annotations

import dataclasses
from typing import Protocol

from mlb_baseball.health import Check


@dataclasses.dataclass(frozen=True)
class BatterContactBins:
    """Observed Statcast contact quality bin counts and observed power metrics."""

    batter_id: str
    batter_name: str
    barrel_count: int = 25
    solid_contact_count: int = 18
    flare_burner_count: int = 32
    under_count: int = 22
    topped_count: int = 38
    weak_count: int = 15
    total_bbe: int = 150
    actual_iso: float = 0.220


@dataclasses.dataclass(frozen=True)
class XSLGEvaluationResult:
    """Evaluated expected slugging, expected ISO, and power conversion efficiency."""

    batter_name: str
    expected_xslg: float
    expected_xiso: float
    actual_iso: float
    tpce_efficiency_pct: float  # (Actual ISO / Expected xISO) * 100%
    power_tier: str  # e.g. "ELITE_BARREL_SLUGGER", "UNDERVALUED_POWER_CEILING"
    is_elite_slugger: bool


class BaseXSLGEngine(Protocol):
    """Polymorphic protocol for expected slugging and ISO power engines."""

    def evaluate_power(
        self,
        bins: BatterContactBins,
    ) -> XSLGEvaluationResult:
        """Calculate xSLG, xISO, and power conversion efficiency."""
        ...


class XSLGPowerEngine:
    """Calculates expected slugging percentage and isolated power (XSLG-01)."""

    def evaluate_power(
        self,
        bins: BatterContactBins,
    ) -> XSLGEvaluationResult:
        """Compute contact-binned xSLG, xISO, and TPCE."""
        tot = max(
            1,
            bins.total_bbe,
            bins.barrel_count
            + bins.solid_contact_count
            + bins.flare_burner_count
            + bins.under_count
            + bins.topped_count
            + bins.weak_count,
        )

        # 1. Expected Slugging (xSLG) and Expected Batting Average (xBA)
        xslg = (
            bins.barrel_count * 2.500
            + bins.solid_contact_count * 1.250
            + bins.flare_burner_count * 0.650
            + bins.under_count * 0.180
            + bins.topped_count * 0.150
            + bins.weak_count * 0.100
        ) / tot
        xslg = round(xslg, 3)

        xba = (
            bins.barrel_count * 0.750
            + bins.solid_contact_count * 0.520
            + bins.flare_burner_count * 0.620
            + bins.under_count * 0.120
            + bins.topped_count * 0.180
            + bins.weak_count * 0.100
        ) / tot
        xba = round(xba, 3)

        # Scale per-BBE ISO to per-PA ISO using baseline in-play rate (0.68)
        xiso_bbe = max(0.0, xslg - xba)
        xiso = round(xiso_bbe * 0.68, 3)

        # 2. True Power Conversion Efficiency (TPCE)
        denom = max(0.050, xiso)
        tpce = round((bins.actual_iso / denom) * 100.0, 1)

        # 3. Elite Flag & Power Tiers
        is_elite = xiso >= 0.250 and bins.barrel_count / tot >= 0.14 and tpce >= 80.0

        if xiso >= 0.220 and tpce <= 80.0:
            tier = "UNDERVALUED_POWER_CEILING"
        elif is_elite:
            tier = "ELITE_BARREL_SLUGGER"
        elif tpce >= 125.0:
            tier = "CONTACT_OVERACHIEVER"
        else:
            tier = "AVERAGE"

        return XSLGEvaluationResult(
            batter_name=bins.batter_name,
            expected_xslg=xslg,
            expected_xiso=xiso,
            actual_iso=bins.actual_iso,
            tpce_efficiency_pct=tpce,
            power_tier=tier,
            is_elite_slugger=is_elite,
        )


def health_check() -> list[Check]:
    """Operational health check for XSLG & ISO Power Engine (XSLG-01)."""
    checks: list[Check] = []
    try:
        engine = XSLGPowerEngine()
        judge = BatterContactBins("b1", "Aaron Judge Archetype", 35, 22, 28, 15, 30, 10, 140, 0.350)
        unlucky = BatterContactBins("b2", "Unlucky Slugger", 28, 20, 30, 18, 32, 12, 140, 0.170)

        r_jud = engine.evaluate_power(judge)
        r_unl = engine.evaluate_power(unlucky)

        if (
            r_jud.power_tier == "ELITE_BARREL_SLUGGER"
            and r_unl.power_tier == "UNDERVALUED_POWER_CEILING"
        ):
            checks.append(
                Check(
                    "xslg power engine",
                    True,
                    f"xSLG verified (Judge xISO: {r_jud.expected_xiso:.3f})",
                )
            )
        else:
            checks.append(
                Check("xslg power engine", False, f"Unexpected xSLG output: {r_jud}, {r_unl}")
            )
    except Exception as exc:
        checks.append(Check("xslg power engine", False, str(exc)))
    return checks
