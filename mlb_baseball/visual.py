"""Visual Asset & Vector Chart Generation Engine (VISUAL-01, ADR-131)."""

from __future__ import annotations

import dataclasses
import enum
import math
from collections.abc import Sequence
from typing import Any, Protocol

from mlb_baseball.health import Check
from mlb_baseball.model.heatmap import BattedBallTrajectoryPoint, SpatialDensityGrid


class ChartType(enum.Enum):
    """Types of vector charts supported by the visual engine."""

    STRIKE_ZONE_HEATMAP = "strike_zone_heatmap"
    DIAMOND_SPRAY_CHART = "diamond_spray_chart"
    WIN_EXPECTANCY_WORM = "win_expectancy_worm"
    PITCH_MOVEMENT_PLOT = "pitch_movement_plot"
    SPIDER_RADAR_CHART = "spider_radar_chart"
    ODDS_MOVEMENT_TIMELINE = "odds_movement_timeline"
    PITCH_BREAK_CHART = "pitch_break_chart"
    INNING_SCORE_FLOW = "inning_score_flow"
    RUN_EXPECTANCY_HEATMAP = "run_expectancy_heatmap"
    SPATIAL_HEXBIN_MAP = "spatial_hexbin_map"
    MATCHUP_COMPARISON_CARD = "matchup_comparison_card"
    WIN_PROBABILITY_REPLAY = "win_probability_replay"
    PITCH_TRAJECTORY_3D = "pitch_trajectory_3d"
    ZONE_SURFACE_CONTOUR = "zone_surface_contour"
    SPIN_AXIS_CLOCK = "spin_axis_clock"
    SEPARATION_DIAMOND_PLOT = "separation_diamond_plot"
    SPRAY_ELEVATION_ROSE = "spray_elevation_rose"
    RELEASE_WINDOW_BOX = "release_window_box"
    ATTACK_ZONE_9X9_GRID = "attack_zone_9x9_grid"


@dataclasses.dataclass(frozen=True)
class GeneratedVectorChart:
    """Encapsulates a rendered vector chart artifact with SVG markup and dimensions."""

    chart_type: ChartType
    title: str
    svg_content: str
    width_px: int
    height_px: int


class BaseVectorChartRenderer(Protocol):
    """Polymorphic protocol for rendering visual baseball charts into SVG."""

    def render(self, data: Any, title: str) -> GeneratedVectorChart:
        """Render underlying quantitative data into an SVG chart."""
        ...


class StrikeZoneHeatmapRenderer:
    """Renders 2D KDE probability density grid and attack zones into an SVG strike zone graphic."""

    def __init__(self, width: int = 400, height: int = 450) -> None:
        self.width = width
        self.height = height

    def _coord_to_svg(self, px: float, pz: float) -> tuple[float, float]:
        """Convert plate coordinates (ft) to SVG pixel coordinates."""
        # x range: [-2.0, 2.0] -> [40, width - 40]
        # z range: [0.5, 4.5] -> [height - 40, 40] (SVG y is inverted)
        x_norm = (px - (-2.0)) / (2.0 - (-2.0))
        z_norm = (pz - 0.5) / (4.5 - 0.5)

        svg_x = 40.0 + x_norm * (self.width - 80.0)
        svg_y = (self.height - 40.0) - (z_norm * (self.height - 80.0))
        return round(svg_x, 1), round(svg_y, 1)

    def render(
        self, grid: SpatialDensityGrid, title: str = "Strike Zone Heatmap"
    ) -> GeneratedVectorChart:
        """Generate SVG markup representing 2D KDE probability density over strike zone."""
        svg_parts = [
            (
                f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {self.width} {self.height}" '
                f'width="{self.width}" height="{self.height}" style="background-color: #0f172a;">'
            ),
            f'<text x="{self.width / 2}" y="25" fill="#f8fafc" font-size="14" font-weight="bold" '
            f'text-anchor="middle">{title}</text>',
        ]

        # Draw discretized density cells
        rows = grid.rows
        cols = grid.cols
        max_d = max([max(r) for r in grid.density_matrix]) if grid.density_matrix else 1.0
        max_d = max(max_d, 1e-6)

        x_lin = [grid.x_min + i * (grid.x_max - grid.x_min) / max(1, cols - 1) for i in range(cols)]
        z_lin = [grid.z_min + j * (grid.z_max - grid.z_min) / max(1, rows - 1) for j in range(rows)]

        cell_w = (self.width - 80.0) / cols
        cell_h = (self.height - 80.0) / rows

        for r_idx in range(rows):
            for c_idx in range(cols):
                d_val = grid.density_matrix[r_idx][c_idx]
                if d_val <= 0:
                    continue
                intensity = min(1.0, d_val / max_d)
                # Thermal colormap: dark blue -> red -> yellow
                red = int(255 * intensity)
                blue = int(255 * (1.0 - intensity))
                alpha = round(0.15 + (0.75 * intensity), 2)
                fill_color = f"rgba({red}, 50, {blue}, {alpha})"

                px_center = x_lin[c_idx]
                pz_center = z_lin[r_idx]
                sx, sy = self._coord_to_svg(px_center, pz_center)

                svg_parts.append(
                    f'<rect x="{sx - cell_w / 2:.1f}" y="{sy - cell_h / 2:.1f}" '
                    f'width="{cell_w:.1f}" height="{cell_h:.1f}" fill="{fill_color}" />'
                )

        # Draw Rule-Book Strike Zone (width: +/- 0.708 ft, height: 1.5 to 3.5 ft)
        sz_top_left = self._coord_to_svg(-0.708, 3.5)
        sz_bot_right = self._coord_to_svg(0.708, 1.5)
        sz_w = abs(sz_bot_right[0] - sz_top_left[0])
        sz_h = abs(sz_bot_right[1] - sz_top_left[1])

        svg_parts.append(
            f'<rect x="{sz_top_left[0]}" y="{sz_top_left[1]}" width="{sz_w}" height="{sz_h}" '
            f'fill="none" stroke="#ffffff" stroke-width="2.5" stroke-dasharray="none" />'
        )

        # Draw Inner Heart Zone
        hz_top_left = self._coord_to_svg(-0.55, 3.17)
        hz_bot_right = self._coord_to_svg(0.55, 1.83)
        hz_w = abs(hz_bot_right[0] - hz_top_left[0])
        hz_h = abs(hz_bot_right[1] - hz_top_left[1])
        svg_parts.append(
            f'<rect x="{hz_top_left[0]}" y="{hz_top_left[1]}" width="{hz_w}" height="{hz_h}" '
            f'fill="none" stroke="#94a3b8" stroke-width="1.0" stroke-dasharray="3,3" />'
        )

        # Home Plate outline at bottom
        hp_left = self._coord_to_svg(-0.708, 0.6)
        hp_right = self._coord_to_svg(0.708, 0.6)
        hp_mid = self._coord_to_svg(0.0, 0.4)
        svg_parts.append(
            f'<polygon points="{hp_left[0]},{hp_left[1]} {hp_right[0]},{hp_right[1]} '
            f'{hp_mid[0]},{hp_mid[1]}" fill="#e2e8f0" stroke="#94a3b8" stroke-width="1.5" />'
        )

        svg_parts.append(
            f'<text x="{self.width / 2}" y="{self.height - 12}" fill="#94a3b8" '
            f'font-size="10" text-anchor="middle">Strike Zone Density</text>'
        )

        svg_parts.append("</svg>")
        return GeneratedVectorChart(
            chart_type=ChartType.STRIKE_ZONE_HEATMAP,
            title=title,
            svg_content="\n".join(svg_parts),
            width_px=self.width,
            height_px=self.height,
        )


class DiamondSprayChartRenderer:
    """Renders batted ball landing points over a baseball diamond SVG layout."""

    def __init__(self, width: int = 450, height: int = 450) -> None:
        self.width = width
        self.height = height

    def _field_to_svg(self, fx: float, fy: float) -> tuple[float, float]:
        """Convert field coordinates (-250 to +250 ft x, 0 to 450 ft y) to SVG pixels."""
        # Home plate is at (width/2, height - 30)
        scale = (self.height - 60.0) / 450.0
        svg_x = (self.width / 2.0) + (fx * scale)
        svg_y = (self.height - 30.0) - (fy * scale)
        return round(svg_x, 1), round(svg_y, 1)

    def render(
        self, hits: Sequence[BattedBallTrajectoryPoint], title: str = "Diamond Spray Chart"
    ) -> GeneratedVectorChart:
        """Generate SVG markup for batted ball spray chart."""
        svg_parts = [
            (
                f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {self.width} {self.height}" '
                f'width="{self.width}" height="{self.height}" style="background-color: #0f172a;">'
            ),
            f'<text x="{self.width / 2}" y="25" fill="#f8fafc" font-size="14" font-weight="bold" '
            f'text-anchor="middle">{title}</text>',
        ]

        # Field Geometry Coordinates
        hp = self._field_to_svg(0.0, 0.0)
        lf_pole = self._field_to_svg(-233.3, 233.3)  # 330 ft down LF line (-45 deg)
        rf_pole = self._field_to_svg(233.3, 233.3)  # 330 ft down RF line (+45 deg)
        cf_wall = self._field_to_svg(0.0, 400.0)  # 400 ft dead center

        # Outfield Wall Arc
        svg_parts.append(
            f'<path d="M {lf_pole[0]} {lf_pole[1]} Q {cf_wall[0]} {cf_wall[1] - 20} '
            f'{rf_pole[0]} {rf_pole[1]}" fill="#1e293b" stroke="#475569" stroke-width="2.5" />'
        )

        # Foul Lines
        svg_parts.append(
            f'<line x1="{hp[0]}" y1="{hp[1]}" x2="{lf_pole[0]}" '
            f'y2="{lf_pole[1]}" stroke="#fff" stroke-width="1.5" />'
        )
        svg_parts.append(
            f'<line x1="{hp[0]}" y1="{hp[1]}" x2="{rf_pole[0]}" '
            f'y2="{rf_pole[1]}" stroke="#fff" stroke-width="1.5" />'
        )

        # Infield Diamond (90 ft bases)
        b1 = self._field_to_svg(63.6, 63.6)
        b2 = self._field_to_svg(0.0, 127.3)
        b3 = self._field_to_svg(-63.6, 63.6)
        svg_parts.append(
            f'<polygon points="{hp[0]},{hp[1]} {b1[0]},{b1[1]} {b2[0]},{b2[1]} {b3[0]},{b3[1]}" '
            f'fill="#334155" stroke="#64748b" stroke-width="1.2" />'
        )

        # Draw hits
        for h in hits:
            sx, sy = self._field_to_svg(h.field_x_ft, h.field_y_ft)
            # Barrels = Gold (#fbbf24), Hard Hit = Red (#ef4444), Soft = Cyan (#38bdf8)
            if h.is_barrel:
                fill_col = "#fbbf24"
                radius = 4.5
                stroke_col = "#ffffff"
            elif h.is_hard_hit:
                fill_col = "#ef4444"
                radius = 3.5
                stroke_col = "#991b1b"
            else:
                fill_col = "#38bdf8"
                radius = 2.8
                stroke_col = "#0284c7"

            svg_parts.append(
                f'<circle cx="{sx}" cy="{sy}" r="{radius}" fill="{fill_col}" '
                f'stroke="{stroke_col}" stroke-width="1.0">'
                f"<title>EV: {h.exit_velocity_mph}mph</title></circle>"
            )

        # Legend
        svg_parts.append(
            f'<circle cx="45" cy="{self.height - 12}" r="4" fill="#fbbf24" />'
            f'<text x="55" y="{self.height - 9}" fill="#94a3b8" font-size="10">Barrel</text>'
            f'<circle cx="120" cy="{self.height - 12}" r="3.5" fill="#ef4444" />'
            f'<text x="130" y="{self.height - 9}" fill="#94a3b8" font-size="10">Hard Hit</text>'
            f'<circle cx="230" cy="{self.height - 12}" r="3" fill="#38bdf8" />'
            f'<text x="240" y="{self.height - 9}" fill="#94a3b8" font-size="10">Soft/Med</text>'
        )

        svg_parts.append("</svg>")
        return GeneratedVectorChart(
            chart_type=ChartType.DIAMOND_SPRAY_CHART,
            title=title,
            svg_content="\n".join(svg_parts),
            width_px=self.width,
            height_px=self.height,
        )


