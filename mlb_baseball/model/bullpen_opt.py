"""Live In-Game Bullpen Managerial Optimizer (BULLPEN-OPT-01, ADR-160).

Provides real-time reliever matchup optimization and leverage-stamina tradeoff analysis:
1. In-Game Situational Leverage Index (LI) and Base/Out Urgency Weighting.
2. Upcoming Batter Handedness Matchup Advantage (L-L / R-R platoon suppression).
3. 3-Day Pitch Load and Rest Day Stamina Cost Penalties.
4. Optimal Reliever Ranking and Tactical Warm-up Dispatch.

Adheres strictly to object-oriented encapsulation, polymorphic protocols, and
point-in-time correctness with zero lookahead leakage.
"""

from __future__ import annotations

import dataclasses
from typing import Protocol

from mlb_baseball.health import Check


@dataclasses.dataclass(frozen=True)
class RelieverCandidate:
    """Bullpen arm available in the active bullpen with fatigue metrics."""

    reliever_id: str
    name: str
    throws_hand: str  # "L" or "R"
    rest_days: int = 1
    pitches_last_3d: int = 20
    fip: float = 3.20
    k_pct: float = 0.28
    bb_pct: float = 0.08


@dataclasses.dataclass(frozen=True)
class InGameLeverageSituation:
    """Live state of the game requiring bullpen intervention."""

    inning: int = 8
    score_diff: int = 1  # Defending team lead
    outs: int = 1
    leverage_index: float = 2.40  # High leverage
    upcoming_batters_hand: list[str] = dataclasses.field(default_factory=lambda: ["L", "L", "R"])


@dataclasses.dataclass(frozen=True)
class RelieverOptionScore:
    """Evaluated optimization score and ranking for a bullpen arm."""

    name: str
    rank: int
    net_score: float
    matchup_advantage: float
    fatigue_penalty: float
    recommendation_label: str  # "PRIMARY_INSERTION", "SECONDARY_BACKUP", "AVOID_FATIGUED"


@dataclasses.dataclass(frozen=True)
class BullpenOptimizationResult:
    """Optimal bullpen strategy ranking for the live situation."""

    inning: int
    score_diff: int
    leverage_index: float
    top_recommendation: RelieverOptionScore
    all_rankings: list[RelieverOptionScore]


class BaseBullpenOptimizer(Protocol):
    """Polymorphic protocol for bullpen optimization engines."""

    def optimize_bullpen(
        self,
        situation: InGameLeverageSituation,
        bullpen: list[RelieverCandidate],
    ) -> BullpenOptimizationResult:
        """Rank bullpen candidates for immediate insertion."""
        ...


class BullpenOptimizerEngine:
    """Evaluates bullpen matchup advantages vs fatigue costs (BULLPEN-OPT-01)."""

    def optimize_bullpen(
        self,
        situation: InGameLeverageSituation,
        bullpen: list[RelieverCandidate],
    ) -> BullpenOptimizationResult:
        """Calculate net insertion value across active relievers."""
        if not bullpen:
            raise ValueError("Bullpen cannot be empty")

        scored_arms: list[tuple[float, float, float, RelieverCandidate]] = []

        for arm in bullpen:
            # 1. Matchup advantage: +0.05 for each same-handed batter faced in next 3 batters
            same_hand_count = sum(
                1 for b in situation.upcoming_batters_hand if b == arm.throws_hand
            )
            matchup_adv = same_hand_count * 0.05

            # 2. Talent Quality score
            quality = (4.00 - arm.fip) * 0.08 + (arm.k_pct - arm.bb_pct) * 0.15

            # 3. Fatigue penalty: 3-day pitch count and 0 days rest
            fatigue_pen = (arm.pitches_last_3d / 40.0) * 0.08 + (
                0.06 if arm.rest_days == 0 else 0.0
            )

            # 4. Net score weighted by situation leverage
            net_score = (matchup_adv + quality) * situation.leverage_index - fatigue_pen
            scored_arms.append((net_score, matchup_adv, fatigue_pen, arm))

        # Sort descending by net score
        scored_arms.sort(key=lambda x: x[0], reverse=True)

        rankings: list[RelieverOptionScore] = []
        for i, (score, m_adv, f_pen, arm) in enumerate(scored_arms, start=1):
            if i == 1:
                label = "PRIMARY_INSERTION"
            elif f_pen > 0.10:
                label = "AVOID_FATIGUED"
            else:
                label = "SECONDARY_BACKUP"

            rankings.append(
                RelieverOptionScore(
                    name=arm.name,
                    rank=i,
                    net_score=round(score, 3),
                    matchup_advantage=round(m_adv, 3),
                    fatigue_penalty=round(f_pen, 3),
                    recommendation_label=label,
                )
            )

        return BullpenOptimizationResult(
            inning=situation.inning,
            score_diff=situation.score_diff,
            leverage_index=situation.leverage_index,
            top_recommendation=rankings[0],
            all_rankings=rankings,
        )


def health_check() -> list[Check]:
    """Operational health check for the Bullpen Optimizer Engine (BULLPEN-OPT-01)."""
    checks: list[Check] = []
    try:
        engine = BullpenOptimizerEngine()
        arms = [
            RelieverCandidate(
                "r1", "Lefty Specialist", "L", rest_days=2, pitches_last_3d=10, fip=2.80
            ),
            RelieverCandidate("r2", "Righty Setup", "R", rest_days=0, pitches_last_3d=45, fip=3.50),
        ]
        sit = InGameLeverageSituation(
            inning=8, score_diff=1, leverage_index=2.5, upcoming_batters_hand=["L", "L", "L"]
        )
        res = engine.optimize_bullpen(sit, arms)

        if res.top_recommendation.name == "Lefty Specialist":
            checks.append(
                Check(
                    "bullpen optimizer engine",
                    True,
                    f"Optimizer verified (Top: {res.top_recommendation.name})",
                )
            )
        else:
            checks.append(
                Check("bullpen optimizer engine", False, f"Unexpected optimizer output: {res}")
            )
    except Exception as exc:
        checks.append(Check("bullpen optimizer engine", False, str(exc)))
    return checks
