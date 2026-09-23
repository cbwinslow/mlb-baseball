"""Batter BABIP Expected Luck Deficit & Regression Scanner (BABIP-LUCK-01, ADR-179).

Provides real actual-vs-expected BABIP comparison and luck-regression tiering:
1. Real actual BABIP (`(H - HR) / (AB - K - HR + SF)`, the standard public
   definition) and real expected BABIP (mean of Statcast's own published
   xBA model, `estimated_ba_using_speedangle`, over the same non-HR balls in
   play) via `babip_from_statcast()`. Cited: Statcast's Expected Statistics
   methodology -- the same source `model/statcast_expected.py` already cites.
   Populated in `raw.statcast_pitch` from the 2015 season on.
2. BABIP Luck Deficit (Actual BABIP - Expected BABIP).
3. Positive and Negative Regression Candidate Identification (Buy-Low vs Sell-High).
4. Regression Tiers (Severe Positive Regression, Fair Value Neutral, Severe Negative Regression).

This module has two independent evaluation paths that must not be conflated:
`babip_from_statcast()` reads a real batter's real Statcast data;
`BABIPRegressionEngine.evaluate_babip()` is a hand-typed what-if/scouting
calculator (the CLI `mlb babip` path when `--batter` is omitted) using an uncited linear
formula. Both return a `BABIPEvaluationResult` whose `data_source` field
says which path produced it -- metric-catalog triage, 2026-09-23.
"""

from __future__ import annotations

import dataclasses
from typing import Protocol

import psycopg

from mlb_baseball.health import Check

DATA_SOURCE_STATCAST = "statcast_expected_ba"
DATA_SOURCE_WHATIF = "hand_typed_whatif"


@dataclasses.dataclass(frozen=True)
class BatterBABIPInputs:
    """Observed BABIP and trajectory distribution inputs for a batter (what-if input)."""

    batter_id: str
    batter_name: str
    actual_babip: float = 0.310
    ld_pct: float = 0.21  # Line drive rate
    gb_pct: float = 0.44  # Ground ball rate
    fb_pct: float = 0.35  # Fly ball rate
    hard_hit_pct: float = 0.40  # Exit velo >= 95 mph
    sprint_speed_fps: float = 27.2  # Statcast sprint speed in ft/s
    iffb_pct: float = 0.08  # Infield fly ball % of FB


@dataclasses.dataclass(frozen=True)
class BABIPEvaluationResult:
    """Evaluated expected xBABIP, luck delta, and regression classification."""

    batter_name: str
    actual_babip: float
    expected_xbabip: float
    babip_luck_delta: float  # Actual BABIP - Expected xBABIP
    regression_tier: str  # e.g. "SEVERE_POSITIVE_REGRESSION", "FAIR_VALUE_NEUTRAL"
    is_buy_low_candidate: bool
    data_source: str  # DATA_SOURCE_STATCAST or DATA_SOURCE_WHATIF -- see module docstring
    balls_in_play: int = 0  # real non-HR BIP sample size (0 for what-if)


class BaseBABIPEngine(Protocol):
    """Polymorphic protocol for BABIP regression engines."""

    def evaluate_babip(
        self,
        inputs: BatterBABIPInputs,
    ) -> BABIPEvaluationResult:
        """Calculate expected xBABIP and luck delta."""
        ...


def _classify_regression_tier(delta: float) -> tuple[str, bool]:
    """Classify an actual-minus-expected BABIP delta into a regression tier."""
    if delta <= -0.045:
        return "SEVERE_POSITIVE_REGRESSION", True
    if delta <= -0.020:
        return "MODERATE_UNDERPERFORMER", True
    if delta >= 0.045:
        return "SEVERE_NEGATIVE_REGRESSION", False
    if delta >= 0.020:
        return "MODERATE_OVERPERFORMER", False
    return "FAIR_VALUE_NEUTRAL", False


class BABIPRegressionEngine:
    """What-if xBABIP calculator from hand-typed trajectory-rate inputs (BABIP-LUCK-01).

    Estimates an expected BABIP from an uncited linear formula over
    caller-supplied rate inputs. This is NOT the real Statcast-derived
    expected BABIP (`babip_from_statcast()`, below) -- see module docstring.
    Never wired to `raw.statcast_pitch`; scouting/what-if input only.
    """

    def evaluate_babip(
        self,
        inputs: BatterBABIPInputs,
    ) -> BABIPEvaluationResult:
        """Compute a what-if xBABIP and luck deficit from hand-typed rate inputs."""
        # Uncited baseline (project-derived, see module/class docstring):
        # 0.220 + 0.380*LD + 0.120*HardHit + 0.006*(Speed - 27.0) - 0.140*IFFB + 0.040*GB
        speed_delta = inputs.sprint_speed_fps - 27.0
        xbabip = (
            0.220
            + 0.380 * inputs.ld_pct
            + 0.120 * inputs.hard_hit_pct
            + 0.006 * speed_delta
            - 0.140 * inputs.iffb_pct
            + 0.040 * inputs.gb_pct
        )
        xbabip = round(xbabip, 3)

        delta = round(inputs.actual_babip - xbabip, 3)
        tier, buy_low = _classify_regression_tier(delta)

        return BABIPEvaluationResult(
            batter_name=inputs.batter_name,
            actual_babip=inputs.actual_babip,
            expected_xbabip=xbabip,
            babip_luck_delta=delta,
            regression_tier=tier,
            is_buy_low_candidate=buy_low,
            data_source=DATA_SOURCE_WHATIF,
        )