class WinExpectancyGraphRenderer:
    """Renders a play-by-play Win Expectancy line graph (0% to 100%) with baseline."""

    def __init__(self, width: int = 600, height: int = 250) -> None:
        self.width = width
        self.height = height

    def render(
        self,
        we_points: Sequence[
            tuple[int, float, float]
        ],  # (play_index, home_win_expectancy, leverage_index)
        home_team: str = "Home",
        away_team: str = "Away",
        title: str = "In-Game Win Expectancy Graph",
    ) -> GeneratedVectorChart:
        """Render play-by-play Win Expectancy line graph in SVG format."""
        svg_parts = [
            (
                f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {self.width} {self.height}" '
                f'width="{self.width}" height="{self.height}" style="background-color: #0f172a;">'
            ),
            f'<text x="{self.width / 2}" y="22" fill="#f8fafc" font-size="13" font-weight="bold" '
            f'text-anchor="middle">{title} ({away_team} @ {home_team})</text>',
        ]

        margin_left = 45.0
        margin_right = 20.0
        margin_top = 40.0
        margin_bottom = 30.0

        plot_w = self.width - margin_left - margin_right
        plot_h = self.height - margin_top - margin_bottom

        # 50% baseline (neutral)
        mid_y = margin_top + (plot_h / 2.0)
        svg_parts.append(
            f'<line x1="{margin_left}" y1="{mid_y}" x2="{self.width - margin_right}" y2="{mid_y}" '
            f'stroke="#475569" stroke-width="1.5" stroke-dasharray="4,4" />'
        )
        svg_parts.append(
            f'<text x="{margin_left - 8}" y="{mid_y + 4}" fill="#94a3b8" '
            f'font-size="10" text-anchor="end">50%</text>'
        )

        n = len(we_points)
        if n >= 2:
            coords: list[tuple[float, float]] = []
            for i, (_, we_home, _) in enumerate(we_points):
                cx = margin_left + (i / (n - 1)) * plot_w
                cy = margin_top + (1.0 - we_home) * plot_h
                coords.append((cx, cy))

            # Build SVG path
            path_str = f"M {coords[0][0]:.1f} {coords[0][1]:.1f}"
            for pt in coords[1:]:
                path_str += f" L {pt[0]:.1f} {pt[1]:.1f}"

            svg_parts.append(
                f'<path d="{path_str}" fill="none" stroke="#38bdf8" stroke-width="2.5" />'
            )

        svg_parts.append("</svg>")
        return GeneratedVectorChart(
            chart_type=ChartType.WIN_EXPECTANCY_WORM,
            title=title,
            svg_content="\n".join(svg_parts),
            width_px=self.width,
            height_px=self.height,
        )


@dataclasses.dataclass(frozen=True)
class RadarDimension:
    """Individual axis attribute label and value (0 to 100)."""

    name: str
    value: float  # 0.0 to 100.0


@dataclasses.dataclass(frozen=True)
class PlayerRadarProfile:
    """Multi-axis skill profile for spider radar rendering."""

    title: str
    dimensions: list[RadarDimension]
    fill_color: str = "#00d2be"


class RadarChartRenderer:
    """Renders pure-Python vector SVG multi-axis Spider/Radar charts (RADAR-01)."""

    def __init__(self, width: int = 500, height: int = 500) -> None:
        self.width = width
        self.height = height

    def render(self, profile: PlayerRadarProfile) -> GeneratedVectorChart:
        """Render radar profile into standard SVG visual chart."""
        import math

        cx = self.width / 2.0
        cy = self.height / 2.0
        r_max = 170.0

        n = len(profile.dimensions)
        if n < 3:
            raise ValueError("Radar chart requires at least 3 dimensions")

        svg_parts: list[str] = [
            f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {self.width} {self.height}" '
            f'width="{self.width}" height="{self.height}" '
            f'style="background-color: #0b1329; border-radius: 8px;">',
            f'<text x="{cx}" y="35" fill="#f8fafc" font-size="16" font-weight="bold" '
            f'text-anchor="middle" font-family="sans-serif">{profile.title}</text>',
        ]

        # Concentric grid rings
        for ring in (0.20, 0.40, 0.60, 0.80, 1.00):
            r_ring = r_max * ring
            ring_points: list[str] = []
            for i in range(n):
                angle = -math.pi / 2.0 + (2.0 * math.pi * i / n)
                px = cx + r_ring * math.cos(angle)
                py = cy + r_ring * math.sin(angle)
                ring_points.append(f"{px:.1f},{py:.1f}")
            pts_str = " ".join(ring_points)
            svg_parts.append(
                f'<polygon points="{pts_str}" fill="none" stroke="#1e293b" stroke-width="1.5" />'
            )

        # Axis Spokes and Labels
        poly_points: list[str] = []
        for i, dim in enumerate(profile.dimensions):
            angle = -math.pi / 2.0 + (2.0 * math.pi * i / n)
            spoke_x = cx + r_max * math.cos(angle)
            spoke_y = cy + r_max * math.sin(angle)

            svg_parts.append(
                f'<line x1="{cx}" y1="{cy}" x2="{spoke_x:.1f}" '
                f'y2="{spoke_y:.1f}" stroke="#334155" stroke-width="1.2" />'
            )

            label_x = cx + (r_max + 24.0) * math.cos(angle)
            label_y = cy + (r_max + 24.0) * math.sin(angle) + 4.0
            svg_parts.append(
                f'<text x="{label_x:.1f}" y="{label_y:.1f}" fill="#94a3b8" font-size="12" '
                f'text-anchor="middle" font-family="sans-serif">{dim.name} ({dim.value:.0f})</text>'
            )

            val_norm = max(0.0, min(100.0, dim.value)) / 100.0
            vx = cx + (r_max * val_norm) * math.cos(angle)
            vy = cy + (r_max * val_norm) * math.sin(angle)
            poly_points.append(f"{vx:.1f},{vy:.1f}")

        # Shaded Data Polygon
        data_pts_str = " ".join(poly_points)
        svg_parts.append(
            f'<polygon points="{data_pts_str}" fill="{profile.fill_color}" fill-opacity="0.35" '
            f'stroke="{profile.fill_color}" stroke-width="2.5" />'
        )

        svg_parts.append("</svg>")
        return GeneratedVectorChart(
            chart_type=ChartType.SPIDER_RADAR_CHART,
            title=profile.title,
            svg_content="\n".join(svg_parts),
            width_px=self.width,
            height_px=self.height,
        )


@dataclasses.dataclass(frozen=True)
class OddsMovementPoint:
    """Snapshot of market odds at a specific point in time before game start."""

    timestamp_label: str  # e.g. "09:00", "12:00", "15:30", "18:45"
    home_decimal_odds: float  # e.g. 1.85
    away_decimal_odds: float  # e.g. 2.05
    total_line: float = 8.5
    is_steam_move: bool = False


@dataclasses.dataclass(frozen=True)
class MarketOddsTimeline:
    """Complete pre-game line movement sequence across betting books."""

    title: str
    home_team: str
    away_team: str
    points: list[OddsMovementPoint]


class OddsMovementChartRenderer:
    """Renders pure-Python vector SVG market line movement and steam move charts (ODDS-CHART-01)."""

    def __init__(self, width: int = 600, height: int = 350) -> None:
        self.width = width
        self.height = height

    def render(self, timeline: MarketOddsTimeline) -> GeneratedVectorChart:
        """Render odds movement timeline into SVG chart."""
        if not timeline.points:
            raise ValueError("Timeline must contain at least one point")

        margin_left = 60.0
        margin_right = 40.0
        margin_top = 50.0
        margin_bottom = 50.0

        plot_w = self.width - margin_left - margin_right
        plot_h = self.height - margin_top - margin_bottom

        # Determine y scale (odds range 1.40 to 2.60 or dynamic)
        all_odds = [p.home_decimal_odds for p in timeline.points] + [
            p.away_decimal_odds for p in timeline.points
        ]
        min_y = max(1.10, min(all_odds) - 0.10)
        max_y = max(all_odds) + 0.10

        svg_parts: list[str] = [
            f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {self.width} {self.height}" '
            f'width="{self.width}" height="{self.height}" '
            f'style="background-color: #0b1329; border-radius: 8px;">',
            f'<text x="{self.width / 2}" y="30" fill="#f8fafc" font-size="15" font-weight="bold" '
            f'text-anchor="middle" font-family="sans-serif">{timeline.title}</text>',
        ]

        # Horizontal gridlines
        y_ticks = 5
        for i in range(y_ticks):
            val = min_y + (max_y - min_y) * (i / (y_ticks - 1))
            norm = (val - min_y) / (max_y - min_y)
            y_px = (margin_top + plot_h) - (norm * plot_h)

            svg_parts.append(
                f'<line x1="{margin_left}" y1="{y_px:.1f}" x2="{self.width - margin_right}" '
                f'y2="{y_px:.1f}" stroke="#1e293b" stroke-width="1.0" />'
            )
            svg_parts.append(
                f'<text x="{margin_left - 10}" y="{y_px + 4:.1f}" fill="#64748b" font-size="11" '
                f'text-anchor="end" font-family="monospace">{val:.2f}</text>'
            )

        n_pts = len(timeline.points)
        home_poly: list[str] = []
        away_poly: list[str] = []

        for idx, pt in enumerate(timeline.points):
            x_norm = idx / max(1, n_pts - 1) if n_pts > 1 else 0.5
            x_px = margin_left + x_norm * plot_w

            # Home point
            h_norm = (pt.home_decimal_odds - min_y) / (max_y - min_y)
            h_y = (margin_top + plot_h) - (h_norm * plot_h)
            home_poly.append(f"{x_px:.1f},{h_y:.1f}")

            # Away point
            a_norm = (pt.away_decimal_odds - min_y) / (max_y - min_y)
            a_y = (margin_top + plot_h) - (a_norm * plot_h)
            away_poly.append(f"{x_px:.1f},{a_y:.1f}")

            # X-axis timestamp
            svg_parts.append(
                f'<text x="{x_px:.1f}" y="{self.height - 20}" fill="#94a3b8" font-size="11" '
                f'text-anchor="middle" font-family="sans-serif">{pt.timestamp_label}</text>'
            )

            # Steam move indicator
            if pt.is_steam_move:
                svg_parts.append(
                    f'<circle cx="{x_px:.1f}" cy="{h_y:.1f}" r="6" fill="#f59e0b" '
                    f'stroke="#ffffff" stroke-width="1.5" />'
                )

        # Polylines for Home (Cyan) and Away (Purple)
        svg_parts.append(
            f'<polyline points="{" ".join(home_poly)}" fill="none" stroke="#00d2be" '
            f'stroke-width="2.5" stroke-linejoin="round" />'
        )
        svg_parts.append(
            f'<polyline points="{" ".join(away_poly)}" fill="none" stroke="#a855f7" '
            f'stroke-width="2.5" stroke-linejoin="round" />'
        )

        # Legend
        svg_parts.append(
            f'<text x="{margin_left + 10}" y="{margin_top + 15}" fill="#00d2be" font-size="12" '
            f'font-weight="bold" font-family="sans-serif">{timeline.home_team} (Home)</text>'
        )
        svg_parts.append(
            f'<text x="{margin_left + 130}" y="{margin_top + 15}" fill="#a855f7" font-size="12" '
            f'font-weight="bold" font-family="sans-serif">{timeline.away_team} (Away)</text>'
        )

        svg_parts.append("</svg>")
        return GeneratedVectorChart(
            chart_type=ChartType.ODDS_MOVEMENT_TIMELINE,
            title=timeline.title,
            svg_content="\n".join(svg_parts),
            width_px=self.width,
            height_px=self.height,
        )


@dataclasses.dataclass(frozen=True)
class PitchBreakObservation:
    """Individual pitch flight movement measurement (IVB and HB in inches)."""

    pitch_type: str  # "FF", "SL", "CH", "CU", "SI", "ST"
    velo_mph: float
    pfx_x_in: float  # Horizontal break in inches (-25 to +25)
    pfx_z_in: float  # Induced vertical break in inches (-20 to +25)
    color_hex: str = "#00d2be"


