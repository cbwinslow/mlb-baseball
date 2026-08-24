"""Unit tests for Visual Asset & Vector Chart Generation Engine (VISUAL-01, ADR-131)."""

from mlb_baseball.model.heatmap import BattedBallBallisticsEngine, StrikeZoneKDEMonitor
from mlb_baseball.visual import (
    ChartType,
    DiamondSprayChartRenderer,
    StrikeZoneHeatmapRenderer,
    WinExpectancyGraphRenderer,
    health_check,
)


def test_strike_zone_heatmap_svg_generation():
    """Verify StrikeZoneHeatmapRenderer creates compliant SVG with strike zone boxes and colors."""
    renderer = StrikeZoneHeatmapRenderer(width=300, height=350)
    kde = StrikeZoneKDEMonitor()
    grid = kde.compute_density_grid([0.1, -0.2, 0.5], [2.4, 3.1, 1.8], grid_size=(6, 6))

    chart = renderer.render(grid, title="Test Strike Zone")

    assert chart.chart_type == ChartType.STRIKE_ZONE_HEATMAP
    assert chart.width_px == 300
    assert chart.height_px == 350
    assert "<svg" in chart.svg_content
    assert "</svg>" in chart.svg_content
    assert "Test Strike Zone" in chart.svg_content
    assert 'stroke="#ffffff"' in chart.svg_content  # Strike zone border


def test_diamond_spray_chart_svg_generation():
    """Verify DiamondSprayChartRenderer creates diamond geometry and hit markers."""
    renderer = DiamondSprayChartRenderer(width=400, height=400)
    ballistics = BattedBallBallisticsEngine()
    hits = [
        ballistics.compute_field_coordinates("h1", 108.0, 28.0, -10.0),  # Barrel
        ballistics.compute_field_coordinates("h2", 96.0, 15.0, 20.0),  # Hard hit
        ballistics.compute_field_coordinates("h3", 80.0, 45.0, 0.0),  # Soft popup
    ]

    chart = renderer.render(hits, title="Batter Spray Map")

    assert chart.chart_type == ChartType.DIAMOND_SPRAY_CHART
    assert "<svg" in chart.svg_content
    assert "#fbbf24" in chart.svg_content  # Gold barrel marker
    assert "#ef4444" in chart.svg_content  # Red hard hit marker
    assert "#38bdf8" in chart.svg_content  # Cyan soft marker


def test_win_expectancy_graph_svg_generation():
    """Verify WinExpectancyGraphRenderer creates play-by-play WE curve with baseline."""
    renderer = WinExpectancyGraphRenderer(width=500, height=200)
    we_plays = [
        (1, 0.50, 1.0),
        (2, 0.55, 1.2),
        (3, 0.40, 2.1),
        (4, 0.78, 3.5),
        (5, 1.00, 4.0),
    ]

    chart = renderer.render(we_plays, home_team="LAD", away_team="NYY", title="Game 7 WE Worm")

    assert chart.chart_type == ChartType.WIN_EXPECTANCY_WORM
    assert "<svg" in chart.svg_content
    assert "Game 7 WE Worm (NYY @ LAD)" in chart.svg_content
    assert "50%" in chart.svg_content


def test_visual_health_check():
    """Verify visual engine health check passes."""
    checks = health_check()
    assert len(checks) == 1
    assert checks[0].ok is True
    assert "SVG renderers verified" in checks[0].detail


def test_radar_chart_svg_generation():
    """Verify RadarChartRenderer creates multi-axis SVG spider chart."""
    from mlb_baseball.visual import (
        PlayerRadarProfile,
        RadarChartRenderer,
        RadarDimension,
    )

    renderer = RadarChartRenderer()
    dims = [
        RadarDimension("Contact", 85.0),
        RadarDimension("Power", 90.0),
        RadarDimension("Discipline", 95.0),
        RadarDimension("Speed", 55.0),
        RadarDimension("Defense", 70.0),
    ]
    profile = PlayerRadarProfile("Juan Soto Scouting Radar", dims)
    chart = renderer.render(profile)

    assert chart.width_px == 500
    assert chart.height_px == 500
    assert "<svg" in chart.svg_content
    assert "Juan Soto Scouting Radar" in chart.svg_content
    assert "Contact (85)" in chart.svg_content


def test_odds_movement_chart_svg_generation():
    """Verify OddsMovementChartRenderer creates time-series line chart with steam markers."""
    from mlb_baseball.visual import (
        MarketOddsTimeline,
        OddsMovementChartRenderer,
        OddsMovementPoint,
    )

    renderer = OddsMovementChartRenderer()
    pts = [
        OddsMovementPoint("09:00", 1.95, 1.95),
        OddsMovementPoint("12:00", 1.85, 2.05),
        OddsMovementPoint("16:00", 1.70, 2.25, is_steam_move=True),
        OddsMovementPoint("19:00", 1.68, 2.30),
    ]
    timeline = MarketOddsTimeline("NYY vs BOS Odds Movement", "NYY", "BOS", pts)
    chart = renderer.render(timeline)

    assert chart.width_px == 600
    assert chart.height_px == 350
    assert "<svg" in chart.svg_content
    assert "NYY vs BOS Odds Movement" in chart.svg_content
    assert "polyline" in chart.svg_content
    assert "circle" in chart.svg_content  # Steam marker


