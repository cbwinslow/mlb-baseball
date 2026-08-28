"""Batter vs. Pitcher (BvP) Arsenal Interaction Engine (BVP-01, ADR-135)."""

from __future__ import annotations

import dataclasses
from typing import Protocol

import numpy as np

from mlb_baseball.health import Check


@dataclasses.dataclass(frozen=True)
class BatterArsenalPreferences:
    """Batter performance run values per 100 pitches across major pitch types."""

    rv_four_seam: float = 0.0  # Runs above average per 100 fastballs
    rv_sinker: float = 0.0
    rv_cutter: float = 0.0
    rv_slider: float = 0.0
    rv_sweeper: float = 0.0
    rv_curveball: float = 0.0
    rv_changeup: float = 0.0
    rv_splitter: float = 0.0


@dataclasses.dataclass(frozen=True)
class PitcherArsenalMix:
    """Pitcher repertoire usage distribution summing to 1.0."""

    pct_four_seam: float = 0.50
    pct_sinker: float = 0.0
    pct_cutter: float = 0.0
    pct_slider: float = 0.30
    pct_sweeper: float = 0.0
    pct_curveball: float = 0.10
    pct_changeup: float = 0.10
    pct_splitter: float = 0.0


@dataclasses.dataclass(frozen=True)
class BvPMatchupResult:
    """Evaluated head-to-head micro-matchup projection."""

    batter_id: str
    batter_name: str
    pitcher_id: str
    pitcher_name: str
    observed_pa: int
    raw_bvp_woba: float
    platoon_prior_woba: float
    shrunk_bvp_woba: float
    arsenal_interaction_rv100: float  # Net run value per 100 pitches based on pitch mix
    composite_matchup_woba: float
    expected_k_pct: float
    expected_bb_pct: float


class BaseBvPEngine(Protocol):
    """Polymorphic protocol for Batter vs Pitcher matchup evaluation."""

    def evaluate_matchup(
        self,
        batter_id: str,
        batter_name: str,
        pitcher_id: str,
        pitcher_name: str,
        batter_woba_vs_hand: float,
        pitcher_woba_vs_hand: float,
        observed_pa: int = 0,
        observed_woba: float = 0.320,
        batter_prefs: BatterArsenalPreferences | None = None,
        pitcher_mix: PitcherArsenalMix | None = None,
    ) -> BvPMatchupResult:
        """Evaluate BvP matchup with empirical Bayes shrinkage and pitch-mix interaction."""
        ...