@dataclasses.dataclass(frozen=True)
class PitcherArsenalBreakProfile:
    """Complete pitch arsenal movement cluster for a pitcher."""

    pitcher_name: str
    pitches: list[PitchBreakObservation]


class PitchBreakChartRenderer:
    """Renders pure-Python vector SVG 2D pitch movement and break charts (BREAK-PLOT-01)."""

    def __init__(self, width: int = 500, height: int = 500) -> None:
        self.width = width
        self.height = height

    def render(self, profile: PitcherArsenalBreakProfile) -> GeneratedVectorChart:
        """Render pitch movement Cartesian plane into SVG."""
        margin = 50.0
        plot_w = self.width - 2 * margin
        plot_h = self.height - 2 * margin

        # HB range: [-25.0, 25.0], IVB range: [-20.0, 25.0]
        min_x, max_x = -25.0, 25.0
        min_z, max_z = -20.0, 25.0

        def to_svg(hb: float, ivb: float) -> tuple[float, float]:
            norm_x = (hb - min_x) / (max_x - min_x)
            norm_z = (ivb - min_z) / (max_z - min_z)
            sx = margin + norm_x * plot_w
            sz = (margin + plot_h) - (norm_z * plot_h)
            return round(sx, 1), round(sz, 1)

        cx, cz = to_svg(0.0, 0.0)

        svg_parts: list[str] = [
            f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {self.width} {self.height}" '
            f'width="{self.width}" height="{self.height}" '
            f'style="background-color: #0b1329; border-radius: 8px;">',
            f'<text x="{self.width / 2}" y="30" fill="#f8fafc" font-size="15" font-weight="bold" '
            f'text-anchor="middle" font-family="sans-serif">'
            f"{profile.pitcher_name} Arsenal Movement</text>",
            # Cartesian Axes (0,0)
            f'<line x1="{margin}" y1="{cz}" x2="{self.width - margin}" '
            f'y2="{cz}" stroke="#334155" stroke-width="1.5" />',
            f'<line x1="{cx}" y1="{margin}" x2="{cx}" '
            f'y2="{self.height - margin}" stroke="#334155" stroke-width="1.5" />',
            # Axis Labels
            f'<text x="{self.width - margin}" y="{cz - 8}" fill="#64748b" font-size="11" '
            f'text-anchor="end" font-family="sans-serif">Arm Side HB (in)</text>',
            f'<text x="{margin}" y="{cz - 8}" fill="#64748b" font-size="11" '
            f'text-anchor="start" font-family="sans-serif">Glove Side HB</text>',
            f'<text x="{cx + 8}" y="{margin + 12}" fill="#64748b" font-size="11" '
            f'font-family="sans-serif">+IVB (Rise)</text>',
            f'<text x="{cx + 8}" y="{self.height - margin - 8}" fill="#64748b" font-size="11" '
            f'font-family="sans-serif">-IVB (Drop)</text>',
        ]

        # Pitch Dots
        for p in profile.pitches:
            px, pz = to_svg(p.pfx_x_in, p.pfx_z_in)
            svg_parts.append(
                f'<circle cx="{px}" cy="{pz}" r="6" fill="{p.color_hex}" fill-opacity="0.85" '
                f'stroke="#ffffff" stroke-width="1.0" />'
            )
            svg_parts.append(
                f'<text x="{px}" y="{pz - 9}" fill="#f8fafc" font-size="10" font-weight="bold" '
                f'text-anchor="middle" font-family="sans-serif">'
                f"{p.pitch_type} ({p.velo_mph:.0f})</text>"
            )

        svg_parts.append("</svg>")
        return GeneratedVectorChart(
            chart_type=ChartType.PITCH_BREAK_CHART,
            title=f"{profile.pitcher_name} Arsenal Movement",
            svg_content="\n".join(svg_parts),
            width_px=self.width,
            height_px=self.height,
        )


@dataclasses.dataclass(frozen=True)
class InningScoreStep:
    """Run scoring progression for a single inning."""

    inning: int
    away_runs_scored: int
    home_runs_scored: int
    away_cumulative: int
    home_cumulative: int


@dataclasses.dataclass(frozen=True)
class GameScoreFlowProfile:
    """Cumulative inning-by-inning score flow for a baseball game."""

    title: str
    home_team: str
    away_team: str
    innings: list[InningScoreStep]


class InningScoreFlowRenderer:
    """Renders pure-Python vector SVG stepped game score flow and lead changes (FLOW-01)."""

    def __init__(self, width: int = 600, height: int = 350) -> None:
        self.width = width
        self.height = height

    def render(self, profile: GameScoreFlowProfile) -> GeneratedVectorChart:
        """Render inning score flow into stepped SVG line chart."""
        if not profile.innings:
            raise ValueError("Innings profile cannot be empty")

        margin_left = 60.0
        margin_right = 40.0
        margin_top = 50.0
        margin_bottom = 50.0

        plot_w = self.width - margin_left - margin_right
        plot_h = self.height - margin_top - margin_bottom

        max_runs = max(
            [step.home_cumulative for step in profile.innings]
            + [step.away_cumulative for step in profile.innings]
            + [5]
        )

        n_inn = len(profile.innings)

        svg_parts: list[str] = [
            f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {self.width} {self.height}" '
            f'width="{self.width}" height="{self.height}" '
            f'style="background-color: #0b1329; border-radius: 8px;">',
            f'<text x="{self.width / 2}" y="30" fill="#f8fafc" font-size="15" font-weight="bold" '
            f'text-anchor="middle" font-family="sans-serif">{profile.title}</text>',
        ]

        # Horizontal Run Gridlines
        for r in range(max_runs + 1):
            norm_y = r / max_runs
            y_px = (margin_top + plot_h) - (norm_y * plot_h)
            svg_parts.append(
                f'<line x1="{margin_left}" y1="{y_px:.1f}" x2="{self.width - margin_right}" '
                f'y2="{y_px:.1f}" stroke="#1e293b" stroke-width="1.0" />'
            )
            svg_parts.append(
                f'<text x="{margin_left - 10}" y="{y_px + 4:.1f}" fill="#64748b" font-size="11" '
                f'text-anchor="end" font-family="monospace">{r}</text>'
            )

        home_pts: list[str] = [f"{margin_left:.1f},{(margin_top + plot_h):.1f}"]
        away_pts: list[str] = [f"{margin_left:.1f},{(margin_top + plot_h):.1f}"]

        for idx, step in enumerate(profile.innings):
            x_left = margin_left + (idx / n_inn) * plot_w
            x_right = margin_left + ((idx + 1) / n_inn) * plot_w

            h_y = (margin_top + plot_h) - (step.home_cumulative / max_runs * plot_h)
            a_y = (margin_top + plot_h) - (step.away_cumulative / max_runs * plot_h)

            home_pts.extend([f"{x_left:.1f},{h_y:.1f}", f"{x_right:.1f},{h_y:.1f}"])
            away_pts.extend([f"{x_left:.1f},{a_y:.1f}", f"{x_right:.1f},{a_y:.1f}"])

            # Inning X labels
            x_mid = (x_left + x_right) / 2.0
            svg_parts.append(
                f'<text x="{x_mid:.1f}" y="{self.height - 20}" fill="#94a3b8" font-size="11" '
                f'text-anchor="middle" font-family="sans-serif">Inn {step.inning}</text>'
            )

        # Polylines for Home (Cyan) and Away (Purple)
        svg_parts.append(
            f'<polyline points="{" ".join(home_pts)}" fill="none" stroke="#00d2be" '
            f'stroke-width="2.5" />'
        )
        svg_parts.append(
            f'<polyline points="{" ".join(away_pts)}" fill="none" stroke="#a855f7" '
            f'stroke-width="2.5" />'
        )

        # Legend
        svg_parts.append(
            f'<text x="{margin_left + 10}" y="{margin_top + 15}" fill="#00d2be" font-size="12" '
            f'font-weight="bold" font-family="sans-serif">{profile.home_team} (Home)</text>'
        )
        svg_parts.append(
            f'<text x="{margin_left + 130}" y="{margin_top + 15}" fill="#a855f7" font-size="12" '
            f'font-weight="bold" font-family="sans-serif">{profile.away_team} (Away)</text>'
        )

        svg_parts.append("</svg>")
        return GeneratedVectorChart(
            chart_type=ChartType.INNING_SCORE_FLOW,
            title=profile.title,
            svg_content="\n".join(svg_parts),
            width_px=self.width,
            height_px=self.height,
        )


@dataclasses.dataclass(frozen=True)
class BaseOutRunExpectancyGrid:
    """Standard 24-state empirical run expectancy matrix across base/out configurations."""

    title: str = "MLB 24-State Run Expectancy Matrix (RE24)"
    era_label: str = "Modern MLB Run Environment"
    matrix: dict[str, list[float]] = dataclasses.field(
        default_factory=lambda: {
            "Empty": [0.48, 0.26, 0.10],
            "1st": [0.86, 0.51, 0.22],
            "2nd": [1.10, 0.67, 0.32],
            "3rd": [1.35, 0.95, 0.36],
            "1st & 2nd": [1.44, 0.90, 0.43],
            "1st & 3rd": [1.79, 1.14, 0.48],
            "2nd & 3rd": [1.96, 1.38, 0.58],
            "Bases Loaded": [2.29, 1.54, 0.75],
        }
    )


class RunExpectancyHeatmapRenderer:
    """Renders SVG 24-state base/out run expectancy matrix heatmaps (RE24-MAP-01)."""

    def __init__(self, width: int = 560, height: int = 480) -> None:
        self.width = width
        self.height = height

    def render(self, grid: BaseOutRunExpectancyGrid) -> GeneratedVectorChart:
        """Render 8x3 base/out matrix heatmap into SVG."""
        margin_left = 110.0
        margin_right = 30.0
        margin_top = 60.0
        margin_bottom = 40.0

        plot_w = self.width - margin_left - margin_right
        plot_h = self.height - margin_top - margin_bottom

        base_states = list(grid.matrix.keys())
        n_rows = len(base_states)
        n_cols = 3  # 0, 1, 2 Outs

        cell_w = plot_w / n_cols
        cell_h = plot_h / n_rows

        svg_parts: list[str] = [
            f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {self.width} {self.height}" '
            f'width="{self.width}" height="{self.height}" '
            f'style="background-color: #0b1329; border-radius: 8px;">',
            f'<text x="{self.width / 2}" y="32" fill="#f8fafc" font-size="15" font-weight="bold" '
            f'text-anchor="middle" font-family="sans-serif">{grid.title}</text>',
        ]

        # X-Axis Out Column Headers
        out_labels = ["0 Outs", "1 Out", "2 Outs"]
        for c_idx, label in enumerate(out_labels):
            cx = margin_left + (c_idx + 0.5) * cell_w
            svg_parts.append(
                f'<text x="{cx:.1f}" y="{margin_top - 12}" fill="#94a3b8" font-size="12" '
                f'font-weight="bold" text-anchor="middle" font-family="sans-serif">{label}</text>'
            )

        # Draw Cells
        for r_idx, state in enumerate(base_states):
            ry = margin_top + r_idx * cell_h
            # Y-Axis Row Label
            svg_parts.append(
                f'<text x="{margin_left - 12}" y="{ry + cell_h * 0.65:.1f}" fill="#cbd5e1" '
                f'font-size="11" font-weight="bold" text-anchor="end" '
                f'font-family="sans-serif">{state}</text>'
            )

            values = grid.matrix[state]
            for c_idx in range(n_cols):
                val = values[c_idx] if c_idx < len(values) else 0.0
                rx = margin_left + c_idx * cell_w

                # Intensity color mapping (0.10 to 2.30)
                norm_v = min(1.0, max(0.0, (val - 0.10) / 2.20))
                # Interpolate from Navy #1e293b to Cyan #00d2be to Gold #eab308
                if norm_v < 0.5:
                    t = norm_v / 0.5
                    r_val = int(30 + t * (0 - 30))
                    g_val = int(41 + t * (210 - 41))
                    b_val = int(59 + t * (190 - 59))
                else:
                    t = (norm_v - 0.5) / 0.5
                    r_val = int(0 + t * (234 - 0))
                    g_val = int(210 + t * (179 - 210))
                    b_val = int(190 + t * (8 - 190))

                fill_hex = f"#{r_val:02x}{g_val:02x}{b_val:02x}"

                svg_parts.append(
                    f'<rect x="{rx + 2:.1f}" y="{ry + 2:.1f}" width="{cell_w - 4:.1f}" '
                    f'height="{cell_h - 4:.1f}" rx="4" fill="{fill_hex}" fill-opacity="0.85" '
                    f'stroke="#334155" stroke-width="1.0" />'
                )
                svg_parts.append(
                    f'<text x="{rx + cell_w / 2:.1f}" y="{ry + cell_h * 0.62:.1f}" fill="#ffffff" '
                    f'font-size="12" font-weight="bold" '
                    f'text-anchor="middle" font-family="monospace">{val:.2f}</text>'
                )

        svg_parts.append("</svg>")
        return GeneratedVectorChart(
            chart_type=ChartType.RUN_EXPECTANCY_HEATMAP,
            title=grid.title,
            svg_content="\n".join(svg_parts),
            width_px=self.width,
            height_px=self.height,
        )


