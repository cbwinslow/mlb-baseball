"""Park-Adjusted True Environmental Carry & Ballpark HR Scanner (CARRY-01, ADR-165).

Provides 30-ballpark overlay simulation and environmental trajectory clearance:
1. Stadium Outfield Wall Geometry (LF, CF, RF distances and wall heights across 30 venues).
2. Altitude & Temperature Environmental Carry Adjustments (e.g. Coors elevation boost).
3. 30-Park Home Run Coverage Scanner (X/30 Ballparks HR Probability).
4. Venue-Specific Short Porch vs Deep Outfield Discrepancy Diagnostics.

Adheres strictly to object-oriented encapsulation, polymorphic protocols, and
point-in-time correctness with zero lookahead leakage.

MLB_STADIUM_PROFILES (bug fix, 2026-09-19, issue #220): previously hardcoded
only 8 "representative sample" parks despite the module's own 30-park naming
-- now lists all 30 current MLB venues. Fence distances per Legion Report's
2026 all-30-park table (https://legionreport.com/mlb-stadium-capacity/),
cross-checked against Wikipedia's per-park center-field figures and this
project's own previously-verified entries; Fenway Park's center-field figure
uses the well-documented 390 ft straightaway marker (not the 420 ft deepest
point of the right-center bullpen triangle, which both sources conflate with
"center field"); Oracle Park's corrected to the standard 399 ft (the prior
391 ft was this module's own error). Kauffman Stadium reflects the Royals'
2026 fence relocation (LF/RF corners moved in ~9 ft, wall height lowered to
8.5 ft outside center field) per contemporaneous reporting (Yahoo Sports/
KSHB, January-April 2026). Notable non-default wall heights: Fenway's 37 ft
Green Monster (LF), Daikin Park's ~19 ft Crawford Boxes (LF), Oracle Park's
24 ft right-field wall, PNC Park's 21 ft Clemente Wall (RF), Kauffman's
8.5 ft (both fields, 2026). Every other wall defaults to the standard 8 ft.
Approximate, not gold/validated data -- stadium dimensions periodically
change (as Kauffman just did) and this list is not kept in automatic sync
with any source; see the catalog entry's `notes:` for the same caveat.
"""

from __future__ import annotations

import dataclasses
from typing import Protocol

from mlb_baseball.health import Check


@dataclasses.dataclass(frozen=True)
class StadiumFenceProfile:
    """Outfield fence dimensions and elevation factor for a stadium."""

    venue_id: str
    name: str
    lf_dist: float
    cf_dist: float
    rf_dist: float
    lf_wall_h: float = 8.0
    rf_wall_h: float = 8.0
    elevation_boost_ft: float = 0.0