def babip_from_statcast(
    batter_mlbam_id: str,
    date_from: str,
    date_to: str,
    conn: psycopg.Connection,
) -> BABIPEvaluationResult | None:
    """Compute a real batter's real actual-vs-expected BABIP from Statcast data.

    Actual BABIP uses the standard public definition, `(H - HR) / (AB - K -
    HR + SF)`, computed here as (non-HR batted-ball hits) / (non-HR
    batted-ball events) -- `raw.statcast_pitch.bb_type IS NOT NULL` is
    Savant's own reliable batted-ball-event marker (already relied on by
    `mlb_baseball/sql/statcast_expected_update.sql`), so this matches the
    public formula except for the rare sac-bunt edge case, a simplification
    shared by most public BABIP calculators. Confirmed directly against
    production (2026-09-23): `raw.statcast_pitch.babip_value` is itself a
    real Statcast-native 0/1 "counts as a BABIP hit" flag -- 1 on
    single/double/triple, 0 on outs/strikeouts, and 0 on home runs (excluded
    from BABIP by definition) -- independently confirming the hit
    classification used below (`events IN ('single', 'double', 'triple')`).
    `estimated_ba_using_speedangle` coverage on real batted balls is ~91%
    (2023 spot check), not 100%; `AVG()` here naturally skips the NULLs
    rather than treating them as zero.

    Expected BABIP is the mean of Statcast's own xBA model
    (`estimated_ba_using_speedangle`) over that same non-HR balls-in-play
    population -- Statcast's Expected Statistics methodology, the same
    source `model/statcast_expected.py` cites.

    Returns None when no batted-ball data exists for this batter/range (e.g.
    a season before Statcast began publishing expected stats, 2015) rather
    than fabricating a value.
    """
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT
                COUNT(*) FILTER (WHERE bb_type IS NOT NULL AND events <> 'home_run')
                    AS bip_n,
                COUNT(*) FILTER (
                    WHERE bb_type IS NOT NULL
                      AND events IN ('single', 'double', 'triple')
                ) AS hits_n,
                AVG(NULLIF(estimated_ba_using_speedangle, '')::double precision)
                    FILTER (WHERE bb_type IS NOT NULL AND events <> 'home_run')
                    AS mean_xba,
                MAX(player_name) AS player_name
            FROM raw.statcast_pitch
            WHERE batter = %(batter_id)s
              AND game_date BETWEEN %(date_from)s AND %(date_to)s
              AND events IS NOT NULL
            """,
            {
                "batter_id": batter_mlbam_id,
                "date_from": date_from,
                "date_to": date_to,
            },
        )
        row = cur.fetchone()

    if row is None or not row[0] or row[2] is None:
        return None

    bip_n, hits_n, mean_xba, player_name = row
    actual_babip = round(hits_n / bip_n, 3)
    expected_babip = round(float(mean_xba), 3)
    delta = round(actual_babip - expected_babip, 3)
    tier, buy_low = _classify_regression_tier(delta)

    return BABIPEvaluationResult(
        batter_name=player_name or batter_mlbam_id,
        actual_babip=actual_babip,
        expected_xbabip=expected_babip,
        babip_luck_delta=delta,
        regression_tier=tier,
        is_buy_low_candidate=buy_low,
        data_source=DATA_SOURCE_STATCAST,
        balls_in_play=int(bip_n),
    )


def health_check() -> list[Check]:
    """Operational health check for BABIP Regression Engine (BABIP-LUCK-01)."""
    checks: list[Check] = []
    try:
        engine = BABIPRegressionEngine()
        unlucky = BatterBABIPInputs(
            "b1",
            "Unlucky Slugger",
            actual_babip=0.235,
            ld_pct=0.24,
            hard_hit_pct=0.48,
            sprint_speed_fps=28.5,
            iffb_pct=0.04,
        )
        lucky = BatterBABIPInputs(
            "b2",
            "Lucky Blooper",
            actual_babip=0.385,
            ld_pct=0.16,
            hard_hit_pct=0.28,
            sprint_speed_fps=25.5,
            iffb_pct=0.14,
        )

        r_un = engine.evaluate_babip(unlucky)
        r_lu = engine.evaluate_babip(lucky)

        if (
            r_un.regression_tier == "SEVERE_POSITIVE_REGRESSION"
            and r_lu.regression_tier == "SEVERE_NEGATIVE_REGRESSION"
        ):
            checks.append(
                Check(
                    "babip luck engine",
                    True,
                    f"BABIP verified (Delta: {r_un.babip_luck_delta:>+5.3f})",
                )
            )
        else:
            checks.append(
                Check("babip luck engine", False, f"Unexpected BABIP output: {r_un}, {r_lu}")
            )
    except Exception as exc:
        checks.append(Check("babip luck engine", False, str(exc)))
    return checks
