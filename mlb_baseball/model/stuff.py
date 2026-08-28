"""Pitch Physics & Stuff+/Location+/Pitching+ Rating Engine (STUFF-01, ADR-126).

Provides physics-based evaluation of pitch trajectories, physical movement, and arsenal quality:
1. Physical Pitch Trajectory Model (Velocity, IVB, HB, VAA, HAA, Release Extension).
2. Stuff+ (Physical Movement Quality independent of location).
3. Location+ (Strike zone execution and count-dependent command quality).
4. Pitching+ (Synthetic composite scoring of physical stuff, location, and arsenal balance).
5. Arsenal Repertoire Aggregator (Usage-weighted pitcher rating).

Adheres strictly to object-oriented encapsulation, polymorphic protocols, and
point-in-time correctness with zero lookahead leakage.
"""

from __future__ import annotations

import dataclasses
import enum
from collections.abc import Sequence
from typing import Protocol

import numpy as np

from mlb_baseball.health import Check


class PitchType(enum.Enum):
    """Standard MLB Statcast pitch classifications."""

    FOUR_SEAM = "FF"  # Four-seam Fastball
    SINKER = "SI"  # Sinker / Two-seam
    CUTTER = "FC"  # Cutter
    SLIDER = "SL"  # Slider
    SWEEPER = "ST"  # Sweeper
    CURVEBALL = "CU"  # Curveball
    CHANGEUP = "CH"  # Changeup
    SPLITTER = "FS"  # Splitter
    KNUCKLE_CURVE = "KC"  # Knuckle Curve
    OTHER = "XX"


@dataclasses.dataclass(frozen=True)
class PitchPhysicsVector:
    """Encapsulates the physical and spatial attributes of a single pitch trajectory."""

    pitch_type: PitchType
    release_speed_mph: float  # Velocity at release (mph)
    induced_vert_break_in: float  # IVB (inches, Magnus lift above gravity)
    horizontal_break_in: float  # HB (inches, arm/glove side horizontal break)
    release_height_ft: float  # z0 release coordinate (ft)
    release_side_ft: float  # x0 release coordinate (ft)
    release_extension_ft: float  # Extension toward home plate (ft)
    plate_x_ft: float  # Horizontal coordinate crossing plate (ft)
    plate_z_ft: float  # Vertical coordinate crossing plate (ft)
    vertical_approach_angle_deg: float | None = None  # VAA
    horizontal_approach_angle_deg: float | None = None  # HAA


@dataclasses.dataclass(frozen=True)
class PitchGrade:
    """Comprehensive sabermetric grade for a single pitch or pitch type (100 = MLB Average)."""

    pitch_type: PitchType
    stuff_plus: float  # Physical pitch trajectory rating (100 avg, higher is better)
    location_plus: float  # Command and plate location rating (100 avg, higher is better)
    pitching_plus: float  # Composite physical and command rating (100 avg, higher is better)
    expected_whiff_rate: float
    expected_run_value_per_100: (
        float  # Negative run value is good for pitcher, but Stuff+ inverts to 100+ baseline
    )


@dataclasses.dataclass(frozen=True)
class PitcherArsenalProfile:
    """Full pitch repertoire profile for a pitcher."""

    pitcher_id: str
    pitcher_name: str
    pitches_evaluated: int
    overall_stuff_plus: float
    overall_location_plus: float
    overall_pitching_plus: float
    repertoire_grades: dict[str, PitchGrade]
    usage_weights: dict[str, float]


