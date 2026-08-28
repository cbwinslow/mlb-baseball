"""Pitcher Arsenal Diversity & Count-State Game Theory Optimizer (ARSENAL-01, ADR-169).

Provides repertoire depth, Gini-Simpson diversity, and count-specific game theory modeling:
1. Gini-Simpson Arsenal Diversity Index (ADI) across count states (0-0, Behind, 2-Strikes).
2. Shannon Entropy Information Bits per Pitch Selection Repertoire.
3. Over-Reliance Predictability Detection (Primary pitch frequency > 65% in 2-strike counts).
4. Pitcher Repertoire Tiers (Five-Pitch Chameleon, Balanced Mix, Two-Pitch Predictable).

Adheres strictly to object-oriented encapsulation, polymorphic protocols, and
point-in-time correctness with zero lookahead leakage.
"""

from __future__ import annotations

import dataclasses
import math
from typing import Protocol

import numpy as np

from mlb_baseball.health import Check


@dataclasses.dataclass(frozen=True)
class DiversityArsenalMix:
    """Repertoire usage frequencies for a pitcher in a given count context."""

    pitcher_id: str
    pitcher_name: str
    count_state: str = "ALL_COUNTS"  # "0-0", "AHEAD", "BEHIND", "TWO_STRIKES"
    pitch_frequencies: dict[str, float] = dataclasses.field(
        default_factory=lambda: {"FF": 0.45, "SL": 0.25, "CH": 0.18, "CU": 0.12}
    )


@dataclasses.dataclass(frozen=True)
class ArsenalDiversityResult:
    """Evaluated repertoire diversity index, entropy, and predictability."""

    pitcher_name: str
    count_state: str
    pitch_count: int
    diversity_index: float  # Normalized Gini-Simpson Index (0.0 to 1.0)
    entropy_bits: float  # Shannon entropy in bits
    repertoire_tier: str  # "FIVE_PITCH_CHAMELEON", "BALANCED_MIX", "TWO_PITCH_PREDICTABLE"
    is_highly_predictable: bool


class BaseArsenalDiversityEngine(Protocol):
    """Polymorphic protocol for pitcher arsenal diversity engines."""

    def evaluate_diversity(
        self,
        mix: DiversityArsenalMix,
    ) -> ArsenalDiversityResult:
        """Calculate Gini-Simpson diversity and Shannon entropy."""
        ...


class ArsenalDiversityEngine:
    """Calculates pitch mix diversity, entropy, and count predictability (ARSENAL-01)."""

    def evaluate_diversity(
        self,
        mix: DiversityArsenalMix,
    ) -> ArsenalDiversityResult:
        """Compute normalized Gini-Simpson ADI and Shannon entropy."""
        freqs = list(mix.pitch_frequencies.values())
        if not freqs:
            return ArsenalDiversityResult(
                pitcher_name=mix.pitch_name if hasattr(mix, "pitch_name") else mix.pitcher_name,
                count_state=mix.count_state,
                pitch_count=0,
                diversity_index=0.0,
                entropy_bits=0.0,
                repertoire_tier="TWO_PITCH_PREDICTABLE",
                is_highly_predictable=True,
            )

        # Normalize frequencies to sum to 1.0
        total_p = sum(freqs)
        p_norm = [f / total_p for f in freqs if f > 0.0]
        k = len(p_norm)

        # 1. Gini-Simpson Diversity: 1 - sum(p^2)
        sum_p_sq = sum(p**2 for p in p_norm)
        raw_gini = 1.0 - sum_p_sq

        # Normalized to [0, 1] for K classes
        if k > 1:
            norm_adi = (k / (k - 1.0)) * raw_gini
        else:
            norm_adi = 0.0
        adi = round(float(np.clip(norm_adi, 0.0, 1.0)), 2)

        # 2. Shannon Entropy: -sum(p * log2(p))
        entropy = round(sum(-p * math.log2(p) for p in p_norm), 2)

        # 3. Predictability flag: any single pitch > 62% frequency
        max_f = max(p_norm) if p_norm else 1.0
        is_predictable = max_f >= 0.62 or k <= 2

        # 4. Repertoire Tier Classification:
        if k >= 4 and adi >= 0.80:
            tier = "FIVE_PITCH_CHAMELEON"
        elif k >= 3 and adi >= 0.60:
            tier = "BALANCED_MIX"
        else:
            tier = "TWO_PITCH_PREDICTABLE"

        return ArsenalDiversityResult(
            pitcher_name=mix.pitcher_name,
            count_state=mix.count_state,
            pitch_count=k,
            diversity_index=adi,
            entropy_bits=entropy,
            repertoire_tier=tier,
            is_highly_predictable=is_predictable,
        )


def health_check() -> list[Check]:
    """Operational health check for the Arsenal Diversity Engine (ARSENAL-01)."""
    checks: list[Check] = []
    try:
        engine = ArsenalDiversityEngine()
        chameleon = DiversityArsenalMix(
            "p1",
            "Yu Darvish",
            "ALL_COUNTS",
            {"FF": 0.28, "SL": 0.24, "CH": 0.18, "CU": 0.16, "SI": 0.14},
        )
        two_pitch = DiversityArsenalMix(
            "p2", "Reliever Fastball-Slider", "TWO_STRIKES", {"FF": 0.75, "SL": 0.25}
        )

        r_cham = engine.evaluate_diversity(chameleon)
        r_two = engine.evaluate_diversity(two_pitch)

        if r_cham.repertoire_tier == "FIVE_PITCH_CHAMELEON" and r_two.is_highly_predictable:
            checks.append(
                Check(
                    "arsenal diversity engine",
                    True,
                    f"Diversity verified (ADI: {r_cham.diversity_index:.2f})",
                )
            )
        else:
            checks.append(
                Check(
                    "arsenal diversity engine",
                    False,
                    f"Unexpected diversity output: {r_cham}, {r_two}",
                )
            )
    except Exception as exc:
        checks.append(Check("arsenal diversity engine", False, str(exc)))
    return checks
