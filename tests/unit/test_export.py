"""Unit tests for Research Database Exporter & Interoperability Layer (EXPORT-01)."""

import builtins
from unittest.mock import MagicMock

import pytest

from mlb_baseball.export import (
    ALLOWLIST,
    BACKBONE_CANDIDATES,
    BACKBONE_EXCLUDED,
    BACKBONE_TABLES,
    RELATIONS,
    ExportRelation,
    _build_count_query,
    _build_select_query,
    export_to_parquet,
    export_to_xlsx,
    health_check,
    resolve_relation,
)


def test_resolve_relation_fully_qualified():
    """Verify fully qualified relation names resolve correctly."""
    rel = resolve_relation("gold.game_export")
    assert rel.schema == "gold"
    assert rel.table == "game_export"
    assert rel.season_column == "season"
    # game_export is a view over gold.game_feature, which carries Statcast/MLB-API
    # enrichment columns -> local_research, not redistributable (docs/SOURCE_RIGHTS.md).
    assert rel.profile == "local_research"


def test_resolve_relation_bare_name():
    """Verify bare table name resolves if present in the allow-list."""
    rel = resolve_relation("game_export")
    assert rel.qualified_name == "gold.game_export"

    player_rel = resolve_relation("player")
    assert player_rel.qualified_name == "core.player"


def test_resolve_relation_rejects_unknown():
    """Verify unknown or malicious table/query strings are rejected."""
    with pytest.raises(ValueError, match="is not in the export allow-list"):
        resolve_relation("unknown_table")

    with pytest.raises(ValueError, match="is not in the export allow-list"):
        resolve_relation("SELECT * FROM core.game")


def test_build_select_query_without_season():
    """Verify standard SELECT query without season filter."""
    rel = ExportRelation("gold", "game_export", "season", "public_safe")
    query, params = _build_select_query(rel)
    assert 'SELECT * FROM "gold"."game_export"' in query.as_string(None)
    assert params == []


def test_build_select_query_with_season():
    """Verify SELECT query with season parameter binding."""
    rel = ExportRelation("gold", "game_export", "season", "public_safe")
    query, params = _build_select_query(rel, season=2024)
    assert 'SELECT * FROM "gold"."game_export" WHERE "season" = %s' in query.as_string(None)
    assert params == [2024]


def test_build_select_query_rejects_season_on_unsupported_relation():
    """Verify attempting to filter a non-season table by season raises ValueError."""
    rel = ExportRelation("core", "player", None, "public_safe")
    with pytest.raises(ValueError, match="does not have a season column"):
        _build_select_query(rel, season=2024)


def test_build_count_query_with_season():
    """Verify count query builds with season parameter."""
    rel = ExportRelation("gold", "player_season", "season", "public_safe")
    query, params = _build_count_query(rel, season=2023)
    assert 'SELECT count(*) FROM "gold"."player_season" WHERE "season" = %s' in query.as_string(
        None
    )
    assert params == [2033] if False else params == [2023]


def test_excel_row_limit_guard():
    """Verify Excel exporter refuses relations exceeding the 1,048,576 row sheet limit."""
    conn = MagicMock()
    cur = MagicMock()
    conn.cursor.return_value.__enter__.return_value = cur
    cur.fetchone.return_value = (1_048_576,)  # 1 over max data rows

    rel = ExportRelation("core", "pitch", "season", "public_safe")
    with pytest.raises(ValueError, match="exceeds maximum sheet limit"):
        export_to_xlsx(conn, rel, pytest.importorskip("pathlib").Path("test.xlsx"))


def test_missing_pyarrow_error(monkeypatch):
    """Verify helpful error message when pyarrow is not installed."""
    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name in ("pyarrow", "pyarrow.parquet"):
            raise ImportError("No module named 'pyarrow'")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    conn = MagicMock()
    rel = ExportRelation("gold", "game_export", "season", "public_safe")

    with pytest.raises(RuntimeError, match="Parquet export requires pyarrow"):
        export_to_parquet(conn, rel, pytest.importorskip("pathlib").Path("test.parquet"))