# MLB League Baseline Benchmarks per Pitch Type (Mean, StdDev) for Fastballs and Secondaries
PITCH_TYPE_BASELINES = {
    PitchType.FOUR_SEAM: {
        "velo_mean": 94.2,
        "velo_std": 2.2,
        "ivb_mean": 16.2,
        "ivb_std": 2.8,
        "hb_mean": 7.5,
        "hb_std": 3.2,
        "rv_mean": 0.05,
        "rv_std": 0.40,
    },
    PitchType.SINKER: {
        "velo_mean": 93.5,
        "velo_std": 2.3,
        "ivb_mean": 9.5,
        "ivb_std": 3.1,
        "hb_mean": 14.8,
        "hb_std": 3.4,
        "rv_mean": 0.02,
        "rv_std": 0.38,
    },
    PitchType.SLIDER: {
        "velo_mean": 85.1,
        "velo_std": 2.8,
        "ivb_mean": 2.5,
        "ivb_std": 3.5,
        "hb_mean": -6.2,
        "hb_std": 4.1,
        "rv_mean": -0.15,
        "rv_std": 0.45,
    },
    PitchType.SWEEPER: {
        "velo_mean": 82.3,
        "velo_std": 2.6,
        "ivb_mean": 1.0,
        "ivb_std": 3.2,
        "hb_mean": -14.5,
        "hb_std": 4.5,
        "rv_mean": -0.22,
        "rv_std": 0.50,
    },
    PitchType.CURVEBALL: {
        "velo_mean": 79.2,
        "velo_std": 3.1,
        "ivb_mean": -9.8,
        "ivb_std": 4.2,
        "hb_mean": -8.5,
        "hb_std": 4.0,
        "rv_mean": -0.18,
        "rv_std": 0.46,
    },
    PitchType.CHANGEUP: {
        "velo_mean": 85.5,
        "velo_std": 2.7,
        "ivb_mean": 6.8,
        "ivb_std": 3.6,
        "hb_mean": 13.5,
        "hb_std": 3.8,
        "rv_mean": -0.12,
        "rv_std": 0.42,
    },
}


class BasePitchRatingModel(Protocol):
    """Polymorphic protocol for physical pitch and arsenal rating models."""

    def evaluate_pitch(
        self, pitch: PitchPhysicsVector, count: tuple[int, int] = (0, 0)
    ) -> PitchGrade:
        """Evaluate a single pitch trajectory into Stuff+, Location+, and Pitching+ grades."""
        ...

    def evaluate_arsenal(
        self,
        pitcher_id: str,
        pitcher_name: str,
        pitches: Sequence[tuple[PitchPhysicsVector, tuple[int, int]]],
    ) -> PitcherArsenalProfile:
        """Aggregate an entire sample of pitches into a pitcher arsenal profile."""
        ...


