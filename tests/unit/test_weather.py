"""Unit tests for Stadium 3D Vector Wind & Micro-Climate Physics Engine (WEATHER-01, ADR-137)."""

from mlb_baseball.model.weather import (
    StadiumOrientation,
    StadiumWeatherPhysicsEngine,
    WeatherConditions,
    health_check,
)


def test_wrigley_field_wind_blowing_out_and_in():
    """Verify wind vector decomposition correctly computes tailwind when blowing OUT vs IN."""
    engine = StadiumWeatherPhysicsEngine()

    wrigley = StadiumOrientation(
        venue_id="wrigley",
        venue_name="Wrigley Field",
        home_to_center_azimuth_deg=22.5,  # Faces NNE
        altitude_feet=600.0,
    )

    # 1. Wind from SSW (202.5°) at 18 mph -> Blowing directly OUT to CF
    wind_out = WeatherConditions(
        temperature_f=75.0, wind_speed_mph=18.0, wind_from_direction_deg=202.5
    )
    impact_out = engine.compute_weather_impact(wrigley, wind_out)

    assert abs(impact_out.effective_tailwind_mph - 18.0) < 0.2
    assert abs(impact_out.effective_crosswind_mph) < 0.2
    assert impact_out.fly_ball_distance_delta_ft > 50.0
    assert impact_out.home_run_multiplier > 1.50
    assert impact_out.total_runs_multiplier > 1.25

    # 2. Wind from NNE (22.5°) at 18 mph -> Blowing directly IN from CF
    wind_in = WeatherConditions(
        temperature_f=55.0, wind_speed_mph=18.0, wind_from_direction_deg=22.5
    )
    impact_in = engine.compute_weather_impact(wrigley, wind_in)

    assert abs(impact_in.effective_tailwind_mph - (-18.0)) < 0.2
    assert impact_in.fly_ball_distance_delta_ft < -50.0
    assert impact_in.home_run_multiplier < 0.60
    assert impact_in.total_runs_multiplier < 0.80


def test_coors_field_altitude_thin_air():
    """Verify Coors Field high altitude generates thin air (low ADI) and extra ball carry."""
    engine = StadiumWeatherPhysicsEngine()

    coors = StadiumOrientation(
        venue_id="coors",
        venue_name="Coors Field",
        home_to_center_azimuth_deg=0.0,  # Dead North
        altitude_feet=5200.0,
    )

    calm_hot = WeatherConditions(temperature_f=85.0, wind_speed_mph=0.0, relative_humidity_pct=25.0)
    impact = engine.compute_weather_impact(coors, calm_hot)

    # ADI at 5200ft should be ~80-84 (16-20% thinner than sea level)
    assert impact.air_density_index < 85.0
    assert impact.fly_ball_distance_delta_ft > 5.0  # Extra carry purely from thin air
    assert impact.home_run_multiplier > 1.05


def test_dome_bypass():
    """Verify closed dome ignores wind and sets neutral 100 ADI."""
    engine = StadiumWeatherPhysicsEngine()

    dome = StadiumOrientation(
        "tropicana", "Tropicana Field", home_to_center_azimuth_deg=45.0, is_dome_or_retractable=True
    )
    crazy_wind = WeatherConditions(wind_speed_mph=45.0, wind_from_direction_deg=180.0)

    impact = engine.compute_weather_impact(dome, crazy_wind)

    assert impact.effective_tailwind_mph == 0.0
    assert impact.air_density_index == 100.0
    assert impact.home_run_multiplier == 1.00
    assert impact.total_runs_multiplier == 1.00


def test_weather_health_check():
    """Verify weather health check passes."""
    checks = health_check()
    assert len(checks) == 1
    assert checks[0].ok is True
    assert "Wrigley wind verified" in checks[0].detail
