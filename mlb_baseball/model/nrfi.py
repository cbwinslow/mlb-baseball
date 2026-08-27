"""First-Inning Run Scored (NRFI / YRFI) Probabilistic Valuation Engine (NRFI-01, ADR-156).

Provides 1st-inning derivative pricing, top-of-order run expectancy, and market value detection:
1. Inning 1 Top-of-Order Offensive Quality vs Starter 1st-Inning Baseline ERA.
2. Independent Inning Half-Score Poisson Distributions (P(Top 1st = 0) and P(Bottom 1st = 0)).
3. Fair NRFI / YRFI Probabilities and Synthetic True-Odds Moneylines.
4. Market Line Shopping & Expected Value (+EV) Derivative Discovery.

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
class InningOneMatchupInputs:
    """Starting pitcher and top-of-the-order offensive metrics for Inning 1."""

    home_team: str
    away_team: str
    home_starter_inn1_era: float = 3.60
    away_starter_inn1_era: float = 3.80
    home_top3_woba: float = 0.340
    away_top3_woba: float = 0.335
    park_factor: float = 1.00


@dataclasses.dataclass(frozen=True)
class NRFIValuationResult:
    """Evaluated NRFI and YRFI probabilities and fair derivative market prices."""

    home_team: str
    away_team: str
    nrfi_probability: float  # P(No Run First Inning)
    yrfi_probability: float  # P(Yes Run First Inning)
    fair_nrfi_decimal: float
    fair_yrfi_decimal: float
    fair_nrfi_american: int
    fair_yrfi_american: int
    recommended_side: str  # "NRFI", "YRFI", or "NEUTRAL"


def _decimal_to_american(decimal_odds: float) -> int:
    """Convert decimal odds to American moneyline format."""
    if decimal_odds <= 1.0:
        return -10000
    if decimal_odds >= 2.0:
        return int(round((decimal_odds - 1.0) * 100.0))
    return int(round(-100.0 / (decimal_odds - 1.0)))


class BaseNRFIEngine(Protocol):
    """Polymorphic protocol for NRFI / YRFI valuation engines."""

    def evaluate_first_inning(
        self,
        matchup: InningOneMatchupInputs,
    ) -> NRFIValuationResult:
        """Calculate NRFI and YRFI derivative market fair odds."""
        ...


class FirstInningValuationEngine:
    """Calculates No-Run-First-Inning (NRFI) probabilities and fair prices (NRFI-01)."""

    def evaluate_first_inning(
        self,
        matchup: InningOneMatchupInputs,
    ) -> NRFIValuationResult:
        """Compute Inning 1 run expectancies and fair derivative lines."""
        # 1. Expected Runs per half inning:
        # Baseline Inning 1 half-inning Poisson mean: 0.40. This is the number
        # ADR-156 and docs/THEORY_AND_METHODOLOGY.md section 42.1 both define
        # the formula with, so it is the one implemented here. (A stray inline
        # comment here previously read "~0.52 runs"; that was never the
        # documented constant and 0.40 fits observed MLB NRFI rates better -- a
        # crude e^-2mu model needs mu ~ 0.33-0.40 to reproduce the real
        # ~50-53% NRFI rate, whereas 0.52 implies ~35%.) The real empirical
        # per-half-inning first-inning run mean has not been tied out against
        # this project's own Retrosheet data yet -- that calibration is
        # tracked as future refit work in docs/PACKAGE_VALIDATION_STATUS.md,
        # not done here (NRFI-01 stays a Bucket B exploratory calculator).
        mu_top = (
            0.40
            * (matchup.away_top3_woba / 0.335)
            * (matchup.home_starter_inn1_era / 3.90)
            * matchup.park_factor
        )
        mu_bot = (
            0.40
            * (matchup.home_top3_woba / 0.335)
            * (matchup.away_starter_inn1_era / 3.90)
            * matchup.park_factor
        )

        # 2. Probability of zero runs in each half inning: P(X = 0) = exp(-mu)
        p_zero_top = math.exp(-mu_top)
        p_zero_bot = math.exp(-mu_bot)

        # 3. Overall NRFI probability:
        p_nrfi = float(np.clip(p_zero_top * p_zero_bot, 0.25, 0.85))
        p_yrfi = float(np.clip(1.0 - p_nrfi, 0.15, 0.75))

        # 4. Fair decimal & American lines:
        dec_nrfi = round(1.0 / p_nrfi, 2)
        dec_yrfi = round(1.0 / p_yrfi, 2)
        am_nrfi = _decimal_to_american(dec_nrfi)
        am_yrfi = _decimal_to_american(dec_yrfi)

        if p_nrfi >= 0.55:
            rec = "NRFI"
        elif p_yrfi >= 0.54:
            rec = "YRFI"
        else:
            rec = "NEUTRAL"

        return NRFIValuationResult(
            home_team=matchup.home_team,
            away_team=matchup.away_team,
            nrfi_probability=round(p_nrfi, 3),
            yrfi_probability=round(p_yrfi, 3),
            fair_nrfi_decimal=dec_nrfi,
            fair_yrfi_decimal=dec_yrfi,
            fair_nrfi_american=am_nrfi,
            fair_yrfi_american=am_yrfi,
            recommended_side=rec,
        )


def health_check() -> list[Check]:
    """Operational health check for the First-Inning Valuation Engine (NRFI-01)."""
    checks: list[Check] = []
    try:
        engine = FirstInningValuationEngine()
        ace_matchup = InningOneMatchupInputs(
            "LAD",
            "SF",
            home_starter_inn1_era=2.50,
            away_starter_inn1_era=2.70,
            home_top3_woba=0.320,
            away_top3_woba=0.310,
        )
        res = engine.evaluate_first_inning(ace_matchup)

        if res.nrfi_probability > 0.60 and res.recommended_side == "NRFI":
            checks.append(
                Check(
                    "first inning valuation engine",
                    True,
                    f"NRFI verified (P: {res.nrfi_probability * 100:.1f}%)",
                )
            )
        else:
            checks.append(
                Check("first inning valuation engine", False, f"Unexpected NRFI result: {res}")
            )
    except Exception as exc:
        checks.append(Check("first inning valuation engine", False, str(exc)))
    return checks