class PhysicalPitchRatingEngine:
    """Physics-based Stuff+ and Location+ calculation engine (STUFF-01, ADR-126).

    Models run expectancy from raw trajectory aerodynamics and plate approach geometry:
    - Stuff+: Evaluates velocity delta, IVB relative to slot, and sweep/drop.
    - Location+: Evaluates Euclidean distance from optimal attack zone targets per count.
    - Pitching+: Weighted blend (60% Stuff+ + 40% Location+ for starters).
    """

    def __init__(self) -> None:
        self.baselines = PITCH_TYPE_BASELINES

    def _calculate_stuff_plus(self, pitch: PitchPhysicsVector) -> tuple[float, float, float]:
        """Compute physical Stuff+ index, expected whiff rate, and expected run value."""
        pt = pitch.pitch_type
        base = self.baselines.get(pt, self.baselines[PitchType.FOUR_SEAM])

        # Velocity component (z-score relative to pitch-type baseline)
        velo_z = (pitch.release_speed_mph - base["velo_mean"]) / base["velo_std"]

        # Movement component: Fastballs reward high IVB; breaking balls reward drop/sweep
        if pt == PitchType.FOUR_SEAM:
            mov_z = (pitch.induced_vert_break_in - base["ivb_mean"]) / base["ivb_std"]
        elif pt in (PitchType.SLIDER, PitchType.SWEEPER):
            # Reward horizontal sweep + velocity
            hb_mag = abs(pitch.horizontal_break_in)
            base_hb_mag = abs(base["hb_mean"])
            mov_z = (hb_mag - base_hb_mag) / base["hb_std"]
        elif pt in (PitchType.CURVEBALL, PitchType.KNUCKLE_CURVE):
            # Reward downward depth (more negative IVB is better)
            mov_z = (base["ivb_mean"] - pitch.induced_vert_break_in) / base["ivb_std"]
        elif pt in (PitchType.CHANGEUP, PitchType.SPLITTER):
            # Reward vertical separation / drop from fastball
            mov_z = (base["ivb_mean"] - pitch.induced_vert_break_in) / base["ivb_std"]
        else:
            mov_z = 0.0

        # Extension bonus: each 0.5 ft above 6.0 ft adds ~0.2 effective z-score
        ext_bonus = (pitch.release_extension_ft - 6.0) * 0.40

        # Composite physical z-score
        raw_stuff_z = (0.50 * velo_z) + (0.45 * mov_z) + (0.05 * ext_bonus)

        # Scale to 100-indexed metric with 15-point standard deviation (like IQ / wRC+)
        stuff_plus = float(np.clip(100.0 + (raw_stuff_z * 15.0), 40.0, 180.0))

        # Expected whiff rate mapping: sigmoid over stuff z-score
        base_whiff = 0.22 if pt == PitchType.FOUR_SEAM else 0.32
        exp_whiff = float(np.clip(base_whiff + (raw_stuff_z * 0.06), 0.05, 0.65))

        # Expected run value per 100 pitches
        exp_rv_100 = float(base["rv_mean"] - (raw_stuff_z * base["rv_std"]))

        return round(stuff_plus, 1), round(exp_whiff, 3), round(exp_rv_100, 3)

    def _calculate_location_plus(self, pitch: PitchPhysicsVector, count: tuple[int, int]) -> float:
        """Compute Location+ index based on count context and strike zone attack zones."""
        balls, strikes = count
        px = pitch.plate_x_ft
        pz = pitch.plate_z_ft

        # Strike zone bounds (approx 17 inches wide = +/- 0.708 ft, height 1.5 to 3.5 ft)
        in_zone_x = abs(px) <= 0.708
        in_zone_z = 1.5 <= pz <= 3.5

        # Edge / Shadow zone (within 0.25 ft of zone boundary)
        dist_to_edge_x = abs(abs(px) - 0.708)
        dist_to_edge_z = min(abs(pz - 1.5), abs(pz - 3.5))

        # Target strategy depends on count
        if strikes == 2:
            # 2 strikes: ideal location is in shadow/chase zone just off the edge
            if 0.65 <= abs(px) <= 1.05 or (pz < 1.6 and pz > 1.0):
                loc_z = +1.2  # Perfect chase/shadow pitch
            elif abs(px) < 0.40 and 2.0 <= pz <= 3.0:
                loc_z = -1.5  # Heart of plate mistake on 2 strikes!
            elif abs(px) > 1.4 or pz < 0.6 or pz > 4.2:
                loc_z = -1.2  # Uncompetitive waste pitch
            else:
                loc_z = +0.3
        elif balls >= 2:
            # Behind in count (2-0, 3-0, 3-1): need competitive strike in zone
            if in_zone_x and in_zone_z:
                loc_z = +0.8 if (dist_to_edge_x < 0.2 or dist_to_edge_z < 0.2) else +0.4
            else:
                loc_z = -1.4  # Ball when behind in count
        else:
            # Neutral count: reward shadow/edge pitches
            if dist_to_edge_x <= 0.25 or dist_to_edge_z <= 0.25:
                loc_z = +1.0
            elif in_zone_x and in_zone_z:
                loc_z = +0.2
            else:
                loc_z = -0.6

        location_plus = float(np.clip(100.0 + (loc_z * 12.0), 50.0, 160.0))
        return round(location_plus, 1)

    def evaluate_pitch(
        self, pitch: PitchPhysicsVector, count: tuple[int, int] = (0, 0)
    ) -> PitchGrade:
        """Evaluate physical trajectory into Stuff+, Location+, and Pitching+ grades."""
        stuff_plus, exp_whiff, exp_rv_100 = self._calculate_stuff_plus(pitch)
        location_plus = self._calculate_location_plus(pitch, count)

        # Composite Pitching+ (60% Stuff+ / 40% Location+)
        pitching_plus = round((0.60 * stuff_plus) + (0.40 * location_plus), 1)

        return PitchGrade(
            pitch_type=pitch.pitch_type,
            stuff_plus=stuff_plus,
            location_plus=location_plus,
            pitching_plus=pitching_plus,
            expected_whiff_rate=exp_whiff,
            expected_run_value_per_100=exp_rv_100,
        )

    def evaluate_arsenal(
        self,
        pitcher_id: str,
        pitcher_name: str,
        pitches: Sequence[tuple[PitchPhysicsVector, tuple[int, int]]],
    ) -> PitcherArsenalProfile:
        """Aggregate an entire sample of pitches into a pitcher arsenal profile."""
        if not pitches:
            return PitcherArsenalProfile(
                pitcher_id=pitcher_id,
                pitcher_name=pitcher_name,
                pitches_evaluated=0,
                overall_stuff_plus=100.0,
                overall_location_plus=100.0,
                overall_pitching_plus=100.0,
                repertoire_grades={},
                usage_weights={},
            )

        n_total = len(pitches)
        type_pitches: dict[PitchType, list[tuple[PitchPhysicsVector, tuple[int, int]]]] = {}

        for p_vec, cnt in pitches:
            type_pitches.setdefault(p_vec.pitch_type, []).append((p_vec, cnt))

        repertoire_grades: dict[str, PitchGrade] = {}
        usage_weights: dict[str, float] = {}

        weighted_stuff = 0.0
        weighted_loc = 0.0
        weighted_pitching = 0.0

        for pt, p_list in type_pitches.items():
            count_pt = len(p_list)
            usage = count_pt / n_total
            usage_weights[pt.value] = round(usage, 3)

            # Average grades across all pitches of this type
            grades = [self.evaluate_pitch(pv, cnt) for pv, cnt in p_list]
            avg_stuff = float(np.mean([g.stuff_plus for g in grades]))
            avg_loc = float(np.mean([g.location_plus for g in grades]))
            avg_pitching = float(np.mean([g.pitching_plus for g in grades]))
            avg_whiff = float(np.mean([g.expected_whiff_rate for g in grades]))
            avg_rv = float(np.mean([g.expected_run_value_per_100 for g in grades]))

            grade_obj = PitchGrade(
                pitch_type=pt,
                stuff_plus=round(avg_stuff, 1),
                location_plus=round(avg_loc, 1),
                pitching_plus=round(avg_pitching, 1),
                expected_whiff_rate=round(avg_whiff, 3),
                expected_run_value_per_100=round(avg_rv, 3),
            )
            repertoire_grades[pt.value] = grade_obj

            weighted_stuff += usage * avg_stuff
            weighted_loc += usage * avg_loc
            weighted_pitching += usage * avg_pitching

        return PitcherArsenalProfile(
            pitcher_id=pitcher_id,
            pitcher_name=pitcher_name,
            pitches_evaluated=n_total,
            overall_stuff_plus=round(weighted_stuff, 1),
            overall_location_plus=round(weighted_loc, 1),
            overall_pitching_plus=round(weighted_pitching, 1),
            repertoire_grades=repertoire_grades,
            usage_weights=usage_weights,
        )


