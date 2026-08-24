"""Late-Inning Pinch-Hit & Substitution Tactical Simulator (SUB-01, ADR-141)."""

from __future__ import annotations

import dataclasses
from collections.abc import Sequence
from typing import Protocol

from mlb_baseball.health import Check


@dataclasses.dataclass(frozen=True)
class BatterCard:
    """Player offensive talent profile by opposing pitcher handedness."""

    player_id: str
    player_name: str
    bats: str  # "R", "L", "S"
    woba_vs_rhp: float = 0.320
    woba_vs_lhp: float = 0.320
    is_defense_first: bool = False


@dataclasses.dataclass(frozen=True)
class PinchHitRecommendation:
    """Evaluated manager tactical substitution decision."""

    should_substitute: bool
    current_batter_name: str
    opposing_pitcher_hand: str
    recommended_substitute_id: str | None
    recommended_substitute_name: str | None
    expected_woba_gain: float
    leverage_index: float
    rationale: str


class BaseSubstitutionEngine(Protocol):
    """Polymorphic protocol for substitution engines."""

    def evaluate_pinch_hit(
        self,
        current_batter: BatterCard,
        opposing_pitcher_hand: str,
        bench_players: Sequence[BatterCard],
        inning: int = 8,
        leverage_index: float = 1.5,
    ) -> PinchHitRecommendation:
        """Evaluate whether to pinch-hit and select the optimal bench player."""
        ...


class TacticalSubstitutionEngine:
    """Simulates manager late-inning pinch-hit decisions and bench optimization (SUB-01)."""

    def evaluate_pinch_hit(
        self,
        current_batter: BatterCard,
        opposing_pitcher_hand: str,
        bench_players: Sequence[BatterCard],
        inning: int = 8,
        leverage_index: float = 1.5,
    ) -> PinchHitRecommendation:
        """Evaluate pinch-hit leverage threshold and find optimal bench substitute."""
        hand = opposing_pitcher_hand.upper()

        # Current batter talent vs this pitcher hand
        current_woba = current_batter.woba_vs_lhp if hand == "L" else current_batter.woba_vs_rhp

        # Late-inning high-leverage threshold
        is_late_inning = inning >= 7
        is_high_leverage = leverage_index >= 1.2

        if not is_late_inning or not bench_players:
            return PinchHitRecommendation(
                should_substitute=False,
                current_batter_name=current_batter.player_name,
                opposing_pitcher_hand=hand,
                recommended_substitute_id=None,
                recommended_substitute_name=None,
                expected_woba_gain=0.0,
                leverage_index=leverage_index,
                rationale="Early inning or empty bench; let starter hit.",
            )

        # Evaluate candidate bench players
        best_candidate: BatterCard | None = None
        best_gain = 0.0

        for bench in bench_players:
            cand_woba = bench.woba_vs_lhp if hand == "L" else bench.woba_vs_rhp
            gain = cand_woba - current_woba

            # Require minimum +0.025 wOBA gain to justify burning bench player
            # In low leverage, require +0.050; in high leverage (LI >= 2.0), accept +0.020
            min_gain_threshold = 0.020 if is_high_leverage else 0.045

            if gain > min_gain_threshold and gain > best_gain:
                best_gain = gain
                best_candidate = bench

        if best_candidate is not None:
            return PinchHitRecommendation(
                should_substitute=True,
                current_batter_name=current_batter.player_name,
                opposing_pitcher_hand=hand,
                recommended_substitute_id=best_candidate.player_id,
                recommended_substitute_name=best_candidate.player_name,
                expected_woba_gain=round(best_gain, 3),
                leverage_index=leverage_index,
                rationale=(
                    f"Pinch-hit {best_candidate.player_name} ({best_candidate.bats}) vs {hand}HP "
                    f"in Inning {inning} (LI: {leverage_index:.1f}, wOBA gain: +{best_gain:.3f})."
                ),
            )

        return PinchHitRecommendation(
            should_substitute=False,
            current_batter_name=current_batter.player_name,
            opposing_pitcher_hand=hand,
            recommended_substitute_id=None,
            recommended_substitute_name=None,
            expected_woba_gain=0.0,
            leverage_index=leverage_index,
            rationale="No bench player provides sufficient wOBA upgrade.",
        )


def health_check() -> list[Check]:
    """Operational health check for the Tactical Substitution Engine (SUB-01)."""
    checks: list[Check] = []
    try:
        engine = TacticalSubstitutionEngine()
        weak_vs_lhp = BatterCard(
            "b1", "Defense Catcher", bats="L", woba_vs_rhp=0.310, woba_vs_lhp=0.220
        )
        bench_power = BatterCard("b2", "Power DH", bats="R", woba_vs_rhp=0.330, woba_vs_lhp=0.370)

        rec = engine.evaluate_pinch_hit(
            current_batter=weak_vs_lhp,
            opposing_pitcher_hand="L",
            bench_players=[bench_power],
            inning=8,
            leverage_index=2.1,
        )

        if rec.should_substitute and rec.expected_woba_gain > 0.10:
            checks.append(
                Check(
                    "tactical substitution engine",
                    True,
                    f"Pinch hit verified (+{rec.expected_woba_gain:.3f} wOBA)",
                )
            )
        else:
            checks.append(
                Check(
                    "tactical substitution engine", False, f"Unexpected substitution result: {rec}"
                )
            )
    except Exception as exc:
        checks.append(Check("tactical substitution engine", False, str(exc)))
    return checks
