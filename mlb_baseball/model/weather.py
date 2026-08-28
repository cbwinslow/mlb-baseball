"""Stadium 3D Vector Wind & Micro-Climate Physics Engine (WEATHER-01, ADR-137)."""

from __future__ import annotations

import dataclasses
import math
from typing import Protocol

import numpy as np

from mlb_baseball.health import Check


@dataclasses.dataclass(frozen=True)
class StadiumOrientation:
    """Venue compass alignment and physical geographic parameters."""

    venue_id: str
    venue_name: str
    home_to_center_azimuth_deg: float  # Degrees from North (0° = N, 90° = E, 180° = S, 270° = W)
    altitude_feet: float = 0.0  # e.g. 5200 ft for Coors Field
    is_dome_or_retractable: bool = False


@dataclasses.dataclass(frozen=True)
class WeatherConditions:
    """Environmental atmospheric conditions at game start."""

    temperature_f: float = 72.0
    wind_speed_mph: float = 0.0
    wind_from_direction_deg: float = (
        0.0  # Standard meteorological direction wind blows FROM (0° = N)
    )
    relative_humidity_pct: float = 50.0
    barometric_pressure_inhg: float = 29.92


@dataclasses.dataclass(frozen=True)
class WeatherPhysicsImpact:
    """Calculated aerodynamic trajectory adjustments and run multipliers."""

    effective_tailwind_mph: float  # Positive = blowing OUT toward CF, Negative = blowing IN
    effective_crosswind_mph: float  # Positive = blowing LF to RF, Negative = blowing RF to LF
    air_density_index: float  # 100.0 = Sea Level Standard (59°F, 29.92 inHg, 0% RH)
    fly_ball_distance_delta_ft: float  # Net feet added/subtracted to 400ft fly balls
    home_run_multiplier: float  # Expected HR rate scaling (e.g. 1.15x for +15% HRs)
    total_runs_multiplier: float  # Expected Game Total runs scaling (e.g. 1.08x)


class BaseWeatherPhysicsEngine(Protocol):
    """Polymorphic protocol for stadium weather physics engines."""

    def compute_weather_impact(
        self,
        stadium: StadiumOrientation,
        weather: WeatherConditions,
    ) -> WeatherPhysicsImpact:
        """Compute 3D wind vectors, ADI, and trajectory multipliers."""
        ...


class StadiumWeatherPhysicsEngine:
    """Ballistics simulator for stadium micro-climates (WEATHER-01)."""

    def compute_weather_impact(
        self,
        stadium: StadiumOrientation,
        weather: WeatherConditions,
    ) -> WeatherPhysicsImpact:
        """Calculate effective wind components, ADI, and run environment scaling."""
        # 1. Closed Dome Bypass
        if stadium.is_dome_or_retractable:
            return WeatherPhysicsImpact(
                effective_tailwind_mph=0.0,
                effective_crosswind_mph=0.0,
                air_density_index=100.0,
                fly_ball_distance_delta_ft=0.0,
                home_run_multiplier=1.00,
                total_runs_multiplier=1.00,
            )

        # 2. Vector Wind Decomposition
        # Meteorological wind direction air travels is (wind_from + 180°)
        wind_travel_dir_deg = (weather.wind_from_direction_deg + 180.0) % 360.0
        # Relative angle between stadium azimuth and wind travel direction
        rel_angle_deg = wind_travel_dir_deg - stadium.home_to_center_azimuth_deg
        rel_angle_rad = math.radians(rel_angle_deg)

        # Positive = Blowing OUT to CF, Negative = Blowing IN from CF
        tailwind = weather.wind_speed_mph * math.cos(rel_angle_rad)
        # Positive = LF to RF, Negative = RF to LF
        crosswind = weather.wind_speed_mph * math.sin(rel_angle_rad)

        # 3. Air Density Index (ADI) - Alan Nathan formulation
        # Temperature in Rankine
        temp_rankine = weather.temperature_f + 459.67
        # Vapor pressure approximation (Magnus-Tetens)
        # Saturated vapor pressure (inHg)
        sat_vp = 0.180 * math.exp(
            (17.27 * (weather.temperature_f - 32.0)) / (weather.temperature_f + 395.0)
        )
        act_vp = sat_vp * (weather.relative_humidity_pct / 100.0)

        # Dry and moist air ratio
        density_ratio = (
            ((weather.barometric_pressure_inhg - (0.3783 * act_vp)) / 29.92)
            * (518.67 / temp_rankine)
            * math.exp(-stadium.altitude_feet / 28000.0)
        )
        adi = round(density_ratio * 100.0, 1)

        # 4. Trajectory & Run Multiplier Scaling
        # Each mph of tailwind adds ~3.0 ft of fly ball distance
        # Each 1.0 drop in ADI (thinner air) adds ~0.35 ft of fly ball distance
        dist_delta = (tailwind * 3.0) + ((100.0 - adi) * 0.35)

        # Each 10 ft of distance shifts HR probability by ~15% and Game Totals by ~6%
        hr_mult = float(np.clip(1.0 + (dist_delta * 0.015), 0.50, 2.00))
        runs_mult = float(np.clip(1.0 + (dist_delta * 0.006), 0.70, 1.50))

        return WeatherPhysicsImpact(
            effective_tailwind_mph=round(tailwind, 1),
            effective_crosswind_mph=round(crosswind, 1),
            air_density_index=adi,
            fly_ball_distance_delta_ft=round(dist_delta, 1),
            home_run_multiplier=round(hr_mult, 3),
            total_runs_multiplier=round(runs_mult, 3),
        )


def health_check() -> list[Check]:
    """Operational health check for the Stadium Weather Physics Engine (WEATHER-01)."""
    checks: list[Check] = []
    try:
        engine = StadiumWeatherPhysicsEngine()
        # Wrigley Field (22.5° NNE) with 15mph SW wind (202.5° blowing OUT)
        wrigley = StadiumOrientation(
            "wrigley", "Wrigley Field", home_to_center_azimuth_deg=22.5, altitude_feet=600
        )
        weather = WeatherConditions(
            temperature_f=85.0,
            wind_speed_mph=15.0,
            wind_from_direction_deg=202.5,
            relative_humidity_pct=45.0,
        )

        impact = engine.compute_weather_impact(wrigley, weather)

        # Wind blowing directly OUT to CF (+15.0 mph tailwind)
        if (
            impact.effective_tailwind_mph > 14.0
            and impact.fly_ball_distance_delta_ft > 40.0
            and impact.home_run_multiplier > 1.40
        ):
            checks.append(
                Check(
                    "stadium weather physics engine",
                    True,
                    f"Wrigley wind verified (+{impact.fly_ball_distance_delta_ft:.1f}ft)",
                )
            )
        else:
            checks.append(
                Check("stadium weather physics engine", False, f"Unexpected wind vector: {impact}")
            )
    except Exception as exc:
        checks.append(Check("stadium weather physics engine", False, str(exc)))
    return checks