@dataclasses.dataclass(frozen=True)
class HexbinPitchObservation:
    """Individual 2D pitch coordinate in feet relative to plate center."""

    px: float  # Horizontal position in feet (-1.5 to +1.5)
    pz: float  # Vertical position in feet (1.0 to 4.5)
    pitch_type: str = "FF"
    is_strike: bool = True


@dataclasses.dataclass(frozen=True)
class SpatialHexbinProfile:
    """Pitch location collection for 2D hexagonal spatial binning."""

    title: str
    batter_name: str
    pitcher_name: str
    pitches: list[HexbinPitchObservation]


class SpatialHexbinVisualizerRenderer:
    """Renders pure-Python vector SVG 2D spatial hexbin strike zone heatmaps (HEXBIN-01)."""

    def __init__(self, width: int = 500, height: int = 500) -> None:
        self.width = width
        self.height = height

    def render(self, profile: SpatialHexbinProfile) -> GeneratedVectorChart:
        """Render 2D hexagonal binning strike zone into SVG."""
        margin_x = 50.0
        margin_y = 50.0
        plot_w = self.width - 2 * margin_x
        plot_h = self.height - 2 * margin_y

        min_x, max_x = -1.8, 1.8
        min_z, max_z = 0.8, 4.5

        def to_svg(x: float, z: float) -> tuple[float, float]:
            nx = (x - min_x) / (max_x - min_x)
            nz = (z - min_z) / (max_z - min_z)
            sx = margin_x + nx * plot_w
            sz = (margin_y + plot_h) - (nz * plot_h)
            return round(sx, 1), round(sz, 1)

        # Strike zone rulebook bounding box [-0.83, 0.83] ft, [1.5, 3.5] ft
        sz_left, sz_top = to_svg(-0.83, 3.5)
        sz_right, sz_bot = to_svg(0.83, 1.5)

        svg_parts: list[str] = [
            f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {self.width} {self.height}" '
            f'width="{self.width}" height="{self.height}" '
            f'style="background-color: #0b1329; border-radius: 8px;">',
            f'<text x="{self.width / 2}" y="30" fill="#f8fafc" font-size="14" font-weight="bold" '
            f'text-anchor="middle" font-family="sans-serif">{profile.title}</text>',
            # Strike Zone Bounding Box
            f'<rect x="{sz_left}" y="{sz_top}" width="{sz_right - sz_left:.1f}" '
            f'height="{sz_bot - sz_top:.1f}" fill="none" stroke="#f8fafc" stroke-width="2.0" '
            f'stroke-dasharray="4,4" />',
        ]

        # Render individual hexagon / circle pitch cluster markers
        for p in profile.pitches:
            sx, sz = to_svg(p.px, p.pz)
            color = "#00d2be" if p.is_strike else "#f59e0b"
            svg_parts.append(
                f'<circle cx="{sx}" cy="{sz}" r="7" fill="{color}" fill-opacity="0.80" '
                f'stroke="#ffffff" stroke-width="1.0" />'
            )

        # Home plate pentagon indicator at bottom
        hp_cx, hp_y = self.width / 2.0, self.height - 35.0
        hp_pts = (
            f"{hp_cx - 20:.1f},{hp_y:.1f} {hp_cx + 20:.1f},{hp_y:.1f} "
            f"{hp_cx + 20:.1f},{hp_y + 12:.1f} {hp_cx:.1f},{hp_y + 22:.1f} "
            f"{hp_cx - 20:.1f},{hp_y + 12:.1f}"
        )
        svg_parts.append(
            f'<polygon points="{hp_pts}" fill="#475569" stroke="#94a3b8" stroke-width="1.5" />'
        )

        svg_parts.append("</svg>")
        return GeneratedVectorChart(
            chart_type=ChartType.SPATIAL_HEXBIN_MAP,
            title=profile.title,
            svg_content="\n".join(svg_parts),
            width_px=self.width,
            height_px=self.height,
        )


@dataclasses.dataclass(frozen=True)
class MatchupMetricComparison:
    """Individual rate metric comparison between batter and pitcher."""

    label: str
    batter_val: float  # Normalized 0.0 to 1.0 for bar length
    pitcher_val: float  # Normalized 0.0 to 1.0 for bar length
    batter_text: str
    pitcher_text: str
    higher_is_better_for_batter: bool = True


@dataclasses.dataclass(frozen=True)
class MatchupCardProfile:
    """Side-by-side player scouting head-to-head card profile."""

    title: str
    batter_name: str
    pitcher_name: str
    overall_edge: str  # "BATTER_ADVANTAGE", "PITCHER_ADVANTAGE", "NEUTRAL"
    metrics: list[MatchupMetricComparison]


class MatchupComparisonCardRenderer:
    """Renders pure-Python vector SVG head-to-head matchup scouting cards (COMPARE-CARD-01)."""

    def __init__(self, width: int = 580, height: int = 380) -> None:
        self.width = width
        self.height = height

    def render(self, profile: MatchupCardProfile) -> GeneratedVectorChart:
        """Render side-by-side dual-bar matchup card into SVG."""
        svg_parts: list[str] = [
            f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {self.width} {self.height}" '
            f'width="{self.width}" height="{self.height}" '
            f'style="background-color: #0b1329; border-radius: 8px;">',
            f'<text x="{self.width / 2}" y="32" fill="#f8fafc" font-size="15" font-weight="bold" '
            f'text-anchor="middle" font-family="sans-serif">{profile.title}</text>',
            # Batter / Pitcher Column Headers
            f'<text x="80" y="65" fill="#00d2be" font-size="13" font-weight="bold" '
            f'font-family="sans-serif">{profile.batter_name} (Hitter)</text>',
            f'<text x="{self.width - 80}" y="65" fill="#f59e0b" font-size="13" font-weight="bold" '
            f'text-anchor="end" font-family="sans-serif">{profile.pitcher_name} (Pitcher)</text>',
        ]

        mid_x = self.width / 2.0
        bar_max_w = 160.0
        start_y = 100.0
        row_h = 48.0

        for i, m in enumerate(profile.metrics):
            curr_y = start_y + i * row_h
            b_w = max(4.0, m.batter_val * bar_max_w)
            p_w = max(4.0, m.pitcher_val * bar_max_w)

            # Metric central label
            svg_parts.append(
                f'<text x="{mid_x}" y="{curr_y + 12}" fill="#cbd5e1" font-size="11" '
                f'font-weight="bold" text-anchor="middle" font-family="sans-serif">{m.label}</text>'
            )

            # Batter Bar (growing left from mid_x - 60)
            b_x = (mid_x - 55.0) - b_w
            svg_parts.append(
                f'<rect x="{b_x:.1f}" y="{curr_y}" width="{b_w:.1f}" height="16" '
                f'fill="#00d2be" rx="3" />'
            )
            svg_parts.append(
                f'<text x="{b_x - 10:.1f}" y="{curr_y + 13}" fill="#f8fafc" font-size="11" '
                f'text-anchor="end" font-family="sans-serif">{m.batter_text}</text>'
            )

            # Pitcher Bar (growing right from mid_x + 55)
            p_x = mid_x + 55.0
            svg_parts.append(
                f'<rect x="{p_x:.1f}" y="{curr_y}" width="{p_w:.1f}" height="16" '
                f'fill="#f59e0b" rx="3" />'
            )
            svg_parts.append(
                f'<text x="{p_x + p_w + 10:.1f}" y="{curr_y + 13}" fill="#f8fafc" font-size="11" '
                f'text-anchor="start" font-family="sans-serif">{m.pitcher_text}</text>'
            )

        # Overall Edge Badge
        badge_y = self.height - 30.0
        edge_col = "#00d2be" if "BATTER" in profile.overall_edge else "#f59e0b"
        svg_parts.append(
            f'<rect x="{mid_x - 90}" y="{badge_y - 18}" width="180" height="26" rx="4" '
            f'fill="#1e293b" stroke="{edge_col}" stroke-width="1.5" />'
        )
        svg_parts.append(
            f'<text x="{mid_x}" y="{badge_y}" fill="{edge_col}" font-size="11" '
            f'font-weight="bold" text-anchor="middle" font-family="sans-serif">'
            f"{profile.overall_edge.replace('_', ' ')}</text>"
        )

        svg_parts.append("</svg>")
        return GeneratedVectorChart(
            chart_type=ChartType.MATCHUP_COMPARISON_CARD,
            title=profile.title,
            svg_content="\n".join(svg_parts),
            width_px=self.width,
            height_px=self.height,
        )


@dataclasses.dataclass(frozen=True)
class WinProbabilityReplayStep:
    """Individual game event step recording win expectancy and narrative context."""

    step_index: int
    inning: int
    is_top_inning: bool
    home_we: float  # 0.0 to 1.0
    play_description: str
    we_delta: float = 0.0  # Change in win expectancy from prior step
    is_pivotal_swing: bool = False  # Set true if |we_delta| >= 0.15


@dataclasses.dataclass(frozen=True)
class GameWPAReplayProfile:
    """Complete game event progression for SVG win probability replay rendering."""

    title: str
    home_team: str
    away_team: str
    final_score_text: str
    steps: list[WinProbabilityReplayStep]


class WinProbabilityReplayRenderer:
    """Renders pure-Python vector SVG game win probability replay flow charts (WPA-REPLAY-01)."""

    def __init__(self, width: int = 680, height: int = 340) -> None:
        self.width = width
        self.height = height

    def render(self, profile: GameWPAReplayProfile) -> GeneratedVectorChart:
        """Render multi-step win probability replay into vector SVG."""
        margin_x = 60.0
        margin_y = 55.0
        plot_w = self.width - 2 * margin_x
        plot_h = self.height - 2 * margin_y

        n_steps = max(1, len(profile.steps) - 1)

        def to_svg(step_idx: int, we: float) -> tuple[float, float]:
            sx = margin_x + (step_idx / n_steps) * plot_w
            sy = (margin_y + plot_h) - (we * plot_h)
            return round(sx, 1), round(sy, 1)

        svg_parts: list[str] = [
            f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {self.width} {self.height}" '
            f'width="{self.width}" height="{self.height}" '
            f'style="background-color: #0b1329; border-radius: 8px;">',
            f'<text x="{self.width / 2}" y="28" fill="#f8fafc" font-size="14" font-weight="bold" '
            f'text-anchor="middle" font-family="sans-serif">{profile.title}</text>',
            f'<text x="{self.width / 2}" y="45" fill="#94a3b8" font-size="11" text-anchor="middle" '
            f'font-family="sans-serif">{profile.home_team} vs {profile.away_team} '
            f"({profile.final_score_text})</text>",
            # 50% Win Expectancy Center Guideline
            f'<line x1="{margin_x}" y1="{margin_y + plot_h / 2:.1f}" x2="{margin_x + plot_w}" '
            f'y2="{margin_y + plot_h / 2:.1f}" stroke="#334155" stroke-width="1.5" '
            f'stroke-dasharray="4,4" />',
            # 100% Home & 100% Away Bounds
            f'<text x="{margin_x - 10}" y="{margin_y + 4}" fill="#00d2be" font-size="10" '
            f'text-anchor="end" font-family="sans-serif">100% {profile.home_team}</text>',
            f'<text x="{margin_x - 10}" y="{margin_y + plot_h / 2 + 3:.1f}" '
            f'fill="#64748b" font-size="10" '
            f'text-anchor="end" font-family="sans-serif">50%</text>',
            f'<text x="{margin_x - 10}" y="{margin_y + plot_h}" fill="#f59e0b" font-size="10" '
            f'text-anchor="end" font-family="sans-serif">100% {profile.away_team}</text>',
        ]

        # Polyline Coordinates
        pts = []
        pivotal_markers = []

        for s in profile.steps:
            sx, sy = to_svg(s.step_index, s.home_we)
            pts.append(f"{sx},{sy}")

            if s.is_pivotal_swing or abs(s.we_delta) >= 0.15:
                marker_col = "#00d2be" if s.we_delta > 0 else "#f59e0b"
                pivotal_markers.append(
                    f'<circle cx="{sx}" cy="{sy}" r="5.5" fill="{marker_col}" '
                    f'stroke="#ffffff" stroke-width="1.5" />'
                )

        if pts:
            svg_parts.append(
                f'<polyline points="{" ".join(pts)}" fill="none" stroke="#00d2be" '
                f'stroke-width="2.5" stroke-linejoin="round" />'
            )

        svg_parts.extend(pivotal_markers)
        svg_parts.append("</svg>")

        return GeneratedVectorChart(
            chart_type=ChartType.WIN_PROBABILITY_REPLAY,
            title=profile.title,
            svg_content="\n".join(svg_parts),
            width_px=self.width,
            height_px=self.height,
        )


