"""Polymorphic Research Dossier & Multi-Format Exporter Architecture (EXPORT-01, ADR-121).

Provides an extensible, component-based document generation system:
1. Polymorphic renderers (Markdown, Terminal, HTML, JSON/Dict).
2. Pluggable section builders (Matchups, Pitcher Props, Portfolio, Standings, Research Citations).
3. ASCII distribution and histogram plotting utilities.
4. Clean decoupling between quantitative data structures and presentation layers.

Adheres strictly to object-oriented encapsulation, open-closed design principles,
and polymorphic composability.
"""

from __future__ import annotations

import dataclasses
import enum
import json
from collections.abc import Sequence
from typing import Any, Protocol

from mlb_baseball.health import Check


class ExportFormat(enum.Enum):
    """Supported export output formats."""

    MARKDOWN = "markdown"
    TERMINAL = "terminal"
    HTML = "html"
    JSON = "json"


# ---------------------------------------------------------------------------
# Polymorphic Document Renderers
# ---------------------------------------------------------------------------


class BaseDocumentRenderer(Protocol):
    """Polymorphic protocol for document formatters."""

    def render_title(self, title: str, subtitle: str | None = None) -> str:
        """Render the master document title and optional subtitle."""
        ...

    def render_section_header(self, heading: str, level: int = 2) -> str:
        """Render a section heading."""
        ...

    def render_table(
        self,
        headers: Sequence[str],
        rows: Sequence[Sequence[Any]],
        alignments: Sequence[str] | None = None,
    ) -> str:
        """Render a tabular dataset."""
        ...

    def render_key_values(self, pairs: Sequence[tuple[str, Any]]) -> str:
        """Render a key-value summary list."""
        ...

    def render_ascii_bar_chart(
        self,
        items: Sequence[tuple[str, float]],
        max_width: int = 30,
        unit: str = "%",
    ) -> str:
        """Render an ASCII horizontal bar chart."""
        ...

    def render_alert(self, level: str, message: str) -> str:
        """Render an emphasized note, tip, or warning alert box."""
        ...


class MarkdownRenderer:
    """GitHub Flavored Markdown (GFM) document renderer."""

    def render_title(self, title: str, subtitle: str | None = None) -> str:
        out = f"# {title}\n"
        if subtitle:
            out += f"\n> {subtitle}\n"
        return out + "\n"

    def render_section_header(self, heading: str, level: int = 2) -> str:
        prefix = "#" * max(1, min(6, level))
        return f"{prefix} {heading}\n\n"

    def render_table(
        self,
        headers: Sequence[str],
        rows: Sequence[Sequence[Any]],
        alignments: Sequence[str] | None = None,
    ) -> str:
        if not headers:
            return ""
        align_map = {"left": ":---", "center": ":---:", "right": "---:"}
        align_row = [
            align_map.get(a.lower(), "---:") if alignments and i < len(alignments) else "---:"
            for i, a in enumerate(alignments or ["right"] * len(headers))
        ]

        lines = [
            "| " + " | ".join(str(h) for h in headers) + " |",
            "| " + " | ".join(align_row) + " |",
        ]
        for row in rows:
            lines.append("| " + " | ".join(str(c) for c in row) + " |")
        return "\n".join(lines) + "\n\n"

    def render_key_values(self, pairs: Sequence[tuple[str, Any]]) -> str:
        lines = [f"- **{k}**: {v}" for k, v in pairs]
        return "\n".join(lines) + "\n\n"

    def render_ascii_bar_chart(
        self,
        items: Sequence[tuple[str, float]],
        max_width: int = 25,
        unit: str = "%",
    ) -> str:
        if not items:
            return ""
        max_val = max((val for _, val in items), default=1.0)
        max_val = max(max_val, 1e-6)
        max_label_len = max((len(lbl) for lbl, _ in items), default=10)

        lines = ["```text"]
        for label, val in items:
            bar_len = int(round((val / max_val) * max_width))
            bar_len = max(0, min(max_width, bar_len))
            bar_str = "█" * bar_len + "░" * (max_width - bar_len)
            lines.append(f"{label:<{max_label_len}} | {bar_str} | {val:>5.1f}{unit}")
        lines.append("```\n")
        return "\n".join(lines) + "\n"

    def render_alert(self, level: str, message: str) -> str:
        lvl_tag = (
            level.upper()
            if level.upper() in ("NOTE", "TIP", "IMPORTANT", "WARNING", "CAUTION")
            else "NOTE"
        )
        return f"> [!{lvl_tag}]\n> {message}\n\n"


