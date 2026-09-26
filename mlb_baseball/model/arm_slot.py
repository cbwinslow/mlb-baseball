"""Pitcher Arm Slot Angle & Release Consistency Dispersion Engine (ARM-SLOT-01, ADR-192).

Provides arm slot angle classification and release-point consistency scoring:
1. Arm Slot Angle (degrees), read directly from Baseball Savant's own published
   per-pitch Arm Angle measurement (Hawk-Eye biomechanic tracking) via
   `arm_slot_from_statcast()` -- real, cited data, populated in
   `raw.statcast_pitch.arm_angle` from the 2020 season on. See
   `mlb_baseball/metrics/arm_slot_engine.yaml` for the citation.
2. Arm Slot Classification (Submarine, Sidearm, Low Three-Quarters, Three-Quarters, Over-The-Top).
3. Release Point Consistency Score (0 to 100): a `project-derived`, uncited
   heuristic -- see `PitcherArmSlotEngine`'s class docstring -- kept separate
   from the cited arm-angle measurement above so no claim implies a citation
   it does not have (metric-catalog triage, 2026-09-23).

This module has two independent evaluation paths that must not be conflated:
`arm_slot_from_statcast()` reads a real pitcher's real Statcast arm-angle
data; `PitcherArmSlotEngine.evaluate_arm_slot()` is a hand-typed what-if/
scouting calculator (the CLI `mlb arm-slot` path when `--pitcher` is omitted) that estimates an
angle from caller-supplied release coordinates and an uncited shoulder-height
assumption. Both return an `ArmSlotEvaluationResult` whose `data_source`
field says which path produced it -- never trust the tier/angle without
checking it.
"""

from __future__ import annotations

import dataclasses
import math
from typing import Protocol

import psycopg

from mlb_baseball.health import Check

DATA_SOURCE_STATCAST = "statcast_arm_angle"
DATA_SOURCE_WHATIF = "hand_typed_whatif"


@dataclasses.dataclass(frozen=True)
class PitcherArmSlotMetrics:
    """Observed spatial release coordinates and anatomical dimensions (what-if input)."""

    pitcher_id: str
    pitcher_name: str
    release_x_ft: float = -2.2
    release_z_ft: float = 5.8
    pitcher_height_in: float = 75.0  # 6'3"
    release_dispersion_std_in: float = 1.3  # Standard deviation of release point across arsenal


@dataclasses.dataclass(frozen=True)
class ArmSlotEvaluationResult:
    """Evaluated arm slot angle, classification tier, and release consistency."""

    pitcher_name: str
    arm_slot_angle_deg: float
    arm_slot_tier: str  # e.g. "THREE_QUARTERS", "SIDEARM", "SUBMARINE", "OVER_THE_TOP"
    release_consistency_score: float  # 0 to 100, project-derived (see module docstring)
    is_elite_release_tunnel: bool
    data_source: str  # DATA_SOURCE_STATCAST or DATA_SOURCE_WHATIF -- see module docstring
    sample_size: int = 0  # number of real Statcast pitches averaged (0 for what-if)


class BaseArmSlotEngine(Protocol):
    """Polymorphic protocol for pitcher arm slot engines."""

    def evaluate_arm_slot(
        self,
        metrics: PitcherArmSlotMetrics,
    ) -> ArmSlotEvaluationResult:
        """Calculate arm slot angle, tier, and consistency score."""
        ...


def _classify_tier(angle_deg: float) -> str:
    """Classify an arm-slot angle (0deg = overhand ... 90deg+ = submarine) into a tier.

    Same convention Statcast's own Arm Angle uses: degrees from horizontal at
    release, so this classification applies unchanged to both the real
    Statcast angle and the what-if geometric estimate below.
    """
    if angle_deg > 90.0:
        return "SUBMARINE"
    if angle_deg >= 70.0:
        return "SIDEARM"
    if angle_deg >= 50.0:
        return "LOW_THREE_QUARTERS"
    if angle_deg >= 30.0:
        return "THREE_QUARTERS"
    return "OVER_THE_TOP"


def _consistency_score(stddev: float, scale: float) -> tuple[float, bool]:
    """Project-derived 0-100 consistency score from a dispersion stddev (uncited, see docstring)."""
    disp = max(0.2, stddev)
    consistency = max(0.0, 100.0 - (disp / 1.0) * scale)
    consistency = round(min(100.0, consistency), 1)
    return consistency, consistency >= 80.0


