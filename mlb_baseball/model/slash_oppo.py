"""Batter Opposite Field Slash & Anti-Shift Engine (SLASH-OPPO-01, ADR-219).

Provides opposite-field spray, pull-side groundball avoidance, and anti-shift modeling:
1. Opposite Field Slash Resilience Rating (OFSRR score measuring all-fields directional control).
2. Anti-Shift BABIP Adjustment (delta_BABIP expected gain from punching through vacated zones).
3. Slash Archetypes (Elite All-Fields Slash Artist, Extreme Pull Shift Bait, Weak Flare Slapper).

Adheres strictly to object-oriented encapsulation, polymorphic protocols, and
point-in-time correctness with zero lookahead leakage.
"""

from __future__ import annotations

import dataclasses
from typing import Protocol

from mlb_baseball.health import Check


@dataclasses.dataclass(frozen=True)
class BatterSlashOppoMetrics:
    """Observed batter opposite-field contact rate, oppo LD%, and pull GB%."""

    batter_id: str
    batter_name: str
    oppo_contact_pct: float = 24.0  # Opposite field spray % (benchmark ~24.0%)
    oppo_line_drive_pct: float = 20.0  # Line drive % on oppo hits (benchmark ~20.0%)
    pull_groundball_pct: float = 64.0  # Pull % on groundballs (benchmark ~64.0%)
    total_bbe_count: int = 250


@dataclasses.dataclass(frozen=True)
class SlashOppoEvaluationResult:
    """Evaluated opposite-field slash rating, expected BABIP boost, and run production."""

    batter_name: str
    ofsrr_score: float  # Opposite Field Slash Resilience Rating (0 to 160)
    babip_adjustment: float  # Expected delta in BABIP
    ofsrv_runs_saved: float  # Net offensive run production from directional spray
    slash_tier: str  # e.g. "ELITE_ALL_FIELDS_SLASH_ARTIST", "EXTREME_PULL_SHIFT_BAIT"
    is_slash_artist: bool


class BaseSlashOppoEngine(Protocol):
    """Polymorphic protocol for opposite field slash engines."""

    def evaluate_slash(
        self,
        metrics: BatterSlashOppoMetrics,
    ) -> SlashOppoEvaluationResult:
        """Calculate OFSRR score, BABIP adjustment, and run production."""
        ...


class BatterSlashOppoEngine:
    """Calculates opposite-field spray control, BABIP boost, and run value (SLASH-OPPO-01)."""

    def evaluate_slash(
        self,
        metrics: BatterSlashOppoMetrics,
    ) -> SlashOppoEvaluationResult:
        """Compute OFSRR rating, expected BABIP gain, and offensive runs."""
        # OFSRR Score: benchmark 24.0% oppo, 20.0% oppo LD, 64.0% pull GB
        oppo_bonus = (metrics.oppo_contact_pct - 24.0) * 2.6
        ld_bonus = (metrics.oppo_line_drive_pct - 20.0) * 2.2
        pull_gb_saving = (64.0 - metrics.pull_groundball_pct) * 1.4
        ofsrr = round(max(0.0, 100.0 + oppo_bonus + ld_bonus + pull_gb_saving), 1)

        # Expected BABIP Boost & Run Value: ~0.00065 BABIP per point above 100
        delta_babip = round((ofsrr - 100.0) * 0.00065, 3)
        bbe = max(1, metrics.total_bbe_count)
        ofsrv = round(delta_babip * bbe * 0.45, 2)

        is_artist = (
            ofsrr >= 116.0
            and metrics.oppo_contact_pct >= 29.0
            and metrics.pull_groundball_pct <= 56.0
        )

        # Tiers
        if is_artist:
            tier = "ELITE_ALL_FIELDS_SLASH_ARTIST"
        elif metrics.pull_groundball_pct >= 72.0 and metrics.oppo_contact_pct <= 19.0:
            tier = "EXTREME_PULL_SHIFT_BAIT"
        elif metrics.oppo_contact_pct >= 29.0 and metrics.oppo_line_drive_pct <= 14.0:
            tier = "WEAK_OPPO_FLARE_SLAPPER"
        else:
            tier = "AVERAGE_SPRAY_DISPERSAL"

        return SlashOppoEvaluationResult(
            batter_name=metrics.batter_name,
            ofsrr_score=ofsrr,
            babip_adjustment=delta_babip,
            ofsrv_runs_saved=ofsrv,
            slash_tier=tier,
            is_slash_artist=is_artist,
        )


def health_check() -> list[Check]:
    """Operational health check for Batter Slash Oppo Engine (SLASH-OPPO-01)."""
    checks: list[Check] = []
    try:
        engine = BatterSlashOppoEngine()
        artist = BatterSlashOppoMetrics("b1", "Luis Arraez", 34.0, 28.0, 48.0, 320)
        pull_bait = BatterSlashOppoMetrics("b2", "Pull Only Hitter", 16.0, 18.0, 76.0, 260)

        r_art = engine.evaluate_slash(artist)
        r_pul = engine.evaluate_slash(pull_bait)

        if (
            r_art.slash_tier == "ELITE_ALL_FIELDS_SLASH_ARTIST"
            and r_pul.slash_tier == "EXTREME_PULL_SHIFT_BAIT"
        ):
            checks.append(
                Check(
                    "slash oppo engine",
                    True,
                    f"Slash Oppo verified (Arraez OFSRR: {r_art.ofsrr_score:.1f})",
                )
            )
        else:
            checks.append(
                Check("slash oppo engine", False, f"Unexpected slash oppo output: {r_art}, {r_pul}")
            )
    except Exception as exc:
        checks.append(Check("slash oppo engine", False, str(exc)))
    return checks
