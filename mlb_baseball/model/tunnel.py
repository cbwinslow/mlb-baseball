"""Pitcher Arsenals Tunneling & Point-of-Commitment Separation (TUNNEL-01, ADR-152).

Provides pitch trajectory overlap and tunneling metrics:
1. 3D Release Coordinate Consistency (Euclidean distance between real release points).
2. Point-of-Commitment (POC) Separation at the Tunnel Point -- 23.8 ft / 175ms
   before the front of home plate (Long/Pavlidis/Judge, Baseball Prospectus,
   "Introducing Pitch Tunnels," 2017). `tunnel_pair_from_statcast()` computes
   this from each real pitch's own measured Statcast kinematics
   (vx0/vy0/vz0/ax/ay/az), via the same closed-form projectile-motion
   approach `model/vaa.py::pitch_vaa_degrees()` uses for VAA -- not the
   `poc_factor = 0.30` linear approximation the hand-typed what-if path
   below still uses (that approximation has no real kinematics to work
   from; see `PitchTunnelingEngine`'s class docstring).
3. Plate Break Differential, using real `plate_x`/`plate_z`.
4. Break:Tunnel Ratio -- (plate separation - Tunnel Point separation) /
   Tunnel Point separation -- Baseball Prospectus's own published ratio of
   post-tunnel break to tunnel-point differential. The 0-100
   `tunneling_quality_score` scaling and the elite-tunnel thresholds are
   `project-derived`: no published source for those specific numbers was
   found (metric-catalog triage literature check, 2026-09-23) -- see
   `mlb_baseball/metrics/pitch_tunneling_engine.yaml`.

This module has two independent evaluation paths that must not be conflated:
`tunnel_pair_from_statcast()` reads a real pitcher's two real pitch types;
`PitchTunnelingEngine.evaluate_tunnel_pair()` is a hand-typed what-if
calculator (the CLI `mlb tunnel --whatif` path). Both return a
`PitchTunnelEvaluation` whose `data_source` field says which path produced
it.
"""

from __future__ import annotations

import dataclasses
import math
from typing import Protocol

import numpy as np
import psycopg

from mlb_baseball.health import Check

DATA_SOURCE_STATCAST = "statcast_kinematics"
DATA_SOURCE_WHATIF = "hand_typed_whatif"

# Statcast kinematics origin and the front of home plate (feet) -- same
# convention model/vaa.py uses. Tunnel Point is 23.8 ft before the front of
# the plate (Long/Pavlidis/Judge, BP, "Introducing Pitch Tunnels," 2017).
_Y0_FT = 50.0
_YF_PLATE_FT = 17.0 / 12.0
_YF_TUNNEL_FT = _YF_PLATE_FT + 23.8


def _position_at_y(
    *,
    x0: float,
    z0: float,
    vx0: float,
    vy0: float,
    vz0: float,
    ax: float,
    ay: float,
    az: float,
    yf: float,
) -> tuple[float, float] | None:
    """Real (x, z) position at plate-distance `yf`, from measured Statcast kinematics.

    Same closed-form projectile-motion solve as `vaa.py::pitch_vaa_degrees()`,
    generalized from a fixed target (the plate) to an arbitrary one (the
    Tunnel Point). Returns None when the kinematics are unusable (zero ay,
    negative discriminant, zero plate-y velocity) -- the same degenerate
    cases VAA guards against.
    """
    if ay == 0.0:
        return None
    disc = vy0 * vy0 - 2.0 * ay * (_Y0_FT - yf)
    if disc <= 0.0:
        return None
    vy_f = -math.sqrt(disc)
    if vy_f == 0.0:
        return None
    t = (vy_f - vy0) / ay
    x = x0 + vx0 * t + 0.5 * ax * t * t
    z = z0 + vz0 * t + 0.5 * az * t * t
    return x, z


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
    break_tunnel_ratio: float  # BP's published Break:Tunnel Ratio (see module docstring)
    tunneling_quality_score: float  # 0 to 100, project-derived (see module docstring)
    whiff_boost_pct: float  # project-derived
    is_elite_tunnel: bool  # project-derived threshold
    data_source: str  # DATA_SOURCE_STATCAST or DATA_SOURCE_WHATIF -- see module docstring


class BaseTunnelingEngine(Protocol):
    """Polymorphic protocol for pitch tunneling engines."""

    def evaluate_tunnel_pair(
        self,
        pitch_a: PitchFlightVector,
        pitch_b: PitchFlightVector,
    ) -> PitchTunnelEvaluation:
        """Calculate release and decision-point tunneling separation."""
        ...