class PitcherArmSlotEngine:
    """What-if arm slot geometry calculator from hand-typed inputs (ARM-SLOT-01).

    Estimates an arm-slot angle from caller-supplied release coordinates and
    an uncited "shoulder is 82% of height" assumption. This is NOT the real
    Statcast arm-angle measurement (`arm_slot_from_statcast()`, below) -- see
    module docstring. Never wired to `raw.statcast_pitch`; scouting/what-if
    input only.
    """

    def evaluate_arm_slot(
        self,
        metrics: PitcherArmSlotMetrics,
    ) -> ArmSlotEvaluationResult:
        """Compute a what-if arm slot angle and consistency from hand-typed inputs."""
        # Shoulder joint height is roughly 82% of total height (uncited assumption)
        height_ft = metrics.pitcher_height_in / 12.0
        shoulder_z = height_ft * 0.82

        dz = metrics.release_z_ft - shoulder_z
        dx = abs(metrics.release_x_ft)

        # Angle relative to vertical (0° = pure overhand, 90° = sidearm, >90° = submarine)
        angle_rad = math.atan2(dx, dz)
        angle_deg = round(math.degrees(angle_rad), 1)

        consistency, is_tunnel = _consistency_score(metrics.release_dispersion_std_in, scale=22.0)
        tier = _classify_tier(angle_deg)

        return ArmSlotEvaluationResult(
            pitcher_name=metrics.pitcher_name,
            arm_slot_angle_deg=angle_deg,
            arm_slot_tier=tier,
            release_consistency_score=consistency,
            is_elite_release_tunnel=is_tunnel,
            data_source=DATA_SOURCE_WHATIF,
        )


def arm_slot_from_statcast(
    pitcher_mlbam_id: str,
    date_from: str,
    date_to: str,
    conn: psycopg.Connection,
) -> ArmSlotEvaluationResult | None:
    """Classify a real pitcher's real arm slot from Statcast's own arm_angle column.

    Reads `raw.statcast_pitch.arm_angle` (Baseball Savant's published, Hawk-Eye
    biomechanic-tracking arm-angle measurement) for the given pitcher and
    date range, and returns the mean angle, its tier, and a release-consistency
    score derived from the angle's real stddev across those pitches (a
    project-derived heuristic -- see module docstring -- kept separate from
    the cited angle itself).

    Returns None when no `arm_angle` data exists for this pitcher/range (e.g.
    a season before Statcast began publishing it, 2020) rather than
    fabricating a value.
    """
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT
                AVG(arm_angle::double precision) AS mean_angle,
                STDDEV(arm_angle::double precision) AS stddev_angle,
                COUNT(*) AS n,
                MAX(player_name) AS player_name
            FROM raw.statcast_pitch
            WHERE pitcher = %(pitcher_id)s
              AND game_date BETWEEN %(date_from)s AND %(date_to)s
              AND arm_angle IS NOT NULL
            """,
            {
                "pitcher_id": pitcher_mlbam_id,
                "date_from": date_from,
                "date_to": date_to,
            },
        )
        row = cur.fetchone()

    if row is None or row[2] == 0 or row[0] is None:
        return None

    mean_angle, stddev_angle, n, player_name = row
    angle_deg = round(float(mean_angle), 1)
    # Savant's own arm_angle convention is degrees from HORIZONTAL (0 deg =
    # true sidearm, 90 deg = true over-the-top, negative = submarine) --
    # the opposite sense from _classify_tier's degrees-from-VERTICAL
    # convention (0 deg = overhand, 90 deg+ = sidearm/submarine) that the
    # what-if path above already produces via atan2(dx, dz). Convert for
    # classification only; arm_slot_angle_deg below still reports Savant's
    # real published value unchanged (CodeRabbit PR #242 review).
    tier = _classify_tier(90.0 - angle_deg)
    # Consistency scale is not comparable to the what-if path's inches-based
    # scale above -- arm_angle's real stddev is in degrees. Project-derived,
    # same as the what-if score (see module docstring); only ordering
    # (lower stddev => higher score) is asserted, not an exact calibration.
    consistency, is_tunnel = _consistency_score(float(stddev_angle or 0.0), scale=8.0)

    return ArmSlotEvaluationResult(
        pitcher_name=player_name or pitcher_mlbam_id,
        arm_slot_angle_deg=angle_deg,
        arm_slot_tier=tier,
        release_consistency_score=consistency,
        is_elite_release_tunnel=is_tunnel,
        data_source=DATA_SOURCE_STATCAST,
        sample_size=int(n),
    )


def health_check() -> list[Check]:
    """Operational health check for Pitcher Arm Slot Engine (ARM-SLOT-01)."""
    checks: list[Check] = []
    try:
        engine = PitcherArmSlotEngine()
        sidearmer = PitcherArmSlotMetrics("p1", "Sidearmer", -2.5, 5.2, 73.0, 1.1)
        overhand = PitcherArmSlotMetrics("p2", "Overhand Pitcher", -0.5, 6.6, 76.0, 1.2)

        r_sid = engine.evaluate_arm_slot(sidearmer)
        r_ove = engine.evaluate_arm_slot(overhand)

        if r_sid.arm_slot_tier == "SIDEARM" and r_ove.arm_slot_tier == "OVER_THE_TOP":
            checks.append(
                Check(
                    "arm slot engine",
                    True,
                    f"Arm slot verified (Sidearm: {r_sid.arm_slot_angle_deg:.1f}°)",
                )
            )
        else:
            checks.append(Check("arm slot engine", False, f"Unexpected arm slot: {r_sid}, {r_ove}"))
    except Exception as exc:
        checks.append(Check("arm slot engine", False, str(exc)))
    return checks