class TerminalRenderer:
    """High-density ANSI text terminal renderer."""

    def render_title(self, title: str, subtitle: str | None = None) -> str:
        border = "=" * 80
        out = [border, f"  {title.upper()}"]
        if subtitle:
            out.append(f"  {subtitle}")
        out.append(border + "\n")
        return "\n".join(out)

    def render_section_header(self, heading: str, level: int = 2) -> str:
        return f"--- {heading.upper()} ---\n"

    def render_table(
        self,
        headers: Sequence[str],
        rows: Sequence[Sequence[Any]],
        alignments: Sequence[str] | None = None,
    ) -> str:
        if not headers:
            return ""
        # Determine column widths
        col_widths = [len(str(h)) for h in headers]
        for row in rows:
            for i, val in enumerate(row):
                if i < len(col_widths):
                    col_widths[i] = max(col_widths[i], len(str(val)))

        # Format header
        header_cells = [f"{str(h):<{col_widths[i]}}" for i, h in enumerate(headers)]
        hdr_line = "  ".join(header_cells)
        sep_line = "-" * len(hdr_line)

        lines = [hdr_line, sep_line]
        for row in rows:
            cells = []
            for i, val in enumerate(row):
                align = alignments[i] if alignments and i < len(alignments) else "right"
                w = col_widths[i] if i < len(col_widths) else 10
                if align == "left":
                    cells.append(f"{str(val):<{w}}")
                else:
                    cells.append(f"{str(val):>{w}}")
            lines.append("  ".join(cells))
        return "\n".join(lines) + "\n\n"

    def render_key_values(self, pairs: Sequence[tuple[str, Any]]) -> str:
        lines = [f"{k:<24}: {v}" for k, v in pairs]
        return "\n".join(lines) + "\n\n"

    def render_ascii_bar_chart(
        self,
        items: Sequence[tuple[str, float]],
        max_width: int = 25,
        unit: str = "%",
    ) -> str:
        if not items:
            return ""
        max_val = max((val for _, val in items), default=1.0)
        max_val = max(max_val, 1e-6)
        max_label_len = max((len(lbl) for lbl, _ in items), default=10)

        lines = []
        for label, val in items:
            bar_len = int(round((val / max_val) * max_width))
            bar_len = max(0, min(max_width, bar_len))
            bar_str = "#" * bar_len + "." * (max_width - bar_len)
            lines.append(f"{label:<{max_label_len}} | {bar_str} | {val:>5.1f}{unit}")
        return "\n".join(lines) + "\n\n"

    def render_alert(self, level: str, message: str) -> str:
        return f"[{level.upper()}]: {message}\n\n"


class HTMLRenderer:
    """Semantic HTML5 card and dossier renderer."""

    def render_title(self, title: str, subtitle: str | None = None) -> str:
        sub_html = f"<p class='subtitle'>{subtitle}</p>" if subtitle else ""
        return f"<div class='dossier-header'><h1>{title}</h1>{sub_html}</div>\n"

    def render_section_header(self, heading: str, level: int = 2) -> str:
        lvl = max(1, min(6, level))
        return f"<h{lvl} class='section-title'>{heading}</h{lvl}>\n"

    def render_table(
        self,
        headers: Sequence[str],
        rows: Sequence[Sequence[Any]],
        alignments: Sequence[str] | None = None,
    ) -> str:
        if not headers:
            return ""
        th_cells = "".join(f"<th>{h}</th>" for h in headers)
        lines = [
            "<table class='dossier-table'>",
            f"  <thead><tr>{th_cells}</tr></thead>",
            "  <tbody>",
        ]
        for row in rows:
            td_cells = "".join(f"<td>{c}</td>" for c in row)
            lines.append(f"    <tr>{td_cells}</tr>")
        lines.extend(["  </tbody>", "</table>\n"])
        return "\n".join(lines)

    def render_key_values(self, pairs: Sequence[tuple[str, Any]]) -> str:
        lines = ["<ul class='kv-list'>"]
        for k, v in pairs:
            lines.append(f"  <li><strong>{k}:</strong> {v}</li>")
        lines.append("</ul>\n")
        return "\n".join(lines)

    def render_ascii_bar_chart(
        self,
        items: Sequence[tuple[str, float]],
        max_width: int = 25,
        unit: str = "%",
    ) -> str:
        lines = ["<pre class='ascii-chart'>"]
        max_val = max((val for _, val in items), default=1.0)
        max_val = max(max_val, 1e-6)
        max_label_len = max((len(lbl) for lbl, _ in items), default=10)

        for label, val in items:
            bar_len = int(round((val / max_val) * max_width))
            bar_str = "█" * bar_len + "░" * (max_width - bar_len)
            lines.append(f"{label:<{max_label_len}} | {bar_str} | {val:>5.1f}{unit}")
        lines.append("</pre>\n")
        return "\n".join(lines)

    def render_alert(self, level: str, message: str) -> str:
        return (
            f"<div class='alert alert-{level.lower()}'>"
            f"<strong>{level.upper()}:</strong> {message}</div>\n"
        )