def _score_and_classify(
    rel_dist_in: float, poc_dist_in: float, plate_dist_in: float
) -> tuple[float, float, float, bool]:
    """Shared, project-derived scoring from release/POC/plate separations (see module docstring).

    Returns (break_tunnel_ratio, tunneling_quality_score, whiff_boost_pct, is_elite_tunnel).
    `break_tunnel_ratio` is BP's published Break:Tunnel Ratio (post-tunnel break
    over Tunnel Point differential); the 0-100 scaling, whiff-boost formula,
    and elite thresholds below have no published source found and are
    project-derived.
    """
    break_tunnel_ratio = (plate_dist_in - poc_dist_in) / max(0.5, poc_dist_in)
    tunnel_score = float(
        np.clip((break_tunnel_ratio / 6.0) * 100.0 - (rel_dist_in * 5.0), 0.0, 100.0)
    )

    if poc_dist_in <= 8.5 and plate_dist_in >= 16.0:
        whiff_boost = round(2.0 + (tunnel_score * 0.035), 2)
        is_elite = True
    else:
        whiff_boost = round(max(0.0, (tunnel_score - 40.0) * 0.03), 2)
        is_elite = False

    return round(break_tunnel_ratio, 3), round(tunnel_score, 1), whiff_boost, is_elite


class PitchTunnelingEngine:
    """What-if pitch tunneling calculator from hand-typed release/movement inputs (TUNNEL-01).

    Estimates Point-of-Commitment separation with a linear `poc_factor = 0.30`
    approximation of how much of a pitch's total plate movement has
    happened by the Tunnel Point -- because hand-typed release/movement
    inputs carry no real acceleration components to solve exact kinematics
    from. This is NOT the real Statcast-kinematics-derived tunnel
    (`tunnel_pair_from_statcast()`, below) -- see module docstring. Never
    wired to `raw.statcast_pitch`; scouting/what-if input only.
    """

    def evaluate_tunnel_pair(
        self,
        pitch_a: PitchFlightVector,
        pitch_b: PitchFlightVector,
    ) -> PitchTunnelEvaluation:
        """Compute a what-if release distance and Point-of-Commitment separation."""
        # 1. 3D Release Point Distance in inches
        dx_rel = (pitch_a.release_x_ft - pitch_b.release_x_ft) * 12.0
        dz_rel = (pitch_a.release_z_ft - pitch_b.release_z_ft) * 12.0
        rel_dist_in = float(math.sqrt(dx_rel**2 + dz_rel**2))

        # 2. Point of Commitment (POC) separation at y = 23.8 ft (uncited approximation --
        # see class docstring: movement assumed to scale as ~30% of total plate
        # movement by the Tunnel Point, not solved from real kinematics)
        poc_factor = 0.30
        dx_poc = dx_rel + ((pitch_a.hb_in - pitch_b.hb_in) * poc_factor)
        dz_poc = dz_rel + ((pitch_a.ivb_in - pitch_b.ivb_in) * poc_factor)
        poc_dist_in = float(math.sqrt(dx_poc**2 + dz_poc**2))

        # 3. Plate Break Total Separation in inches:
        dx_plate = dx_rel + (pitch_a.hb_in - pitch_b.hb_in)
        dz_plate = dz_rel + (pitch_a.ivb_in - pitch_b.ivb_in)
        plate_dist_in = float(math.sqrt(dx_plate**2 + dz_plate**2))

        ratio, tunnel_score, whiff_boost, is_elite = _score_and_classify(
            rel_dist_in, poc_dist_in, plate_dist_in
        )

        pair_label = f"{pitch_a.pitch_type}-{pitch_b.pitch_type}"

        return PitchTunnelEvaluation(
            pitch_pair_label=pair_label,
            release_distance_in=round(rel_dist_in, 2),
            tunnel_distance_at_poc_in=round(poc_dist_in, 2),
            plate_break_separation_in=round(plate_dist_in, 2),
            break_tunnel_ratio=ratio,
            tunneling_quality_score=tunnel_score,
            whiff_boost_pct=whiff_boost,
            is_elite_tunnel=is_elite,
            data_source=DATA_SOURCE_WHATIF,
        )


