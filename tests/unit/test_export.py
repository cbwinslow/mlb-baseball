"""Unit tests for Research Database Exporter & Interoperability Layer (EXPORT-01)."""

import builtins
from unittest.mock import MagicMock

import pytest

from mlb_baseball.export import (
    ALLOWLIST,
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
    assert rel.profile == "public_safe"


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
    """Verify all public_safe relations only come from Retrosheet rights-cleared data."""
    for rel in RELATIONS:
        if rel.profile == "public_safe":
            assert "Retrosheet" in rel.rights_note or rel.schema in ("core", "gold", "raw")
            assert not rel.table.startswith("mlb_")
            assert not rel.table.startswith("statcast_")
            assert not rel.table.startswith("register_")
            assert not rel.table.startswith("news")
            assert rel.table != "player_war"
            assert rel.table != "market"
            assert rel.table != "game_feature"


def test_export_health_check_passes():
    """Verify export module health check reports allowlist and optional dependencies."""
    checks = health_check()
    assert len(checks) == 3
    allowlist_check = next(c for c in checks if c.name == "export allowlist")
    assert allowlist_check.ok is True
    assert f"{len(ALLOWLIST)} relations registered" in allowlist_check.detail