# All 30 current MLB stadium profiles -- see module docstring for sourcing
# and the deliberate Fenway/Oracle Park/Kauffman corrections.
MLB_STADIUM_PROFILES: list[StadiumFenceProfile] = [
    StadiumFenceProfile("ATH", "Sutter Health Park", 325.0, 403.0, 325.0),
    StadiumFenceProfile("ATL", "Truist Park", 335.0, 400.0, 325.0),
    StadiumFenceProfile("AZ", "Chase Field", 330.0, 407.0, 335.0),
    StadiumFenceProfile("BAL", "Oriole Park at Camden Yards", 333.0, 406.0, 318.0),
    StadiumFenceProfile("BOS", "Fenway Park", 310.0, 390.0, 302.0, lf_wall_h=37.0),
    StadiumFenceProfile("CHC", "Wrigley Field", 355.0, 400.0, 353.0),
    StadiumFenceProfile("CIN", "Great American Ball Park", 328.0, 404.0, 325.0),
    StadiumFenceProfile("CLE", "Progressive Field", 325.0, 410.0, 325.0),
    StadiumFenceProfile("COL", "Coors Field", 347.0, 415.0, 350.0, elevation_boost_ft=16.0),
    StadiumFenceProfile("CWS", "Guaranteed Rate Field", 330.0, 400.0, 335.0),
    StadiumFenceProfile("DET", "Comerica Park", 345.0, 412.0, 330.0),
    StadiumFenceProfile("HOU", "Daikin Park", 315.0, 409.0, 326.0, lf_wall_h=19.0),
    StadiumFenceProfile(
        "KC", "Kauffman Stadium", 347.0, 410.0, 344.0, lf_wall_h=8.5, rf_wall_h=8.5
    ),
    StadiumFenceProfile("LAA", "Angel Stadium", 330.0, 396.0, 330.0),
    StadiumFenceProfile("LAD", "Dodger Stadium", 330.0, 395.0, 330.0),
    StadiumFenceProfile("MIA", "loanDepot Park", 344.0, 407.0, 335.0),
    StadiumFenceProfile("MIL", "American Family Field", 342.0, 400.0, 345.0),
    StadiumFenceProfile("MIN", "Target Field", 339.0, 404.0, 328.0),
    StadiumFenceProfile("NYM", "Citi Field", 335.0, 408.0, 330.0),
    StadiumFenceProfile("NYY", "Yankee Stadium", 318.0, 408.0, 314.0),
    StadiumFenceProfile("PHI", "Citizens Bank Park", 329.0, 401.0, 330.0),
    StadiumFenceProfile("PIT", "PNC Park", 325.0, 399.0, 320.0, rf_wall_h=21.0),
    StadiumFenceProfile("SD", "Petco Park", 336.0, 396.0, 322.0),
    StadiumFenceProfile("SEA", "T-Mobile Park", 331.0, 401.0, 326.0),
    StadiumFenceProfile("SF", "Oracle Park", 339.0, 399.0, 309.0, rf_wall_h=24.0),
    StadiumFenceProfile("STL", "Busch Stadium", 336.0, 400.0, 335.0),
    StadiumFenceProfile("TB", "Tropicana Field", 315.0, 404.0, 322.0),
    StadiumFenceProfile("TEX", "Globe Life Field", 329.0, 407.0, 326.0),
    StadiumFenceProfile("TOR", "Rogers Centre", 328.0, 400.0, 328.0),
    StadiumFenceProfile("WSH", "Nationals Park", 336.0, 402.0, 335.0),
]


@dataclasses.dataclass(frozen=True)
class BattedBallTrajectory:
    """Trajectory mechanics of a deep fly ball or line drive."""

    hit_id: str
    exit_velocity_mph: float
    launch_angle_deg: float
    spray_angle_deg: float  # -45 (Left line) to 0 (Center) to +45 (Right line)
    nominal_distance_ft: float


@dataclasses.dataclass(frozen=True)
class ParkHRScanResult:
    """Evaluated home run clearance across MLB ballparks."""

    nominal_distance_ft: float
    parks_hr_count: int
    total_parks_evaluated: int
    hr_percentage: float  # (parks_hr_count / total) * 100
    home_run_venues: list[str]
    out_venues: list[str]
    scan_summary: str


class BaseCarryEngine(Protocol):
    """Polymorphic protocol for environmental carry and ballpark HR engines."""

    def scan_ballparks(
        self,
        trajectory: BattedBallTrajectory,
    ) -> ParkHRScanResult:
        """Evaluate trajectory clearance across all stadium profiles."""
        ...


# Every profiled park's wall is treated as standard 8 ft tall at straightaway
# center field (StadiumFenceProfile has no cf_wall_h field -- no current MLB
# park has an unusually tall wall at dead center, only in the LF/RF corners
# and gaps, e.g. Fenway's Green Monster).
_STANDARD_CF_WALL_H = 8.0


