"""Visual Asset & Vector Chart Generation Engine (VISUAL-01, ADR-131)."""

from __future__ import annotations

import dataclasses
import enum
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

        if (
            "<svg" in sz_chart.svg_content
            and "<svg" in spray_chart.svg_content
            and "<svg" in we_chart.svg_content
        ):
            checks.append(
                Check(
                    "visual chart generation engine",
                    True,
                    "SVG vector renderers verified (Heatmap, Spray, WE Graph)",
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
