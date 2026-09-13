"""Every notebook under ``notebooks/`` uses only the released delivery surface
(the ``mlb_research`` package) and never reaches for a database layer
(notebook-recipes change; delivery spec "A runnable example notebook").

This is a static check -- it parses the notebook source rather than executing
it, because executing a notebook downloads the published dataset from Hugging
Face and CI carries no network dependency for the suite.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

NOTEBOOKS_DIR = Path(__file__).resolve().parents[2] / "notebooks"
NOTEBOOKS = sorted(NOTEBOOKS_DIR.glob("[0-9]*.py"))

_FORBIDDEN_IMPORT_ROOTS = {"mlb_baseball", "psycopg", "psycopg2", "sqlalchemy"}


def _imported_roots(source: str) -> set[str]:
    tree = ast.parse(source)
    roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            roots.add(node.module.split(".")[0])
    return roots


def test_at_least_five_notebooks_exist() -> None:
    assert len(NOTEBOOKS) >= 5, f"expected >=5 numbered notebooks, found {len(NOTEBOOKS)}"


@pytest.mark.parametrize("notebook", NOTEBOOKS, ids=lambda p: p.name)
def test_notebook_uses_only_the_released_surface(notebook: Path) -> None:
    roots = _imported_roots(notebook.read_text())

    assert "mlb_research" in roots, (
        f"{notebook.name} does not import mlb_research -- a recipe must run "
        "against the released dataset, not a live database"
    )

    leaked = roots & _FORBIDDEN_IMPORT_ROOTS
    assert not leaked, (
        f"{notebook.name} imports {sorted(leaked)} -- notebooks must not touch "
        "the database layer (delivery spec: 'makes no connection to a Postgres "
        "database and imports no database-layer package')"
    )