def health_check() -> list[Check]:
    """Operational health check for the Pitch Physics & Arsenal Rating Engine (STUFF-01)."""
    checks: list[Check] = []
    try:
        engine = PhysicalPitchRatingEngine()

        # Elite Four-Seamer (99 mph, 19.5" IVB, 6.8 ft extension)
        elite_ff = PitchPhysicsVector(
            pitch_type=PitchType.FOUR_SEAM,
            release_speed_mph=99.2,
            induced_vert_break_in=19.5,
            horizontal_break_in=8.2,
            release_height_ft=6.1,
            release_side_ft=-1.8,
            release_extension_ft=6.8,
            plate_x_ft=0.2,
            plate_z_ft=3.2,
        )
        grade = engine.evaluate_pitch(elite_ff, count=(0, 2))

        # Elite fastball should score > 125 Stuff+
        if grade.stuff_plus > 125.0 and grade.expected_whiff_rate > 0.25:
            checks.append(
                Check(
                    "pitch physics rating engine",
                    True,
                    f"Stuff+ model verified (Elite FF score: {grade.stuff_plus:.1f})",
                )
            )
        else:
            checks.append(
                Check(
                    "pitch physics rating engine",
                    False,
                    f"Unexpected Stuff+ score: {grade.stuff_plus}",
                )
            )
    except Exception as exc:
        checks.append(Check("pitch physics rating engine", False, str(exc)))
    return checks
