"""Pitcher Arsenals Tunneling & Point-of-Commitment Separation (TUNNEL-01, ADR-152).

Provides pitch trajectory overlap, release point consistency, and tunneling metrics:
1. 3D Release Coordinate Consistency (Euclidean distance between pitch release points).
2. Point-of-Commitment (POC) Separation at 23.8 ft / 175ms decision plane.
3. Plate Break Differential & Late Break Deception Index.
4. Tunneling Whiff & Called Strike Multiplier on sequential pitch pairing.

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
class PitchFlightVector:
    """3D release point and trajectory flight parameters."""

    pitch_type: str  # "FF", "SL", "CH", "SI", "CU"
    velocity_mph: float
    release_x_ft: float  # horizontal release (-2.0 ft for RHP)
    release_z_ft: float  # vertical release height (6.0 ft)
    ivb_in: float  # Induced Vertical Break
    hb_in: float  # Horizontal Break (positive = arm side)


@dataclasses.dataclass(frozen=True)
class PitchTunnelEvaluation:
    """Evaluated tunneling overlap and deception score between two pitches."""

    pitch_pair_label: str  # e.g. "FF-SL"
    release_distance_in: float  # release point difference in inches
    tunnel_distance_at_poc_in: float  # separation at Point of Commitment (23.8 ft from plate)
    plate_break_separation_in: float  # separation at home plate
    tunneling_quality_score: float  # 0 to 100 (higher = tighter tunnel before break)
    whiff_boost_pct: float
    is_elite_tunnel: bool


class BaseTunnelingEngine(Protocol):
    """Polymorphic protocol for pitch tunneling engines."""

    def evaluate_tunnel_pair(
        self,
        pitch_a: PitchFlightVector,
        pitch_b: PitchFlightVector,
    ) -> PitchTunnelEvaluation:
        """Calculate release and decision-point tunneling separation."""
        ...


class PitchTunnelingEngine:
    """Calculates pitch trajectory mirroring and point-of-commitment separation (TUNNEL-01)."""

    def evaluate_tunnel_pair(
        self,
        pitch_a: PitchFlightVector,
        pitch_b: PitchFlightVector,
    ) -> PitchTunnelEvaluation:
        """Compute release distance and Point-of-Commitment trajectory separation."""
        # 1. 3D Release Point Distance in inches
        dx_rel = (pitch_a.release_x_ft - pitch_b.release_x_ft) * 12.0
        dz_rel = (pitch_a.release_z_ft - pitch_b.release_z_ft) * 12.0
        rel_dist_in = float(math.sqrt(dx_rel**2 + dz_rel**2))

        # 2. Point of Commitment (POC) separation at y = 23.8 ft
        # Aerodynamic acceleration acts quadratically with flight time (t^2)
        # Release at ~54 ft, Plate at 1.4 ft (total flight distance = 52.6 ft)
        # At POC (23.8 ft from plate), ball has traveled ~30.2 ft (~55% of flight time)
        # Movement at POC is ~ (0.55)^2 = ~30% of total plate movement
        poc_factor = 0.30

        # Trajectory coordinates at POC:
        # x_poc = x_rel + (HB * poc_factor)
        dx_poc = dx_rel + ((pitch_a.hb_in - pitch_b.hb_in) * poc_factor)
        dz_poc = dz_rel + ((pitch_a.ivb_in - pitch_b.ivb_in) * poc_factor)
        poc_dist_in = float(math.sqrt(dx_poc**2 + dz_poc**2))

        # 3. Plate Break Total Separation in inches:
        dx_plate = dx_rel + (pitch_a.hb_in - pitch_b.hb_in)
        dz_plate = dz_rel + (pitch_a.ivb_in - pitch_b.ivb_in)
        plate_dist_in = float(math.sqrt(dx_plate**2 + dz_plate**2))

        # 4. Tunneling Quality Score:
        # Rewarded for: Small release (< 2.0 in), tight POC (< 2.5 in), and large plate break
        # Late break ratio = Plate Dist / max(0.5, POC Dist)
        late_break_ratio = plate_dist_in / max(0.5, poc_dist_in)
        tunnel_score = float(
            np.clip((late_break_ratio / 6.0) * 100.0 - (rel_dist_in * 5.0), 0.0, 100.0)
        )

        # Whiff boost: tight tunnel and large plate split gives up to +5.0% whiff boost
        if poc_dist_in <= 8.5 and plate_dist_in >= 16.0:
            whiff_boost = round(2.0 + (tunnel_score * 0.035), 2)
            is_elite = True
        else:
            whiff_boost = round(max(0.0, (tunnel_score - 40.0) * 0.03), 2)
            is_elite = False

        pair_label = f"{pitch_a.pitch_type}-{pitch_b.pitch_type}"

        return PitchTunnelEvaluation(
            pitch_pair_label=pair_label,
            release_distance_in=round(rel_dist_in, 2),
            tunnel_distance_at_poc_in=round(poc_dist_in, 2),
            plate_break_separation_in=round(plate_dist_in, 2),
            tunneling_quality_score=round(tunnel_score, 1),
            whiff_boost_pct=whiff_boost,
            is_elite_tunnel=is_elite,
        )


def health_check() -> list[Check]:
    """Operational health check for the Pitch Tunneling Engine (TUNNEL-01)."""
    checks: list[Check] = []
    try:
        engine = PitchTunnelingEngine()
        # Elite Fastball & Slider tunnel with identical release point
        ff = PitchFlightVector(
            "FF", velocity_mph=96.0, release_x_ft=-2.1, release_z_ft=5.9, ivb_in=17.0, hb_in=10.0
        )
        sl = PitchFlightVector(
            "SL", velocity_mph=86.0, release_x_ft=-2.1, release_z_ft=5.9, ivb_in=2.0, hb_in=-8.0
        )

        res = engine.evaluate_tunnel_pair(ff, sl)

        if res.is_elite_tunnel and res.plate_break_separation_in > 15.0:
            checks.append(
                Check(
                    "pitch tunneling engine",
                    True,
                    f"Tunnel verified (POC: {res.tunnel_distance_at_poc_in:.1f}in)",
                )
            )
        else:
            checks.append(
                Check("pitch tunneling engine", False, f"Unexpected tunneling evaluation: {res}")
            )
    except Exception as exc:
        checks.append(Check("pitch tunneling engine", False, str(exc)))
    return checks
