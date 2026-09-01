"""Structural contracts for the repository's progressive-disclosure DOX tree."""

from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CHECKER = ROOT / "scripts" / "check_dox.py"


def _load_checker():
    spec = importlib.util.spec_from_file_location("check_dox", CHECKER)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_repository_dox_structure_is_valid() -> None:
    checker = _load_checker()
    problems = checker.validate(ROOT)
    assert problems == [], "\n".join(problem.render() for problem in problems)


def test_file_documented_profile_requires_matching_sidecar(tmp_path: Path) -> None:
    checker = _load_checker()
    (tmp_path / "AGENTS.md").write_text(
        "# Root\n\n## Child DOX Index\n\n"
        "- [pkg/AGENTS.md](pkg/AGENTS.md)\n",
        encoding="utf-8",
    )
    package = tmp_path / "pkg"
    package.mkdir()
    (package / "AGENTS.md").write_text(
        "# Package\n\nThis is a file-documented DOX profile.\n\n"
        "## Child DOX Index\n\nNo child DOX files.\n",
        encoding="utf-8",
    )
    (package / "source.py").write_text("VALUE = 1\n", encoding="utf-8")

    problems = checker.validate(tmp_path)
    assert any("missing required DOX sidecar" in problem.message for problem in problems)

    (package / "source.py.dox.md").write_text(
        "# source.py DOX\n\n## Purpose\n\nTest.\n\n"
        "## Ownership\n\nTest.\n\n## Verification\n\nTest.\n",
        encoding="utf-8",
    )
    assert checker.validate(tmp_path) == []


def test_orphan_sidecar_is_rejected(tmp_path: Path) -> None:
    checker = _load_checker()
    (tmp_path / "AGENTS.md").write_text(
        "# Root\n\n## Child DOX Index\n\nNo child DOX files.\n",
        encoding="utf-8",
    )
    (tmp_path / "gone.py.dox.md").write_text(
        "# gone.py DOX\n\n## Purpose\n\nTest.\n\n"
        "## Ownership\n\nTest.\n\n## Verification\n\nTest.\n",
        encoding="utf-8",
    )

    problems = checker.validate(tmp_path)
    assert any("orphaned sidecar" in problem.message for problem in problems)