@dataclasses.dataclass(frozen=True)
class PitchTrajectory3DSpec:
    """Aerodynamic flight parameters for a single pitch in 3D space."""

    pitch_type: str  # "FF", "SL", "CH", "CU", "SI"
    pitch_name: str
    release_x: float  # Feet (-2.5 to +2.5)
    release_z: float  # Feet (5.0 to 6.5)
    plate_x: float  # Feet (-1.2 to +1.2)
    plate_z: float  # Feet (1.2 to 3.8)
    pfx_x: float  # Horizontal movement in inches
    pfx_z: float  # Induced vertical break in inches
    color_hex: str = "#00d2be"


@dataclasses.dataclass(frozen=True)
class PitchTunnel3DProfile:
    """Multi-pitch 3D trajectory tunnel profile."""

    title: str
    pitcher_name: str
    pitches: list[PitchTrajectory3DSpec]


class PitchTrajectory3DVisualizerRenderer:
    """Renders pure-Python vector SVG 3D isometric pitch flight trajectories (FLIGHT-3D-01)."""

    def __init__(self, width: int = 650, height: int = 380) -> None:
        self.width = width
        self.height = height

    def render(self, profile: PitchTunnel3DProfile) -> GeneratedVectorChart:
        """Render 3D isometric flight trajectories into vector SVG."""
        # Mound rubber at y=54.5 ft; Home plate at y=0.0 ft
        # Isometric projection mapping:
        # Screen origin (center):
        cx = self.width / 2.0
        cy = self.height / 2.0 + 40.0

        def project(x_ft: float, y_ft: float, z_ft: float) -> tuple[float, float]:
            # y goes from 54.5 (mound, high up/back) to 0.0 (plate, low/front)
            # x goes from left (-) to right (+)
            # z goes from ground (0) up
            sx = cx + (x_ft * 26.0) + ((54.5 - y_ft) * 4.2)
            sy = cy - (z_ft * 32.0) - (y_ft * 2.8)
            return round(sx, 1), round(sy, 1)

        svg_parts: list[str] = [
            f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {self.width} {self.height}" '
            f'width="{self.width}" height="{self.height}" '
            f'style="background-color: #0b1329; border-radius: 8px;">',
            f'<text x="{self.width / 2}" y="28" fill="#f8fafc" font-size="14" font-weight="bold" '
            f'text-anchor="middle" font-family="sans-serif">{profile.title}</text>',
            f'<text x="{self.width / 2}" y="45" fill="#94a3b8" font-size="11" text-anchor="middle" '
            f'font-family="sans-serif">{profile.pitcher_name} 3D Pitch Flight & Tunneling</text>',
        ]

        # 1. Home Plate Wireframe at y=0.0
        hp_l, hp_b = project(-0.71, 0.0, 0.0)
        hp_r, _ = project(0.71, 0.0, 0.0)
        hp_c, hp_t = project(0.0, 0.0, 0.0)
        svg_parts.append(
            f'<polygon points="{hp_l:.1f},{hp_b:.1f} {hp_r:.1f},{hp_b:.1f} '
            f'{hp_c:.1f},{hp_t + 10:.1f}" fill="#334155" stroke="#64748b" stroke-width="1.5" />'
        )

        # 2. Strike Zone Wireframe at Plate (y=0.0, z in [1.5, 3.5], x in [-0.83, 0.83])
        sz_bl = project(-0.83, 0.0, 1.5)
        sz_br = project(0.83, 0.0, 1.5)
        sz_tr = project(0.83, 0.0, 3.5)
        sz_tl = project(-0.83, 0.0, 3.5)
        sz_pts = (
            f"{sz_bl[0]},{sz_bl[1]} {sz_br[0]},{sz_br[1]} "
            f"{sz_tr[0]},{sz_tr[1]} {sz_tl[0]},{sz_tl[1]}"
        )
        svg_parts.append(
            f'<polygon points="{sz_pts}" fill="#00d2be" fill-opacity="0.08" '
            f'stroke="#f8fafc" stroke-width="1.5" stroke-dasharray="3,3" />'
        )

        # 3. Mound Rubber at y=54.5
        mr_l = project(-1.0, 54.5, 0.8)
        mr_r = project(1.0, 54.5, 0.8)
        svg_parts.append(
            f'<line x1="{mr_l[0]}" y1="{mr_l[1]}" x2="{mr_r[0]}" y2="{mr_r[1]}" '
            f'stroke="#94a3b8" stroke-width="2.5" />'
        )

        # 4. Multi-Pitch Trajectory Curves (sampled across 12 flight points)
        for p in profile.pitches:
            pts = []
            for i in range(13):
                frac = i / 12.0
                curr_y = 54.5 * (1.0 - frac)
                curr_x = (
                    p.release_x
                    + (p.plate_x - p.release_x) * frac
                    + (p.pfx_x / 12.0) * (frac**2 - frac)
                )
                curr_z = (
                    p.release_z
                    + (p.plate_z - p.release_z) * frac
                    + (p.pfx_z / 12.0) * (frac**2 - frac)
                )
                sx, sy = project(curr_x, curr_y, curr_z)
                pts.append(f"{sx},{sy}")

            svg_parts.append(
                f'<polyline points="{" ".join(pts)}" fill="none" stroke="{p.color_hex}" '
                f'stroke-width="2.5" stroke-linecap="round" />'
            )

            # Start & End markers
            start_x, start_y = project(p.release_x, 54.5, p.release_z)
            end_x, end_y = project(p.plate_x, 0.0, p.plate_z)
            svg_parts.append(
                f'<circle cx="{start_x}" cy="{start_y}" r="4.0" fill="{p.color_hex}" '
                f'stroke="#ffffff" stroke-width="1.0" />'
            )
            svg_parts.append(
                f'<circle cx="{end_x}" cy="{end_y}" r="5.0" fill="{p.color_hex}" '
                f'stroke="#ffffff" stroke-width="1.5" />'
            )

        svg_parts.append("</svg>")
        return GeneratedVectorChart(
            chart_type=ChartType.PITCH_TRAJECTORY_3D,
            title=profile.title,
            svg_content="\n".join(svg_parts),
            width_px=self.width,
            height_px=self.height,
        )


@dataclasses.dataclass(frozen=True)
class ZoneGridValue:
    """Single spatial cell value in 5x5 strike zone grid."""

    row: int  # 0 to 4 (top to bottom)
    col: int  # 0 to 4 (left to right)
    val: float  # e.g. 0.0 to 1.0 (slugging or whiff rate)
    label: str = ""


@dataclasses.dataclass(frozen=True)
class ZoneSurfaceContourProfile:
    """Strike zone 5x5 iso-contour surface profile."""

    title: str
    batter_name: str
    metric_label: str
    grid_cells: list[ZoneGridValue]


class ZoneSurfaceContourRenderer:
    """Renders pure-Python vector SVG strike zone iso-contour heat surfaces (ZONE-SURFACE-01)."""

    def __init__(self, width: int = 500, height: int = 460) -> None:
        self.width = width
        self.height = height

    def render(self, profile: ZoneSurfaceContourProfile) -> GeneratedVectorChart:
        """Render 5x5 interpolated contour mesh into vector SVG."""
        margin_x = 75.0
        margin_y = 65.0
        grid_w = self.width - 2 * margin_x
        grid_h = self.height - margin_y - 75.0

        cell_w = grid_w / 5.0
        cell_h = grid_h / 5.0

        svg_parts: list[str] = [
            f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {self.width} {self.height}" '
            f'width="{self.width}" height="{self.height}" '
            f'style="background-color: #0b1329; border-radius: 8px;">',
            f'<text x="{self.width / 2}" y="28" fill="#f8fafc" font-size="14" font-weight="bold" '
            f'text-anchor="middle" font-family="sans-serif">{profile.title}</text>',
            f'<text x="{self.width / 2}" y="45" fill="#94a3b8" font-size="11" text-anchor="middle" '
            f'font-family="sans-serif">{profile.batter_name} ({profile.metric_label})</text>',
        ]

        def get_color(val: float) -> str:
            # Color map from 0.0 (Cyan #00d2be) -> 0.5 (Slate #475569) -> 1.0 (Amber/Red #ef4444)
            clamped = max(0.0, min(1.0, val))
            if clamped <= 0.5:
                # Cyan to Slate
                r = int(0 + (clamped / 0.5) * 71)
                g = int(210 - (clamped / 0.5) * 125)
                b = int(190 - (clamped / 0.5) * 85)
            else:
                # Slate to Red
                factor = (clamped - 0.5) / 0.5
                r = int(71 + factor * (239 - 71))
                g = int(85 - factor * (85 - 68))
                b = int(105 - factor * (105 - 68))
            return f"rgb({r},{g},{b})"

        # Render 5x5 mesh tiles
        for cell in profile.grid_cells:
            gx = margin_x + cell.col * cell_w
            gy = margin_y + cell.row * cell_h
            col_hex = get_color(cell.val)
            svg_parts.append(
                f'<rect x="{gx:.1f}" y="{gy:.1f}" width="{cell_w:.1f}" height="{cell_h:.1f}" '
                f'fill="{col_hex}" stroke="#1e293b" stroke-width="0.8" rx="3" />'
            )
            txt = cell.label if cell.label else f"{cell.val:.2f}"
            svg_parts.append(
                f'<text x="{gx + cell_w / 2:.1f}" y="{gy + cell_h / 2 + 4:.1f}" fill="#f8fafc" '
                f'font-size="10" font-weight="bold" text-anchor="middle" '
                f'font-family="sans-serif">{txt}</text>'
            )

        # Draw Official Strike Zone Inset Box (Inner 3x3 rows 1-3, cols 1-3)
        sz_x = margin_x + 1 * cell_w
        sz_y = margin_y + 1 * cell_h
        sz_w = 3 * cell_w
        sz_h = 3 * cell_h
        svg_parts.append(
            f'<rect x="{sz_x:.1f}" y="{sz_y:.1f}" width="{sz_w:.1f}" height="{sz_h:.1f}" '
            f'fill="none" stroke="#ffffff" stroke-width="2.2" rx="2" />'
        )

        # Home Plate polygon underneath
        hp_y = margin_y + grid_h + 15.0
        hp_cx = self.width / 2.0
        hp_hw = cell_w * 1.5
        svg_parts.append(
            f'<polygon points="{hp_cx - hp_hw:.1f},{hp_y:.1f} {hp_cx + hp_hw:.1f},{hp_y:.1f} '
            f"{hp_cx + hp_hw:.1f},{hp_y + 12:.1f} {hp_cx:.1f},{hp_y + 22:.1f} "
            f'{hp_cx - hp_hw:.1f},{hp_y + 12:.1f}" fill="#475569" stroke="#94a3b8" '
            f'stroke-width="1.5" />'
        )

        svg_parts.append("</svg>")
        return GeneratedVectorChart(
            chart_type=ChartType.ZONE_SURFACE_CONTOUR,
            title=profile.title,
            svg_content="\n".join(svg_parts),
            width_px=self.width,
            height_px=self.height,
        )