class EmpiricalBayesBvPEngine:
    """Evaluates BvP micro-matchups with empirical Bayes shrinkage (BVP-01)."""

    SHRINKAGE_PA_CONSTANT = 350.0

    def calculate_log5_platoon_prior(
        self,
        batter_woba: float,
        pitcher_woba: float,
        league_woba: float = 0.315,
    ) -> float:
        """Combine batter and pitcher platoon baselines via odds-ratio Log5 method."""
        b_odds = batter_woba / max(1e-4, 1.0 - batter_woba)
        p_odds = pitcher_woba / max(1e-4, 1.0 - pitcher_woba)
        lg_odds = league_woba / max(1e-4, 1.0 - league_woba)

        matchup_odds = (b_odds * p_odds) / max(1e-4, lg_odds)
        woba_prior = matchup_odds / (1.0 + matchup_odds)
        return float(np.clip(woba_prior, 0.200, 0.480))

    def calculate_arsenal_interaction(
        self,
        prefs: BatterArsenalPreferences,
        mix: PitcherArsenalMix,
    ) -> float:
        """Compute expected net run value per 100 pitches from arsenal overlap."""
        net_rv = (
            (mix.pct_four_seam * prefs.rv_four_seam)
            + (mix.pct_sinker * prefs.rv_sinker)
            + (mix.pct_cutter * prefs.rv_cutter)
            + (mix.pct_slider * prefs.rv_slider)
            + (mix.pct_sweeper * prefs.rv_sweeper)
            + (mix.pct_curveball * prefs.rv_curveball)
            + (mix.pct_changeup * prefs.rv_changeup)
            + (mix.pct_splitter * prefs.rv_splitter)
        )
        return round(float(net_rv), 2)

    def evaluate_matchup(
        self,
        batter_id: str,
        batter_name: str,
        pitcher_id: str,
        pitcher_name: str,
        batter_woba_vs_hand: float,
        pitcher_woba_vs_hand: float,
        observed_pa: int = 0,
        observed_woba: float = 0.320,
        batter_prefs: BatterArsenalPreferences | None = None,
        pitcher_mix: PitcherArsenalMix | None = None,
        league_woba: float = 0.315,
    ) -> BvPMatchupResult:
        """Evaluate BvP matchup with empirical Bayes shrinkage and pitch-mix interaction."""
        # 1. Compute platoon baseline prior
        prior_woba = self.calculate_log5_platoon_prior(
            batter_woba_vs_hand, pitcher_woba_vs_hand, league_woba
        )

        # 2. Empirical Bayes shrinkage over observed head-to-head PA
        if observed_pa > 0:
            weight_sample = observed_pa / (observed_pa + self.SHRINKAGE_PA_CONSTANT)
            shrunk_woba = (weight_sample * observed_woba) + ((1.0 - weight_sample) * prior_woba)
        else:
            shrunk_woba = prior_woba

        # 3. Arsenal interaction adjustment
        prefs = batter_prefs or BatterArsenalPreferences()
        mix = pitcher_mix or PitcherArsenalMix()
        net_rv100 = self.calculate_arsenal_interaction(prefs, mix)

        # 1 run per 100 pitches translates to approx +0.008 wOBA (approx 3.9 pitches per PA)
        # 1.0 RV/100 pitches = ~0.04 Runs/PA -> ~+0.035 wOBA delta
        woba_delta_arsenal = (net_rv100 / 100.0) * 3.5
        composite_woba = float(np.clip(shrunk_woba + woba_delta_arsenal, 0.180, 0.500))

        # Expected K% and BB% derived from composite wOBA
        exp_k = float(np.clip(0.22 - ((composite_woba - league_woba) * 0.40), 0.08, 0.42))
        exp_bb = float(np.clip(0.08 + ((composite_woba - league_woba) * 0.30), 0.02, 0.22))

        return BvPMatchupResult(
            batter_id=batter_id,
            batter_name=batter_name,
            pitcher_id=pitcher_id,
            pitcher_name=pitcher_name,
            observed_pa=observed_pa,
            raw_bvp_woba=round(observed_woba, 3),
            platoon_prior_woba=round(prior_woba, 3),
            shrunk_bvp_woba=round(shrunk_woba, 3),
            arsenal_interaction_rv100=net_rv100,
            composite_matchup_woba=round(composite_woba, 3),
            expected_k_pct=round(exp_k, 3),
            expected_bb_pct=round(exp_bb, 3),
        )


def health_check() -> list[Check]:
    """Operational health check for the BvP Arsenal Interaction Engine (BVP-01)."""
    checks: list[Check] = []
    try:
        engine = EmpiricalBayesBvPEngine()
        # Elite slugger vs tough pitcher with 10 PA noisy sample (.500 wOBA)
        res = engine.evaluate_matchup(
            batter_id="b1",
            batter_name="Slugger",
            pitcher_id="p1",
            pitcher_name="Ace",
            batter_woba_vs_hand=0.370,
            pitcher_woba_vs_hand=0.290,
            observed_pa=10,
            observed_woba=0.500,
            batter_prefs=BatterArsenalPreferences(rv_slider=+1.8),
            pitcher_mix=PitcherArsenalMix(pct_slider=0.40),
        )

        # Shrunk wOBA should heavily regress .500 sample back toward ~0.345
        if 0.330 <= res.shrunk_bvp_woba <= 0.360 and res.arsenal_interaction_rv100 > 0.5:
            checks.append(
                Check(
                    "bvp interaction engine",
                    True,
                    f"Empirical Bayes shrinkage verified (wOBA: {res.composite_matchup_woba:.3f})",
                )
            )
        else:
            checks.append(
                Check(
                    "bvp interaction engine",
                    False,
                    f"Unexpected shrunk wOBA: {res.shrunk_bvp_woba}",
                )
            )
    except Exception as exc:
        checks.append(Check("bvp interaction engine", False, str(exc)))
    return checks