def _avg_pitch_kinematics(
    pitcher_mlbam_id: str,
    pitch_type: str,
    date_from: str,
    date_to: str,
    conn: psycopg.Connection,
) -> dict[str, float] | None:
    """Average real Statcast kinematics for one pitcher's one pitch type over a date range."""
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT
                AVG(release_pos_x::double precision) AS x0,
                AVG(release_pos_z::double precision) AS z0,
                AVG(vx0::double precision) AS vx0,
                AVG(vy0::double precision) AS vy0,
                AVG(vz0::double precision) AS vz0,
                AVG(ax::double precision) AS ax,
                AVG(ay::double precision) AS ay,
                AVG(az::double precision) AS az,
                AVG(plate_x::double precision) AS plate_x,
                AVG(plate_z::double precision) AS plate_z,
                COUNT(*) AS n
            FROM raw.statcast_pitch
            WHERE pitcher = %(pitcher_id)s
              AND pitch_type = %(pitch_type)s
              AND game_date BETWEEN %(date_from)s AND %(date_to)s
              AND vy0 IS NOT NULL AND ay IS NOT NULL
              AND release_pos_x IS NOT NULL AND release_pos_z IS NOT NULL
              AND plate_x IS NOT NULL AND plate_z IS NOT NULL
            """,
            {
                "pitcher_id": pitcher_mlbam_id,
                "pitch_type": pitch_type,
                "date_from": date_from,
                "date_to": date_to,
            },
        )
        row = cur.fetchone()

    if row is None or row[-1] == 0 or row[0] is None:
        return None

    keys = ("x0", "z0", "vx0", "vy0", "vz0", "ax", "ay", "az", "plate_x", "plate_z", "n")
    return dict(zip(keys, row, strict=True))


def tunnel_pair_from_statcast(
    pitcher_mlbam_id: str,
    pitch_type_a: str,
    pitch_type_b: str,
    date_from: str,
    date_to: str,
    conn: psycopg.Connection,
) -> PitchTunnelEvaluation | None:
    """Evaluate a real pitcher's two real pitch types' tunneling from Statcast kinematics.

    Averages each pitch type's real release/kinematics/plate-crossing
    columns over the date range, then computes release distance, real
    Tunnel Point separation (via `_position_at_y`, exact projectile-motion
    kinematics -- not the what-if path's `poc_factor` approximation), and
    real plate-break separation (from real `plate_x`/`plate_z`, not
    release + movement addition).

    Returns None when either pitch type has no usable kinematics coverage
    for this pitcher/range, rather than fabricating a value.
    """
    a = _avg_pitch_kinematics(pitcher_mlbam_id, pitch_type_a, date_from, date_to, conn)
    b = _avg_pitch_kinematics(pitcher_mlbam_id, pitch_type_b, date_from, date_to, conn)
    if a is None or b is None:
        return None

    dx_rel = (a["x0"] - b["x0"]) * 12.0
    dz_rel = (a["z0"] - b["z0"]) * 12.0
    rel_dist_in = float(math.sqrt(dx_rel**2 + dz_rel**2))

    pos_a = _position_at_y(
        x0=a["x0"],
        z0=a["z0"],
        vx0=a["vx0"],
        vy0=a["vy0"],
        vz0=a["vz0"],
        ax=a["ax"],
        ay=a["ay"],
        az=a["az"],
        yf=_YF_TUNNEL_FT,
    )
    pos_b = _position_at_y(
        x0=b["x0"],
        z0=b["z0"],
        vx0=b["vx0"],
        vy0=b["vy0"],
        vz0=b["vz0"],
        ax=b["ax"],
        ay=b["ay"],
        az=b["az"],
        yf=_YF_TUNNEL_FT,
    )
    if pos_a is None or pos_b is None:
        return None

    dx_poc = (pos_a[0] - pos_b[0]) * 12.0
    dz_poc = (pos_a[1] - pos_b[1]) * 12.0
    poc_dist_in = float(math.sqrt(dx_poc**2 + dz_poc**2))

    dx_plate = (a["plate_x"] - b["plate_x"]) * 12.0
    dz_plate = (a["plate_z"] - b["plate_z"]) * 12.0
    plate_dist_in = float(math.sqrt(dx_plate**2 + dz_plate**2))

    ratio, tunnel_score, whiff_boost, is_elite = _score_and_classify(
        rel_dist_in, poc_dist_in, plate_dist_in
    )

    return PitchTunnelEvaluation(
        pitch_pair_label=f"{pitch_type_a}-{pitch_type_b}",
        release_distance_in=round(rel_dist_in, 2),
        tunnel_distance_at_poc_in=round(poc_dist_in, 2),
        plate_break_separation_in=round(plate_dist_in, 2),
        break_tunnel_ratio=ratio,
        tunneling_quality_score=tunnel_score,
        whiff_boost_pct=whiff_boost,
        is_elite_tunnel=is_elite,
        data_source=DATA_SOURCE_STATCAST,
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