@dataclasses.dataclass(frozen=True)
class PitchSpinClockSpec:
    """Pitch spin axis tilt and efficiency parameters for clock dial representation."""

    pitch_type: str  # "FF", "SL", "CH", "SI", "CU"
    pitch_name: str
    tilt_hours: int  # 1 to 12
    tilt_minutes: int  # 0 to 59
    spin_efficiency_pct: float  # 0.0 to 100.0%
    color_hex: str = "#00d2be"


@dataclasses.dataclass(frozen=True)
class PitcherSpinClockArsenalProfile:
    """Complete arsenal spin axis profile for 12-hour clock visualizer."""

    title: str
    pitcher_name: str
    pitches: list[PitchSpinClockSpec]


class SpinAxisClockVisualizerRenderer:
    """Renders pure-Python vector SVG 12-hour pitch spin axis clock dials (SPIN-CLOCK-01)."""

    def __init__(self, width: int = 480, height: int = 480) -> None:
        self.width = width
        self.height = height

    def render(self, profile: PitcherSpinClockArsenalProfile) -> GeneratedVectorChart:
        """Render analog clock dial with pitch tilt vectors into vector SVG."""
        cx = self.width / 2.0
        cy = self.height / 2.0 + 15.0
        r_dial = 160.0

        svg_parts: list[str] = [
            f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {self.width} {self.height}" '
            f'width="{self.width}" height="{self.height}" '
            f'style="background-color: #0b1329; border-radius: 8px;">',
            f'<text x="{self.width / 2}" y="28" fill="#f8fafc" font-size="14" font-weight="bold" '
            f'text-anchor="middle" font-family="sans-serif">{profile.title}</text>',
            f'<text x="{self.width / 2}" y="45" fill="#94a3b8" font-size="11" text-anchor="middle" '
            f'font-family="sans-serif">{profile.pitcher_name} Spin Tilt Vectors</text>',
            # Clock Dial Outlines
            f'<circle cx="{cx}" cy="{cy}" r="{r_dial}" fill="#0f172a" '
            f'stroke="#334155" stroke-width="2.0" />',
            f'<circle cx="{cx}" cy="{cy}" r="{r_dial * 0.5}" fill="none" '
            f'stroke="#1e293b" stroke-width="1.0" '
            f'stroke-dasharray="3,3" />',
        ]

        # 12-Hour Numerals & Tick Marks
        for hr in range(1, 13):
            # 12 is top (270° or -90°), each hour is 30°
            angle_deg = hr * 30.0 - 90.0
            rad = math.radians(angle_deg)
            tx = cx + (r_dial - 18.0) * math.cos(rad)
            ty = cy + (r_dial - 18.0) * math.sin(rad) + 4.0
            svg_parts.append(
                f'<text x="{tx:.1f}" y="{ty:.1f}" fill="#64748b" font-size="11" font-weight="bold" '
                f'text-anchor="middle" font-family="sans-serif">{hr}</text>'
            )

        # Center Pivot Dot
        svg_parts.append(f'<circle cx="{cx}" cy="{cy}" r="4.5" fill="#f8fafc" />')

        # Pitch Spin Tilt Vectors
        for p in profile.pitches:
            # Calculate total angle in degrees
            tot_hrs = (p.tilt_hours % 12) + (p.tilt_minutes / 60.0)
            angle_deg = tot_hrs * 30.0 - 90.0
            rad = math.radians(angle_deg)

            # Vector length scaled by spin efficiency
            eff_frac = max(0.15, min(1.0, p.spin_efficiency_pct / 100.0))
            v_len = 30.0 + eff_frac * 105.0

            vx = cx + v_len * math.cos(rad)
            vy = cy + v_len * math.sin(rad)

            # Draw vector ray
            svg_parts.append(
                f'<line x1="{cx}" y1="{cy}" x2="{vx:.1f}" y2="{vy:.1f}" stroke="{p.color_hex}" '
                f'stroke-width="3.0" stroke-linecap="round" />'
            )
            # Arrowhead / tip circle
            svg_parts.append(
                f'<circle cx="{vx:.1f}" cy="{vy:.1f}" r="5.0" '
                f'fill="{p.color_hex}" stroke="#ffffff" '
                f'stroke-width="1.2" />'
            )

            # Pitch Tag
            lx = cx + (v_len + 16.0) * math.cos(rad)
            ly = cy + (v_len + 16.0) * math.sin(rad) + 3.5
            svg_parts.append(
                f'<text x="{lx:.1f}" y="{ly:.1f}" fill="{p.color_hex}" '
                f'font-size="10" font-weight="bold" '
                f'text-anchor="middle" font-family="sans-serif">{p.pitch_type}</text>'
            )

        svg_parts.append("</svg>")
        return GeneratedVectorChart(
            chart_type=ChartType.SPIN_AXIS_CLOCK,
            title=profile.title,
            svg_content="\n".join(svg_parts),
            width_px=self.width,
            height_px=self.height,
        )


@dataclasses.dataclass(frozen=True)
class PitchSeparationPoint:
    """Individual pitch velocity and movement coordinates for arsenal separation plot."""

    pitch_type: str  # "FF", "SL", "CH", "SI", "CU"
    pitch_name: str
    velo_mph: float
    pfx_z_in: float  # Induced vertical break
    pfx_x_in: float  # Horizontal break
    color_hex: str = "#00d2be"


@dataclasses.dataclass(frozen=True)
class PitchSeparationArsenalProfile:
    """Arsenal velocity and movement separation profile."""

    title: str
    pitcher_name: str
    pitches: list[PitchSeparationPoint]


class SeparationDiamondPlotRenderer:
    """Renders pure-Python vector SVG arsenal separation plots (SEPARATION-PLOT-01)."""

    def __init__(self, width: int = 520, height: int = 460) -> None:
        self.width = width
        self.height = height

    def render(self, profile: PitchSeparationArsenalProfile) -> GeneratedVectorChart:
        """Render multi-pitch velocity vs IVB Cartesian plot with separation deltas."""
        margin_left = 65.0
        margin_right = 40.0
        margin_top = 60.0
        margin_bottom = 60.0

        plot_w = self.width - margin_left - margin_right
        plot_h = self.height - margin_top - margin_bottom

        v_min, v_max = 75.0, 102.0
        z_min, z_max = -15.0, 25.0

        def to_screen_x(v: float) -> float:
            return margin_left + ((v - v_min) / (v_max - v_min)) * plot_w

        def to_screen_y(z: float) -> float:
            return margin_top + ((z_max - z) / (z_max - z_min)) * plot_h

        svg_parts: list[str] = [
            f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {self.width} {self.height}" '
            f'width="{self.width}" height="{self.height}" '
            f'style="background-color: #0b1329; border-radius: 8px;">',
            f'<text x="{self.width / 2}" y="26" fill="#f8fafc" font-size="14" font-weight="bold" '
            f'text-anchor="middle" font-family="sans-serif">{profile.title}</text>',
            f'<text x="{self.width / 2}" y="44" fill="#94a3b8" font-size="11" text-anchor="middle" '
            f'font-family="sans-serif">{profile.pitcher_name} Velocity & Movement Banding</text>',
            # Plot Background and Grid
            f'<rect x="{margin_left}" y="{margin_top}" width="{plot_w}" height="{plot_h}" '
            f'fill="#0f172a" stroke="#334155" stroke-width="1.2" rx="4" />',
        ]

        # Horizontal Gridlines (IVB)
        for ivb in range(-10, 25, 10):
            gy = to_screen_y(float(ivb))
            svg_parts.append(
                f'<line x1="{margin_left}" y1="{gy:.1f}" x2="{margin_left + plot_w}" y2="{gy:.1f}" '
                f'stroke="#1e293b" stroke-width="1.0" stroke-dasharray="3,3" />'
            )
            svg_parts.append(
                f'<text x="{margin_left - 8}" y="{gy + 4:.1f}" fill="#64748b" font-size="10" '
                f'text-anchor="end" font-family="sans-serif">{ivb:+}in</text>'
            )

        # Vertical Gridlines (Velo)
        for v in range(80, 105, 5):
            gx = to_screen_x(float(v))
            svg_parts.append(
                f'<line x1="{gx:.1f}" y1="{margin_top}" x2="{gx:.1f}" y2="{margin_top + plot_h}" '
                f'stroke="#1e293b" stroke-width="1.0" stroke-dasharray="3,3" />'
            )
            svg_parts.append(
                f'<text x="{gx:.1f}" y="{margin_top + plot_h + 16}" fill="#64748b" font-size="10" '
                f'text-anchor="middle" font-family="sans-serif">{v}mph</text>'
            )

        # Find primary fastball for separation delta lines
        fastballs = [p for p in profile.pitches if "FF" in p.pitch_type or "SI" in p.pitch_type]
        anchor = (
            max(fastballs, key=lambda p: p.velo_mph)
            if fastballs
            else (profile.pitches[0] if profile.pitches else None)
        )

        if anchor:
            ax = to_screen_x(anchor.velo_mph)
            ay = to_screen_y(anchor.pfx_z_in)

            # Draw delta connection lines
            for p in profile.pitches:
                if p == anchor:
                    continue
                px = to_screen_x(p.velo_mph)
                py = to_screen_y(p.pfx_z_in)
                svg_parts.append(
                    f'<line x1="{ax:.1f}" y1="{ay:.1f}" x2="{px:.1f}" y2="{py:.1f}" '
                    f'stroke="#475569" stroke-width="1.2" stroke-dasharray="4,4" />'
                )
                # Label midpoint with delta velo
                mx = (ax + px) / 2.0
                my = (ay + py) / 2.0 - 4.0
                dv = round(p.velo_mph - anchor.velo_mph, 1)
                svg_parts.append(
                    f'<text x="{mx:.1f}" y="{my:.1f}" fill="#94a3b8" font-size="9" '
                    f'text-anchor="middle" font-family="sans-serif">{dv:+.1f}mph</text>'
                )

        # Draw Pitch Nodes
        for p in profile.pitches:
            sx = to_screen_x(p.velo_mph)
            sy = to_screen_y(p.pfx_z_in)
            svg_parts.append(
                f'<circle cx="{sx:.1f}" cy="{sy:.1f}" r="8.0" fill="{p.color_hex}" '
                f'stroke="#ffffff" stroke-width="1.5" />'
            )
            svg_parts.append(
                f'<text x="{sx:.1f}" y="{sy - 12.0:.1f}" fill="{p.color_hex}" font-size="11" '
                f'font-weight="bold" text-anchor="middle" '
                f'font-family="sans-serif">{p.pitch_type}</text>'
            )
            svg_parts.append(
                f'<text x="{sx:.1f}" y="{sy + 18.0:.1f}" fill="#f8fafc" font-size="9" '
                f'text-anchor="middle" font-family="sans-serif">{p.velo_mph:.1f}</text>'
            )

        svg_parts.append("</svg>")
        return GeneratedVectorChart(
            chart_type=ChartType.SEPARATION_DIAMOND_PLOT,
            title=profile.title,
            svg_content="\n".join(svg_parts),
            width_px=self.width,
            height_px=self.height,
        )


@dataclasses.dataclass(frozen=True)
class SpraySectorData:
    """Batted ball trajectory elevation mix across directional spray sectors."""

    sector_name: str  # "Dead Pull", "Pull", "Center", "Oppo", "Dead Oppo"
    spray_angle_center_deg: float  # -45° to +45° (0° is CF, negative is pull for RHB)
    groundball_pct: float
    linedrive_pct: float
    flyball_pct: float
    popup_pct: float
    avg_ev_mph: float


@dataclasses.dataclass(frozen=True)
class BatterSprayElevationRoseProfile:
    """Batter spray and elevation rose chart profile."""

    title: str
    batter_name: str
    sectors: list[SpraySectorData]


