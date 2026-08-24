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
    assert "SVG vector renderers verified" in checks[0].detail