def test_pitch_break_chart_svg_generation():
    """Verify PitchBreakChartRenderer generates Cartesian 2D pitch movement chart."""
    from mlb_baseball.visual import (
        PitchBreakChartRenderer,
        PitchBreakObservation,
        PitcherArsenalBreakProfile,
    )

    renderer = PitchBreakChartRenderer()
    pitches = [
        PitchBreakObservation("FF", 98.5, -8.5, 17.5),
        PitchBreakObservation("SL", 87.0, 6.0, 1.5),
        PitchBreakObservation("CH", 89.0, -14.0, 6.0),
    ]
    profile = PitcherArsenalBreakProfile("Paul Skenes", pitches)
    chart = renderer.render(profile)

    assert chart.width_px == 500
    assert chart.height_px == 500
    assert "<svg" in chart.svg_content
    assert "Paul Skenes Arsenal Movement" in chart.svg_content
    assert "FF (98)" in chart.svg_content
    assert "Arm Side HB" in chart.svg_content


def test_inning_score_flow_svg_generation():
    """Verify InningScoreFlowRenderer generates stepped game score flow chart."""
    from mlb_baseball.visual import (
        GameScoreFlowProfile,
        InningScoreFlowRenderer,
        InningScoreStep,
    )

    renderer = InningScoreFlowRenderer()
    innings = [
        InningScoreStep(1, 0, 0, 0, 0),
        InningScoreStep(2, 0, 2, 0, 2),
        InningScoreStep(3, 1, 0, 1, 2),
        InningScoreStep(4, 0, 1, 1, 3),
        InningScoreStep(5, 2, 0, 3, 3),
    ]
    profile = GameScoreFlowProfile("LAD 3, SF 3 Live Game Flow", "LAD", "SF", innings)
    chart = renderer.render(profile)

    assert chart.width_px == 600
    assert chart.height_px == 350
    assert "<svg" in chart.svg_content
    assert "LAD 3, SF 3 Live Game Flow" in chart.svg_content
    assert "Inn 1" in chart.svg_content
    assert "polyline" in chart.svg_content


def test_re24_matrix_heatmap_svg_generation():
    """Verify RunExpectancyHeatmapRenderer generates 24-state SVG matrix heatmap."""
    from mlb_baseball.visual import (
        BaseOutRunExpectancyGrid,
        RunExpectancyHeatmapRenderer,
    )

    renderer = RunExpectancyHeatmapRenderer()
    grid = BaseOutRunExpectancyGrid("2024 MLB Run Expectancy Matrix (RE24)")
    chart = renderer.render(grid)

    assert chart.width_px == 560
    assert chart.height_px == 480
    assert "<svg" in chart.svg_content
    assert "2024 MLB Run Expectancy Matrix (RE24)" in chart.svg_content
    assert "0 Outs" in chart.svg_content
    assert "Bases Loaded" in chart.svg_content
    assert "rect" in chart.svg_content


def test_spatial_hexbin_strike_zone_svg_generation():
    """Verify SpatialHexbinVisualizerRenderer generates 2D strike zone hexbin map."""
    from mlb_baseball.visual import (
        HexbinPitchObservation,
        SpatialHexbinProfile,
        SpatialHexbinVisualizerRenderer,
    )

    renderer = SpatialHexbinVisualizerRenderer()
    pitches = [
        HexbinPitchObservation(0.0, 2.4, "FF", True),
        HexbinPitchObservation(0.3, 2.8, "SL", True),
        HexbinPitchObservation(-0.9, 1.4, "CH", False),
    ]
    prof = SpatialHexbinProfile("Shohei Ohtani Spatial Map", "Ohtani", "Pitcher", pitches)
    chart = renderer.render(prof)

    assert chart.width_px == 500
    assert chart.height_px == 500
    assert "<svg" in chart.svg_content
    assert "Shohei Ohtani Spatial Map" in chart.svg_content
    assert "rect" in chart.svg_content
    assert "polygon" in chart.svg_content


def test_matchup_comparison_card_svg_generation():
    """Verify MatchupComparisonCardRenderer generates side-by-side scouting card."""
    from mlb_baseball.visual import (
        MatchupCardProfile,
        MatchupComparisonCardRenderer,
        MatchupMetricComparison,
    )

    renderer = MatchupComparisonCardRenderer()
    comps = [
        MatchupMetricComparison("wOBA", 0.90, 0.60, ".410", ".305"),
        MatchupMetricComparison("Hard-Hit%", 0.85, 0.45, "52.0%", "36.0%"),
        MatchupMetricComparison("K%", 0.30, 0.80, "18.0%", "32.0%"),
    ]
    prof = MatchupCardProfile(
        "Judge vs Cole Scouting Card", "Aaron Judge", "Gerrit Cole", "BATTER_ADVANTAGE", comps
    )
    chart = renderer.render(prof)

    assert chart.width_px == 580
    assert chart.height_px == 380
    assert "<svg" in chart.svg_content
    assert "Judge vs Cole Scouting Card" in chart.svg_content
    assert "BATTER ADVANTAGE" in chart.svg_content
    assert "Aaron Judge" in chart.svg_content
    assert "Gerrit Cole" in chart.svg_content