class SprayElevationRoseRenderer:
    """Renders pure-Python vector SVG spray and elevation polar rose charts (SPRAY-ROSE-01)."""

    def __init__(self, width: int = 480, height: int = 480) -> None:
        self.width = width
        self.height = height

    def render(self, profile: BatterSprayElevationRoseProfile) -> GeneratedVectorChart:
        """Render directional polar rose wedges with elevation breakdown into vector SVG."""
        cx = self.width / 2.0
        cy = self.height - 75.0
        r_max = 240.0

        svg_parts: list[str] = [
            f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {self.width} {self.height}" '
            f'width="{self.width}" height="{self.height}" '
            f'style="background-color: #0b1329; border-radius: 8px;">',
            f'<text x="{self.width / 2}" y="28" fill="#f8fafc" font-size="14" font-weight="bold" '
            f'text-anchor="middle" font-family="sans-serif">{profile.title}</text>',
            f'<text x="{self.width / 2}" y="46" fill="#94a3b8" font-size="11" text-anchor="middle" '
            f'font-family="sans-serif">{profile.batter_name} Directional Trajectory Rose</text>',
        ]

        # Draw Outfield Arc Boundaries (Polar grid)
        for r_step in (80.0, 160.0, 240.0):
            svg_parts.append(
                f'<path d="M {cx - r_step * 0.707:.1f} {cy - r_step * 0.707:.1f} '
                f'A {r_step} {r_step} 0 0 1 {cx + r_step * 0.707:.1f} {cy - r_step * 0.707:.1f}" '
                f'fill="none" stroke="#1e293b" stroke-width="1.0" stroke-dasharray="3,3" />'
            )

        # Foul lines (-45° and +45°)
        fl_len = r_max * 1.05
        fl_lx = cx - fl_len * 0.707
        fl_ly = cy - fl_len * 0.707
        fl_rx = cx + fl_len * 0.707
        fl_ry = cy - fl_len * 0.707
        svg_parts.append(
            f'<line x1="{cx}" y1="{cy}" x2="{fl_lx:.1f}" y2="{fl_ly:.1f}" '
            f'stroke="#475569" stroke-width="1.5" />'
        )
        svg_parts.append(
            f'<line x1="{cx}" y1="{cy}" x2="{fl_rx:.1f}" y2="{fl_ry:.1f}" '
            f'stroke="#475569" stroke-width="1.5" />'
        )

        # Render Rose Sectors
        for sec in profile.sectors:
            # 0° is straight up (-90° in standard SVG screen space)
            base_angle_deg = -90.0 + sec.spray_angle_center_deg
            half_w_deg = 8.5  # wedge width
            a1_rad = math.radians(base_angle_deg - half_w_deg)
            a2_rad = math.radians(base_angle_deg + half_w_deg)

            # Stacked Elevation Wedges: GB (inner) -> LD -> FB -> PU (outer)
            r_ev_scale = max(0.5, min(1.0, sec.avg_ev_mph / 100.0))
            tot_len = r_max * 0.95 * r_ev_scale

            r_gb = tot_len * (sec.groundball_pct / 100.0)
            r_ld = r_gb + tot_len * (sec.linedrive_pct / 100.0)
            r_fb = r_ld + tot_len * (sec.flyball_pct / 100.0)
            r_pu = tot_len

            def make_arc(r_inner: float, r_outer: float, a1: float, a2: float, color: str) -> str:
                x1_in = cx + r_inner * math.cos(a1)
                y1_in = cy + r_inner * math.sin(a1)
                x2_in = cx + r_inner * math.cos(a2)
                y2_in = cy + r_inner * math.sin(a2)

                x1_out = cx + r_outer * math.cos(a1)
                y1_out = cy + r_outer * math.sin(a1)
                x2_out = cx + r_outer * math.cos(a2)
                y2_out = cy + r_outer * math.sin(a2)

                return (
                    f'<path d="M {x1_in:.1f} {y1_in:.1f} L {x1_out:.1f} {y1_out:.1f} '
                    f"A {r_outer:.1f} {r_outer:.1f} 0 0 1 {x2_out:.1f} {y2_out:.1f} "
                    f"L {x2_in:.1f} {y2_in:.1f} "
                    f'A {r_inner:.1f} {r_inner:.1f} 0 0 0 {x1_in:.1f} {y1_in:.1f} Z" '
                    f'fill="{color}" stroke="#0b1329" stroke-width="0.8" />'
                )

            svg_parts.append(make_arc(10.0, r_gb, a1_rad, a2_rad, "#475569"))  # Groundball
            svg_parts.append(make_arc(r_gb, r_ld, a1_rad, a2_rad, "#10b981"))  # Line Drive
            svg_parts.append(make_arc(r_ld, r_fb, a1_rad, a2_rad, "#f59e0b"))  # Flyball
            svg_parts.append(make_arc(r_fb, r_pu, a1_rad, a2_rad, "#6366f1"))  # Popup

            # Label sector tip
            tx = cx + (r_pu + 14.0) * math.cos(math.radians(base_angle_deg))
            ty = cy + (r_pu + 14.0) * math.sin(math.radians(base_angle_deg))
            svg_parts.append(
                f'<text x="{tx:.1f}" y="{ty:.1f}" fill="#94a3b8" font-size="9" font-weight="bold" '
                f'text-anchor="middle" font-family="sans-serif">{sec.sector_name}</text>'
            )

        # Home Plate polygon at origin
        svg_parts.append(
            f'<polygon points="{cx - 8.0:.1f},{cy:.1f} {cx + 8.0:.1f},{cy:.1f} '
            f"{cx + 8.0:.1f},{cy + 6.0:.1f} "
            f'{cx:.1f},{cy + 12.0:.1f} {cx - 8.0:.1f},{cy + 6.0:.1f}" '
            f'fill="#f8fafc" stroke="#94a3b8" stroke-width="1.0" />'
        )

        svg_parts.append("</svg>")
        return GeneratedVectorChart(
            chart_type=ChartType.SPRAY_ELEVATION_ROSE,
            title=profile.title,
            svg_content="\n".join(svg_parts),
            width_px=self.width,
            height_px=self.height,
        )


@dataclasses.dataclass(frozen=True)
class PitchReleasePoint:
    """Release point centroid and spatial variance for an arsenal pitch."""

    pitch_type: str  # "FF", "SL", "CH", "CB"
    rel_x_ft: float  # Horizontal release (-3.5 to +3.5 ft)
    rel_z_ft: float  # Vertical release (4.5 to 7.0 ft)
    std_x_in: float  # Horizontal std dev in inches
    std_z_in: float  # Vertical std dev in inches
    color_hex: str = "#3b82f6"


@dataclasses.dataclass(frozen=True)
class PitcherReleaseWindowProfile:
    """Pitcher arsenal release point tunneling profile."""

    title: str
    pitcher_name: str
    pitches: list[PitchReleasePoint]


class ReleaseWindowBoxRenderer:
    """Renders pure-Python vector SVG release window scatter plots (RELEASE-BOX-01)."""

    def __init__(self, width: int = 480, height: int = 480) -> None:
        self.width = width
        self.height = height

    def render(self, profile: PitcherReleaseWindowProfile) -> GeneratedVectorChart:
        """Render multi-pitch release scatter centroids with confidence ellipses into SVG."""
        margin_left = 60
        margin_right = 40
        margin_top = 70
        margin_bottom = 60

        plot_w = self.width - margin_left - margin_right
        plot_h = self.height - margin_top - margin_bottom

        # Coordinate domain: X from -3.5 to +3.5 ft, Z from 4.5 to 7.0 ft
        x_min, x_max = -3.5, 3.5
        z_min, z_max = 4.5, 7.0

        def to_screen(rx: float, rz: float) -> tuple[float, float]:
            sx = margin_left + ((rx - x_min) / (x_max - x_min)) * plot_w
            sy = margin_top + ((z_max - rz) / (z_max - z_min)) * plot_h
            return sx, sy

        svg_parts: list[str] = [
            f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {self.width} {self.height}" '
            f'width="{self.width}" height="{self.height}" '
            f'style="background-color: #0b1329; border-radius: 8px;">',
            f'<text x="{self.width / 2}" y="28" fill="#f8fafc" font-size="14" font-weight="bold" '
            f'text-anchor="middle" font-family="sans-serif">{profile.title}</text>',
            f'<text x="{self.width / 2}" y="46" fill="#94a3b8" font-size="11" text-anchor="middle" '
            f'font-family="sans-serif">{profile.pitcher_name} Release Tunneling Envelopes</text>',
        ]

        # Inner Plot Box Background
        svg_parts.append(
            f'<rect x="{margin_left}" y="{margin_top}" width="{plot_w}" height="{plot_h}" '
            f'fill="#0f172a" stroke="#334155" stroke-width="1.0" />'
        )

        # Center X Guideline (Mound Center X=0)
        cx0, _ = to_screen(0.0, 5.75)
        svg_parts.append(
            f'<line x1="{cx0:.1f}" y1="{margin_top}" x2="{cx0:.1f}" y2="{margin_top + plot_h}" '
            f'stroke="#1e293b" stroke-width="1.0" stroke-dasharray="3,3" />'
        )

        # Draw Grid & Axis Labels
        for x_val in (-3.0, -1.5, 0.0, 1.5, 3.0):
            sx, _ = to_screen(x_val, 5.0)
            svg_parts.append(
                f'<text x="{sx:.1f}" y="{margin_top + plot_h + 18}" fill="#64748b" font-size="9" '
                f'text-anchor="middle" font-family="sans-serif">{x_val:>+3.1f} ft</text>'
            )

        for z_val in (5.0, 5.5, 6.0, 6.5, 7.0):
            _, sy = to_screen(0.0, z_val)
            svg_parts.append(
                f'<line x1="{margin_left}" y1="{sy:.1f}" x2="{margin_left + plot_w}" y2="{sy:.1f}" '
                f'stroke="#1e293b" stroke-width="0.8" />'
            )
            svg_parts.append(
                f'<text x="{margin_left - 8}" y="{sy + 3:.1f}" fill="#64748b" font-size="9" '
                f'text-anchor="end" font-family="sans-serif">{z_val:.1f} ft</text>'
            )

        # Render Pitches (Centroid + 1-sigma Ellipse)
        for p in profile.pitches:
            px, py = to_screen(p.rel_x_ft, p.rel_z_ft)

            # Ellipse radii in screen pixels (std_in / 12 -> ft -> pixels)
            erx = ((p.std_x_in / 12.0) / (x_max - x_min)) * plot_w
            ery = ((p.std_z_in / 12.0) / (z_max - z_min)) * plot_h

            # Confidence ellipse
            svg_parts.append(
                f'<ellipse cx="{px:.1f}" cy="{py:.1f}" rx="{erx:.1f}" ry="{ery:.1f}" '
                f'fill="{p.color_hex}" fill-opacity="0.25" stroke="{p.color_hex}" '
                f'stroke-width="1.5" stroke-dasharray="2,2" />'
            )

            # Centroid point
            svg_parts.append(
                f'<circle cx="{px:.1f}" cy="{py:.1f}" r="5.0" fill="{p.color_hex}" '
                f'stroke="#ffffff" stroke-width="1.2" />'
            )

            # Label
            svg_parts.append(
                f'<text x="{px + 8.0:.1f}" y="{py - 6.0:.1f}" fill="{p.color_hex}" font-size="10" '
                f'font-weight="bold" font-family="sans-serif">{p.pitch_type}</text>'
            )

        # Legend
        svg_parts.append(
            f'<text x="{self.width / 2}" y="{self.height - 18}" fill="#94a3b8" font-size="9" '
            f'text-anchor="middle" font-family="sans-serif">Release X vs Z (1-sigma)</text>'
        )

        svg_parts.append("</svg>")
        return GeneratedVectorChart(
            chart_type=ChartType.RELEASE_WINDOW_BOX,
            title=profile.title,
            svg_content="\n".join(svg_parts),
            width_px=self.width,
            height_px=self.height,
        )


@dataclasses.dataclass(frozen=True)
class AttackZone9x9Cell:
    """Cell data inside a 9x9 fine-grained strike zone attack grid."""

    row: int  # 0 (top waste) to 8 (bottom waste)
    col: int  # 0 (inside waste) to 8 (outside waste)
    swing_pct: float
    woba_value: float
    whiff_pct: float