def test_missing_openpyxl_error(monkeypatch):
    """Verify helpful error message when openpyxl is not installed."""
    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "openpyxl":
            raise ImportError("No module named 'openpyxl'")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    conn = MagicMock()
    rel = ExportRelation("gold", "game_export", "season", "public_safe")

    with pytest.raises(RuntimeError, match="Excel export requires openpyxl"):
        export_to_xlsx(conn, rel, pytest.importorskip("pathlib").Path("test.xlsx"))


def test_public_safe_relations_are_conservative():
    """public_safe is Retrosheet-only (docs/SOURCE_RIGHTS.md). This is the guard
    against a redistributable bundle silently shipping Statcast / MLB-API /
    Baseball-Reference / Lahman / Chadwick data. If you add a relation here, its
    entire lineage must be Retrosheet -- verify it and extend this allowlist in
    the same change."""
    allowed_public_safe = {
        "raw.retrosheet_event",
        "raw.retrosheet_gameinfo",
        "gold.run_expectancy_24",
        "gold.win_expectancy",
        "gold.leverage_index",
    }
    actual_public_safe = {r.qualified_name for r in RELATIONS if r.profile == "public_safe"}
    assert actual_public_safe == allowed_public_safe
    for rel in RELATIONS:
        if rel.profile == "public_safe":
            assert "Retrosheet" in rel.rights_note


def test_build_select_query_with_order_by():
    """Verify ORDER BY is appended for deterministic backbone export row order."""
    rel = ExportRelation(
        "gold", "batting_game", "season", "local_research", "", ("game_id", "player_id", "team_id")
    )
    query, params = _build_select_query(rel, order_by=rel.primary_key)
    assert query.as_string(None) == (
        'SELECT * FROM "gold"."batting_game" ORDER BY "game_id", "player_id", "team_id"'
    )
    assert params == []


def test_build_select_query_with_season_and_order_by():
    """Verify a season filter and ORDER BY compose correctly."""
    rel = ExportRelation(
        "gold", "batting_team", "season", "local_research", "", ("team_id", "season")
    )
    query, params = _build_select_query(rel, season=2023, order_by=rel.primary_key)
    assert query.as_string(None) == (
        'SELECT * FROM "gold"."batting_team" WHERE "season" = %s ORDER BY "team_id", "season"'
    )
    assert params == [2023]


def test_backbone_excludes_player_season_and_team_season():
    """player_season (Baseball-Reference) and team_season (Lahman) fail the
    redistribution rights review (rights-review.md) -- confirmed by inspecting
    their defining migrations, not merely anticipated by design.md."""
    assert set(BACKBONE_EXCLUDED) == {"gold.player_season", "gold.team_season"}
    assert "Baseball-Reference" in BACKBONE_EXCLUDED["gold.player_season"]
    assert "Lahman" in BACKBONE_EXCLUDED["gold.team_season"]


def test_backbone_tables_is_candidates_minus_excluded():
    """The publishable backbone set is exactly the eight Retrosheet-only relations."""
    assert set(BACKBONE_TABLES) == set(BACKBONE_CANDIDATES) - set(BACKBONE_EXCLUDED)
    assert BACKBONE_TABLES == (
        "gold.batting_game",
        "gold.pitching_game",
        "gold.batting_season",
        "gold.pitching_season",
        "gold.batting_team",
        "gold.pitching_team",
        "gold.batting_career",
        "gold.pitching_career",
    )
    for name in BACKBONE_TABLES:
        assert name in ALLOWLIST, f"{name} must remain a resolvable export relation"


def test_backbone_relations_have_primary_key_for_order_by():
    """Every publishable backbone relation declares a primary_key so the export
    query can ORDER BY it for deterministic row order (task 1.3)."""
    by_name = {r.qualified_name: r for r in RELATIONS}
    for name in BACKBONE_TABLES:
        assert by_name[name].primary_key, f"{name} must declare primary_key"


def test_export_health_check_passes():
    """Verify export module health check reports allowlist and optional dependencies."""
    checks = health_check()
    assert len(checks) == 3
    allowlist_check = next(c for c in checks if c.name == "export allowlist")
    assert allowlist_check.ok is True
    assert f"{len(ALLOWLIST)} relations registered" in allowlist_check.detail