# ---------------------------------------------------------------------------
# Pluggable Component Section Builders
# ---------------------------------------------------------------------------


class BaseSectionBuilder(Protocol):
    """Polymorphic protocol for dossier section builders."""

    def build_section(self, renderer: BaseDocumentRenderer) -> str:
        """Build and render this section using the specified document renderer."""
        ...

    def to_dict(self) -> dict[str, Any]:
        """Serialize section data to a dictionary for JSON output."""
        ...


@dataclasses.dataclass(frozen=True)
class KeyValueSectionBuilder:
    """Generic key-value summary section builder."""

    title: str
    pairs: list[tuple[str, Any]]

    def build_section(self, renderer: BaseDocumentRenderer) -> str:
        out = renderer.render_section_header(self.title)
        out += renderer.render_key_values(self.pairs)
        return out

    def to_dict(self) -> dict[str, Any]:
        return {"title": self.title, "data": dict(self.pairs)}


@dataclasses.dataclass(frozen=True)
class TableSectionBuilder:
    """Generic tabular data section builder."""

    title: str
    headers: list[str]
    rows: list[list[Any]]
    alignments: list[str] | None = None

    def build_section(self, renderer: BaseDocumentRenderer) -> str:
        out = renderer.render_section_header(self.title)
        out += renderer.render_table(self.headers, self.rows, self.alignments)
        return out

    def to_dict(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "headers": self.headers,
            "rows": self.rows,
        }


@dataclasses.dataclass(frozen=True)
class ChartSectionBuilder:
    """Horizontal distribution bar chart section builder."""

    title: str
    items: list[tuple[str, float]]
    unit: str = "%"

    def build_section(self, renderer: BaseDocumentRenderer) -> str:
        out = renderer.render_section_header(self.title)
        out += renderer.render_ascii_bar_chart(self.items, unit=self.unit)
        return out

    def to_dict(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "items": [{"label": lbl, "value": val} for lbl, val in self.items],
            "unit": self.unit,
        }


# ---------------------------------------------------------------------------
# Master Dossier Assembler
# ---------------------------------------------------------------------------


class ResearchDossier:
    """Composable research dossier holding arbitrary modular sections."""

    def __init__(
        self,
        title: str,
        subtitle: str | None = None,
        sections: Sequence[BaseSectionBuilder] | None = None,
    ) -> None:
        self.title = title
        self.subtitle = subtitle
        self.sections: list[BaseSectionBuilder] = list(sections or [])

    def add_section(self, section: BaseSectionBuilder) -> ResearchDossier:
        """Append a section builder to the dossier."""
        self.sections.append(section)
        return self

    def export(self, renderer: BaseDocumentRenderer) -> str:
        """Export the complete document using the provided renderer."""
        chunks = [renderer.render_title(self.title, self.subtitle)]
        for sec in self.sections:
            chunks.append(sec.build_section(renderer))
        return "".join(chunks)

    def to_json(self, indent: int = 2) -> str:
        """Export structured data as JSON."""
        doc = {
            "title": self.title,
            "subtitle": self.subtitle,
            "sections": [sec.to_dict() for sec in self.sections],
        }
        return json.dumps(doc, indent=indent)


def get_renderer(fmt: ExportFormat | str) -> BaseDocumentRenderer:
    """Polymorphic factory returning the appropriate renderer instance."""
    fmt_enum = ExportFormat(fmt.lower()) if isinstance(fmt, str) else fmt
    if fmt_enum == ExportFormat.MARKDOWN:
        return MarkdownRenderer()
    elif fmt_enum == ExportFormat.HTML:
        return HTMLRenderer()
    elif fmt_enum == ExportFormat.TERMINAL:
        return TerminalRenderer()
    return MarkdownRenderer()


def health_check() -> list[Check]:
    """Operational health check for the Polymorphic Exporter Engine (EXPORT-01)."""
    checks: list[Check] = []
    try:
        dossier = ResearchDossier("Test", "Subtitle")
        dossier.add_section(KeyValueSectionBuilder("Summary", [("Key", "Value")]))
        md = dossier.export(MarkdownRenderer())
        term = dossier.export(TerminalRenderer())
        js = dossier.to_json()

        if "# Test" in md and "TEST" in term and '"title": "Test"' in js:
            checks.append(
                Check("research dossier exporter", True, "Multi-format rendering verified")
            )
        else:
            checks.append(
                Check("research dossier exporter", False, "Rendering mismatch across formats")
            )
    except Exception as exc:
        checks.append(Check("research dossier exporter", False, str(exc)))
    return checks