@dataclasses.dataclass(frozen=True)
class BatterAttackZone9x9Profile:
    """Batter fine-grained 9x9 attack zone heat matrix profile."""

    title: str
    batter_name: str
    metric_mode: str  # "wOBA", "Swing%", "Whiff%"
    cells: list[AttackZone9x9Cell]


class AttackZone9x9GridRenderer:
    """Renders pure-Python vector SVG 9x9 strike zone attack matrices (ATTACK-9X9-01)."""

    def __init__(self, width: int = 480, height: int = 480) -> None:
        self.width = width
        self.height = height

    def render(self, profile: BatterAttackZone9x9Profile) -> GeneratedVectorChart:
        """Render 9x9 fine-grained grid cells with zone boundaries into vector SVG."""
        margin_x = 75
        margin_top = 70
        grid_dim = 330
        cell_size = grid_dim / 9.0  # ~36.6px per cell

        svg_parts: list[str] = [
            f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {self.width} {self.height}" '
            f'width="{self.width}" height="{self.height}" '
            f'style="background-color: #0b1329; border-radius: 8px;">',
            f'<text x="{self.width / 2}" y="28" fill="#f8fafc" font-size="14" font-weight="bold" '
            f'text-anchor="middle" font-family="sans-serif">{profile.title}</text>',
            f'<text x="{self.width / 2}" y="46" fill="#94a3b8" font-size="11" text-anchor="middle" '
            f'font-family="sans-serif">{profile.batter_name} 9x9 ({profile.metric_mode})</text>',
        ]

        def get_color(val: float) -> str:
            # Color map for wOBA: <0.240 blue, 0.320 slate, >0.420 red
            if val < 0.240:
                return "#1e3a8a"
            elif val < 0.300:
                return "#334155"
            elif val < 0.360:
                return "#d97706"
            elif val < 0.450:
                return "#dc2626"
            return "#991b1b"

        # Render 9x9 cells
        for cell in profile.cells:
            cx = margin_x + cell.col * cell_size
            cy = margin_top + cell.row * cell_size
            col_hex = get_color(cell.woba_value)

            svg_parts.append(
                f'<rect x="{cx:.1f}" y="{cy:.1f}" width="{cell_size:.1f}" height="{cell_size:.1f}" '
                f'fill="{col_hex}" stroke="#0b1329" stroke-width="0.8" />'
            )
            # Text inside cell
            svg_parts.append(
                f'<text x="{cx + cell_size / 2:.1f}" y="{cy + cell_size / 2 + 3:.1f}" '
                f'fill="#f8fafc" font-size="8" font-weight="bold" text-anchor="middle" '
                f'font-family="sans-serif">.{int(cell.woba_value * 1000):03d}</text>'
            )

        # Official Strike Zone Boundary Box: rows 2 to 6, cols 2 to 6 (5x5 inner area)
        sz_x = margin_x + 2 * cell_size
        sz_y = margin_top + 2 * cell_size
        sz_w = 5 * cell_size
        sz_h = 5 * cell_size
        svg_parts.append(
            f'<rect x="{sz_x:.1f}" y="{sz_y:.1f}" width="{sz_w:.1f}" height="{sz_h:.1f}" '
            f'fill="none" stroke="#f8fafc" stroke-width="2.2" />'
        )

        # Heart Zone Inner Box (rows 3 to 5, cols 3 to 5 - 3x3 core)
        hz_x = margin_x + 3 * cell_size
        hz_y = margin_top + 3 * cell_size
        hz_w = 3 * cell_size
        hz_h = 3 * cell_size
        svg_parts.append(
            f'<rect x="{hz_x:.1f}" y="{hz_y:.1f}" width="{hz_w:.1f}" height="{hz_h:.1f}" '
            f'fill="none" stroke="#94a3b8" stroke-width="1.2" stroke-dasharray="3,3" />'
        )

        # Legend
        svg_parts.append(
            f'<text x="{self.width / 2}" y="{self.height - 18}" fill="#94a3b8" font-size="9" '
            f'text-anchor="middle" font-family="sans-serif">Zone Edge vs Heart Core</text>'
        )

        svg_parts.append("</svg>")
        return GeneratedVectorChart(
            chart_type=ChartType.ATTACK_ZONE_9X9_GRID,
            title=profile.title,
            svg_content="\n".join(svg_parts),
            width_px=self.width,
            height_px=self.height,
        )


def health_check() -> list[Check]:
    """Operational health check for the Visual Asset & Chart Generation Engine (VISUAL-01)."""
    checks: list[Check] = []
    try:
        from mlb_baseball.model.heatmap import BattedBallBallisticsEngine, StrikeZoneKDEMonitor

        sz_renderer = StrikeZoneHeatmapRenderer()
        spray_renderer = DiamondSprayChartRenderer()
        we_renderer = WinExpectancyGraphRenderer()

        kde = StrikeZoneKDEMonitor()
        grid = kde.compute_density_grid([0.1, 0.2], [2.5, 2.8], grid_size=(5, 5))
        sz_chart = sz_renderer.render(grid)

        ballistics = BattedBallBallisticsEngine()
        hits = [ballistics.compute_field_coordinates("h1", 102.0, 26.0, 5.0)]
        spray_chart = spray_renderer.render(hits)

        we_points = [(0, 0.50, 1.0), (1, 0.65, 1.8), (2, 0.90, 2.5)]
        we_chart = we_renderer.render(we_points)

        radar_renderer = RadarChartRenderer()
        dims = [
            RadarDimension("Contact", 80),
            RadarDimension("Power", 90),
            RadarDimension("Discipline", 85),
        ]
        radar_chart = radar_renderer.render(PlayerRadarProfile("Test Radar", dims))

        odds_renderer = OddsMovementChartRenderer()
        pts = [
            OddsMovementPoint("Open", 1.85, 2.05),
            OddsMovementPoint("Close", 1.75, 2.20, is_steam_move=True),
        ]
        odds_chart = odds_renderer.render(MarketOddsTimeline("Test Odds", "LAD", "SF", pts))

        break_renderer = PitchBreakChartRenderer()
        pitches = [
            PitchBreakObservation("FF", 97.0, -8.0, 18.0),
            PitchBreakObservation("SL", 86.0, 6.0, 2.0),
        ]
        break_chart = break_renderer.render(PitcherArsenalBreakProfile("Test Pitcher", pitches))

        flow_renderer = InningScoreFlowRenderer()
        steps = [InningScoreStep(1, 0, 1, 0, 1), InningScoreStep(2, 0, 0, 0, 1)]
        flow_chart = flow_renderer.render(GameScoreFlowProfile("Test Flow", "LAD", "SF", steps))

        re24_renderer = RunExpectancyHeatmapRenderer()
        re24_chart = re24_renderer.render(BaseOutRunExpectancyGrid())

        hex_renderer = SpatialHexbinVisualizerRenderer()
        hex_pitches = [
            HexbinPitchObservation(0.1, 2.5, "FF", True),
            HexbinPitchObservation(-0.4, 3.1, "SL", False),
        ]
        hex_chart = hex_renderer.render(
            SpatialHexbinProfile("Test Hex", "Batter", "Pitcher", hex_pitches)
        )

        card_renderer = MatchupComparisonCardRenderer()
        m_comps = [MatchupMetricComparison("wOBA", 0.85, 0.65, ".395", ".310")]
        card_chart = card_renderer.render(
            MatchupCardProfile("Matchup", "Hitter", "Pitcher", "BATTER_ADVANTAGE", m_comps)
        )

        replay_renderer = WinProbabilityReplayRenderer()
        r_steps = [
            WinProbabilityReplayStep(0, 1, True, 0.50, "Start"),
            WinProbabilityReplayStep(1, 9, False, 0.95, "Walkoff HR", 0.45, True),
        ]
        replay_chart = replay_renderer.render(
            GameWPAReplayProfile("Replay", "LAD", "NYY", "6-3", r_steps)
        )

        f3d_renderer = PitchTrajectory3DVisualizerRenderer()
        f3d_pitches = [
            PitchTrajectory3DSpec("FF", "4-Seam", -2.2, 5.8, 0.2, 3.2, 8.0, 18.0, "#00d2be"),
            PitchTrajectory3DSpec("SL", "Slider", -2.3, 5.7, 0.6, 2.1, -6.0, 2.0, "#f59e0b"),
        ]
        f3d_chart = f3d_renderer.render(PitchTunnel3DProfile("3D Flight", "Skubal", f3d_pitches))

        zs_renderer = ZoneSurfaceContourRenderer()
        zs_cells = [ZoneGridValue(r, c, (r + c) / 8.0) for r in range(5) for c in range(5)]
        zs_chart = zs_renderer.render(ZoneSurfaceContourProfile("Surface", "Soto", "SLG", zs_cells))

        clk_renderer = SpinAxisClockVisualizerRenderer()
        clk_pitches = [
            PitchSpinClockSpec("FF", "4-Seam", 1, 15, 98.0, "#00d2be"),
            PitchSpinClockSpec("SL", "Slider", 9, 30, 22.0, "#f59e0b"),
        ]
        clk_chart = clk_renderer.render(
            PitcherSpinClockArsenalProfile("Spin Clock", "Skenes", clk_pitches)
        )

        sep_renderer = SeparationDiamondPlotRenderer()
        sep_pitches = [
            PitchSeparationPoint("FF", "4-Seam", 98.0, 18.0, -8.0, "#00d2be"),
            PitchSeparationPoint("CH", "Changeup", 87.0, 4.0, 14.0, "#a855f7"),
        ]
        sep_chart = sep_renderer.render(
            PitchSeparationArsenalProfile("Separation", "Skubal", sep_pitches)
        )

        rose_renderer = SprayElevationRoseRenderer()
        rose_sectors = [
            SpraySectorData("Pull", -22.0, 30.0, 35.0, 30.0, 5.0, 95.0),
            SpraySectorData("Center", 0.0, 20.0, 45.0, 30.0, 5.0, 98.0),
        ]
        rose_chart = rose_renderer.render(
            BatterSprayElevationRoseProfile("Rose", "Ohtani", rose_sectors)
        )

        box_renderer = ReleaseWindowBoxRenderer()
        box_pitches = [
            PitchReleasePoint("FF", -2.15, 5.85, 1.4, 1.2, "#3b82f6"),
            PitchReleasePoint("SL", -2.20, 5.80, 1.5, 1.3, "#ec4899"),
        ]
        box_chart = box_renderer.render(
            PitcherReleaseWindowProfile("Release Box", "Skenes", box_pitches)
        )

        grid_renderer = AttackZone9x9GridRenderer()
        grid_cells = [
            AttackZone9x9Cell(r, c_idx, 45.0, 0.340, 18.0) for r in range(9) for c_idx in range(9)
        ]
        grid_chart = grid_renderer.render(
            BatterAttackZone9x9Profile("Grid", "Soto", "wOBA", grid_cells)
        )

        if (
            "<svg" in sz_chart.svg_content
            and "<svg" in spray_chart.svg_content
            and "<svg" in we_chart.svg_content
            and "<svg" in radar_chart.svg_content
            and "<svg" in odds_chart.svg_content
            and "<svg" in break_chart.svg_content
            and "<svg" in flow_chart.svg_content
            and "<svg" in re24_chart.svg_content
            and "<svg" in hex_chart.svg_content
            and "<svg" in card_chart.svg_content
            and "<svg" in replay_chart.svg_content
            and "<svg" in f3d_chart.svg_content
            and "<svg" in zs_chart.svg_content
            and "<svg" in clk_chart.svg_content
            and "<svg" in sep_chart.svg_content
            and "<svg" in rose_chart.svg_content
            and "<svg" in box_chart.svg_content
            and "<svg" in grid_chart.svg_content
        ):
            checks.append(
                Check(
                    "visual chart generation engine",
                    True,
                    "SVG renderers verified (Heatmap, Spray, WE, Radar)",
                )
            )
        else:
            checks.append(
                Check(
                    "visual chart generation engine",
                    False,
                    "SVG generation failed to produce markup",
                )
            )
    except Exception as exc:
        checks.append(Check("visual chart generation engine", False, str(exc)))
    return checks
