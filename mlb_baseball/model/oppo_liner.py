"""Batter Opposite-Field Line Drive Sinking Liners Engine (OPPO-LINER-01, ADR-251).

Provides opposite field line drive rate, BABIP efficiency, and OFLDII index:
1. Opposite Field Line Drive Impact Index (OFLDII score measuring oppo line drive mastery).
2. Opposite Line Drive Production Runs (OLPR net offensive runs produced).
3. Opposite Line Drive Archetypes (Surgical Oppo Line Drive Artist, Weak Oppo Flare).

Adheres strictly to object-oriented encapsulation, polymorphic protocols, and
point-in-time correctness with zero lookahead leakage.
"""

from __future__ import annotations

import dataclasses
from typing import Protocol

from mlb_baseball.health import Check


@dataclasses.dataclass(frozen=True)
class BatterOppoLinerMetrics:
    """Observed opposite field line drive %, BABIP, and hard-hit rate."""

    batter_id: str
    batter_name: str
    oppo_line_drive_pct: float = 20.0  # Line drive % on oppo contact (benchmark ~20.0%)
    oppo_liner_babip: float = 0.620  # BABIP on oppo line drives (benchmark ~0.620)
    oppo_liner_hard_hit_pct: float = 40.0  # Hard-hit % on oppo line drives (benchmark ~40.0%)
    oppo_contact_events: int = 120


@dataclasses.dataclass(frozen=True)
class OppoLinerEvaluationResult:
    """Evaluated oppo line drive score, runs produced, and liner tier."""

    batter_name: str
    ofldii_score: float  # Opposite Field Line Drive Impact Index (0 to 160)
    olpr_runs_produced: float  # Net offensive runs produced via oppo line drives
    liner_tier: str  # e.g. "SURGICAL_OPPOSITE_FIELD_LINE_DRIVE_ARTIST"
    is_line_drive_artist: bool


class BaseOppoLinerEngine(Protocol):
    """Polymorphic protocol for opposite field line drive engines."""

    def evaluate_oppo_liner(
        self,
        metrics: BatterOppoLinerMetrics,
    ) -> OppoLinerEvaluationResult:
        """Calculate OFLDII rating, OLPR runs, and liner tier."""
        ...


class BatterOppoLinerEngine:
    """Calculates opposite field line drive rate, BABIP, and OFLDII (OPPO-LINER-01)."""

    def evaluate_oppo_liner(
        self,
        metrics: BatterOppoLinerMetrics,
    ) -> OppoLinerEvaluationResult:
        """Compute OFLDII score and net offensive runs produced."""
        # OFLDII Score: benchmark 20.0% LD, 0.620 BABIP, 40.0% hard hit
        ld_bonus = (metrics.oppo_line_drive_pct - 20.0) * 2.0
        babip_bonus = (metrics.oppo_liner_babip - 0.620) * 50.0
        hard_bonus = (metrics.oppo_liner_hard_hit_pct - 40.0) * 1.2
        ofldii = round(max(0.0, 100.0 + ld_bonus + babip_bonus + hard_bonus), 1)

        # OLPR Runs (~0.0030 runs per contact event per point above 100)
        events = max(1, metrics.oppo_contact_events)
        runs = round((ofldii - 100.0) * (events * 0.0030), 2)

        is_artist = (
            ofldii >= 116.0
            and metrics.oppo_line_drive_pct >= 26.0
            and metrics.oppo_liner_babip >= 0.680
        )

        # Tiers
        if is_artist:
            tier = "SURGICAL_OPPOSITE_FIELD_LINE_DRIVE_ARTIST"
        elif metrics.oppo_line_drive_pct <= 14.0 or metrics.oppo_liner_babip <= 0.520:
            tier = "ROLLOVER_WEAK_OPPO_FLARE_LIABILITY"
        elif metrics.oppo_line_drive_pct >= 23.0:
            tier = "SOLID_OPPO_SPRAY_HITTER"
        else:
            tier = "AVERAGE_OPPOSITE_FIELD_LINE_DRIVE_PROFILE"

        return OppoLinerEvaluationResult(
            batter_name=metrics.batter_name,
            ofldii_score=ofldii,
            olpr_runs_produced=runs,
            liner_tier=tier,
            is_line_drive_artist=is_artist,
        )


def health_check() -> list[Check]:
    """Operational health check for Batter Oppo Liner Engine (OPPO-LINER-01)."""
    checks: list[Check] = []
    try:
        engine = BatterOppoLinerEngine()
        artist = BatterOppoLinerMetrics("b1", "Luis Arraez", 30.0, 0.740, 48.0, 160)
        weak = BatterOppoLinerMetrics("b2", "Weak Flare", 12.0, 0.480, 25.0, 100)

        r_art = engine.evaluate_oppo_liner(artist)
        r_wea = engine.evaluate_oppo_liner(weak)

        if (
            r_art.liner_tier == "SURGICAL_OPPOSITE_FIELD_LINE_DRIVE_ARTIST"
            and r_wea.liner_tier == "ROLLOVER_WEAK_OPPO_FLARE_LIABILITY"
        ):
            checks.append(
                Check(
                    "oppo liner engine",
                    True,
                    f"Oppo Liner verified (Arraez OFLDII: {r_art.ofldii_score:.1f})",
                )
            )
        else:
            checks.append(
                Check(
                    "oppo liner engine",
                    False,
                    f"Unexpected oppo liner output: {r_art}, {r_wea}",
                )
            )
    except Exception as exc:
        checks.append(Check("oppo liner engine", False, str(exc)))
    return checks
