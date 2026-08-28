"""Unit tests for Polymorphic Research Dossier & Multi-Format Exporter (EXPORT-01, ADR-121)."""

import json

from mlb_baseball.export import (
    ChartSectionBuilder,
    HTMLRenderer,
    KeyValueSectionBuilder,
    MarkdownRenderer,
    ResearchDossier,
    TableSectionBuilder,
    TerminalRenderer,
    get_renderer,
    health_check,
)


def test_markdown_renderer_tables_and_alerts():
    """Verify MarkdownRenderer produces valid GFM tables and alert callouts."""
    renderer = MarkdownRenderer()

    # 1. Title
    title_str = renderer.render_title("MLB Game Dossier", "BAL @ NYA")
    assert "# MLB Game Dossier" in title_str
    assert "> BAL @ NYA" in title_str

    # 2. Table
    table_str = renderer.render_table(
        headers=["Model", "Win%", "Edge"],
        rows=[["GBM-v2", "62.0%", "+12.0%"], ["Log5", "58.5%", "+8.5%"]],
        alignments=["left", "right", "right"],
    )
    assert "| Model | Win% | Edge |" in table_str
    assert "| :--- | ---: | ---: |" in table_str
    assert "| GBM-v2 | 62.0% | +12.0% |" in table_str

    # 3. Alert
    alert_str = renderer.render_alert("IMPORTANT", "Model recommends quarter-Kelly stake.")
    assert "> [!IMPORTANT]" in alert_str
    assert "quarter-Kelly" in alert_str

    # 4. ASCII Chart
    chart_str = renderer.render_ascii_bar_chart(
        items=[("Strikeout 5.5+", 74.5), ("Strikeout 6.5+", 58.2)],
        max_width=10,
    )
    assert "```text" in chart_str
    assert "Strikeout 5.5+" in chart_str
    assert "74.5%" in chart_str


def test_terminal_renderer_aligned_columns():
    """Verify TerminalRenderer generates properly padded and aligned columns."""
    renderer = TerminalRenderer()

    table_str = renderer.render_table(
        headers=["Pitcher", "Team", "K%"],
        rows=[["Gerrit Cole", "NYA", "29.5%"], ["Corbin Burnes", "BAL", "28.1%"]],
        alignments=["left", "left", "right"],
    )

    assert "Gerrit Cole" in table_str
    assert "Corbin Burnes" in table_str
    assert "---" in table_str


def test_html_renderer_semantic_markup():
    """Verify HTMLRenderer generates valid semantic HTML tags."""
    renderer = HTMLRenderer()

    title_html = renderer.render_title("Title", "Subtitle")
    assert (
        "<div class='dossier-header'><h1>Title</h1><p class='subtitle'>Subtitle</p></div>"
        in title_html
    )

    tbl_html = renderer.render_table(
        headers=["A", "B"],
        rows=[[1, 2]],
    )
    assert "<table class='dossier-table'>" in tbl_html
    assert "<th>A</th><th>B</th>" in tbl_html
    assert "<td>1</td><td>2</td>" in tbl_html


def test_dossier_assembler_composition():
    """Verify ResearchDossier accepts pluggable sections and exports across all formats."""
    dossier = ResearchDossier("NYA Matchup Dossier", "2026-08-24")

    # Add 3 distinct polymorphic section builders
    dossier.add_section(
        KeyValueSectionBuilder(
            "Game Details",
            [
                ("Venue", "Yankee Stadium"),
                ("Home Starter", "Gerrit Cole"),
                ("Away Starter", "Corbin Burnes"),
            ],
        )
    )
    dossier.add_section(
        TableSectionBuilder(
            "Model Forecasts",
            headers=["Model", "Home Win%"],
            rows=[["GBM-v2", "62.0%"], ["Log5-v2", "58.5%"]],
        )
    )
    dossier.add_section(
        ChartSectionBuilder(
            "Pitcher Strikeout PMF",
            items=[("4.5+ K", 88.0), ("5.5+ K", 74.5), ("6.5+ K", 58.2)],
        )
    )

    # 1. Export Markdown
    md_output = dossier.export(get_renderer("markdown"))
    assert "# NYA Matchup Dossier" in md_output
    assert "Yankee Stadium" in md_output
    assert "| GBM-v2 | 62.0% |" in md_output

    # 2. Export Terminal
    term_output = dossier.export(get_renderer("terminal"))
    assert "NYA MATCHUP DOSSIER" in term_output
    assert "Gerrit Cole" in term_output

    # 3. Export JSON
    json_str = dossier.to_json()
    data = json.loads(json_str)
    assert data["title"] == "NYA Matchup Dossier"
    assert len(data["sections"]) == 3
    assert data["sections"][0]["title"] == "Game Details"


def test_export_health_check():
    """Verify export engine health check passes cleanly."""
    checks = health_check()
    assert len(checks) == 1
    assert checks[0].ok is True
    assert "Multi-format" in checks[0].detail