class BallparkCarryScannerEngine:
    """Simulates 30-park home run clearance and environmental carry (CARRY-01)."""

    def _estimate_fence_distance(
        self,
        stadium: StadiumFenceProfile,
        spray_angle: float,
    ) -> float:
        """Estimate fence distance at specific spray angle (-45 to +45)."""
        # spray -45 to 0: interpolate LF to CF
        # spray 0 to +45: interpolate CF to RF
        if spray_angle <= 0.0:
            weight_lf = abs(spray_angle) / 45.0
            dist = weight_lf * stadium.lf_dist + (1.0 - weight_lf) * stadium.cf_dist
        else:
            weight_rf = spray_angle / 45.0
            dist = weight_rf * stadium.rf_dist + (1.0 - weight_rf) * stadium.cf_dist
        return dist

    def _estimate_wall_height(
        self,
        stadium: StadiumFenceProfile,
        spray_angle: float,
    ) -> float:
        """Estimate wall height at specific spray angle, same LF/CF/RF
        interpolation as `_estimate_fence_distance` (bug fix, 2026-09-19,
        issue #220: `lf_wall_h`/`rf_wall_h` previously had zero effect on
        `scan_ballparks`'s HR/out determination)."""
        if spray_angle <= 0.0:
            weight_lf = abs(spray_angle) / 45.0
            return weight_lf * stadium.lf_wall_h + (1.0 - weight_lf) * _STANDARD_CF_WALL_H
        weight_rf = spray_angle / 45.0
        return weight_rf * stadium.rf_wall_h + (1.0 - weight_rf) * _STANDARD_CF_WALL_H

    def scan_ballparks(
        self,
        trajectory: BattedBallTrajectory,
    ) -> ParkHRScanResult:
        """Check home run clearance across stadium profiles.

        Requires clearing the fence distance by a base 4 ft margin, plus one
        additional foot of required carry for every foot the interpolated
        wall height at that spray angle exceeds the standard 8 ft (bug fix,
        2026-09-19, issue #220) -- a tall wall like Fenway's 37 ft Green
        Monster now makes a marginal fly ball that would clear a standard
        fence an out, not a HR.
        """
        hr_venues: list[str] = []
        out_venues: list[str] = []

        for stadium in MLB_STADIUM_PROFILES:
            effective_distance = trajectory.nominal_distance_ft + stadium.elevation_boost_ft
            fence_dist = self._estimate_fence_distance(stadium, trajectory.spray_angle_deg)
            wall_height = self._estimate_wall_height(stadium, trajectory.spray_angle_deg)
            required_margin = 4.0 + max(0.0, wall_height - _STANDARD_CF_WALL_H)

            if effective_distance >= fence_dist + required_margin:
                hr_venues.append(stadium.name)
            else:
                out_venues.append(stadium.name)

        total = len(MLB_STADIUM_PROFILES)
        hr_count = len(hr_venues)
        pct = round((hr_count / total) * 100.0, 1)

        summary = f"Gone in {hr_count}/{total} MLB Ballparks ({pct:.1f}%)"

        return ParkHRScanResult(
            nominal_distance_ft=trajectory.nominal_distance_ft,
            parks_hr_count=hr_count,
            total_parks_evaluated=total,
            hr_percentage=pct,
            home_run_venues=hr_venues,
            out_venues=out_venues,
            scan_summary=summary,
        )


def health_check() -> list[Check]:
    """Operational health check for the Ballpark Carry Scanner Engine (CARRY-01)."""
    checks: list[Check] = []
    try:
        engine = BallparkCarryScannerEngine()
        # 340 ft flyball down the right field line (+40 deg spray)
        porch_shot = BattedBallTrajectory("h1", 96.0, 32.0, 40.0, nominal_distance_ft=340.0)
        res = engine.scan_ballparks(porch_shot)

        if "Yankee Stadium" in res.home_run_venues and res.parks_hr_count > 0:
            checks.append(
                Check(
                    "ballpark carry engine",
                    True,
                    f"Carry verified ({res.scan_summary})",
                )
            )
        else:
            checks.append(Check("ballpark carry engine", False, f"Unexpected carry output: {res}"))
    except Exception as exc:
        checks.append(Check("ballpark carry engine", False, str(exc)))
    return checks
