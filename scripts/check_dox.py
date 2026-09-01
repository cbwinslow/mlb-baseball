#!/usr/bin/env python3
"""Validate the repository's progressive-disclosure DOX structure.

The checker intentionally enforces only objective filesystem contracts:

* Child DOX Index links to AGENTS.md files must resolve.
* Every non-root AGENTS.md must be indexed by its nearest applicable parent.
* A directory declaring itself a "file-documented DOX profile" must give each
  direct Python source file (except __init__.py) a matching ``.py.dox.md``.
* File-level DOX sidecars must not be orphaned after a source rename/deletion.
* File-level sidecars must contain the minimum operational sections.

It does not lint prose quality, line counts, architectural opinions, or whether a
particular statement is semantically correct. Those remain review responsibilities.
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
AGENTS_NAME = "AGENTS.md"
FILE_PROFILE_MARKER = "file-documented DOX profile"
MINIMUM_SIDECAR_HEADINGS = ("## Purpose", "## Ownership", "## Verification")

_LINK_RE = re.compile(r"\[[^\]]+\]\(([^)]+/AGENTS\.md|AGENTS\.md)\)")


@dataclass(frozen=True, slots=True)
class Problem:
    path: Path
    message: str

    def render(self) -> str:
        try:
            display = self.path.relative_to(ROOT)
        except ValueError:
            display = self.path
        return f"{display}: {self.message}"


def _agents_files(root: Path = ROOT) -> list[Path]:
    """Return tracked-style AGENTS files, excluding common generated roots."""
    ignored_parts = {
        ".git",
        ".venv",
        ".pytest_cache",
        "__pycache__",
        "node_modules",
        "downloads",
        "backups",
    }
    return sorted(
        path
        for path in root.rglob(AGENTS_NAME)
        if not any(part in ignored_parts for part in path.relative_to(root).parts)
    )


def _child_index_text(path: Path) -> str:
    text = path.read_text(encoding="utf-8")
    marker = "## Child DOX Index"
    if marker not in text:
        return ""
    return text.split(marker, 1)[1]


def _indexed_children(path: Path) -> set[Path]:
    children: set[Path] = set()
    for target in _LINK_RE.findall(_child_index_text(path)):
        resolved = (path.parent / target).resolve()
        children.add(resolved)
    return children


def _nearest_parent_agents(path: Path, agents_files: set[Path], root: Path) -> Path | None:
    """Find the nearest ancestor AGENTS.md above ``path``."""
    current = path.parent.parent
    root = root.resolve()
    while True:
        candidate = (current / AGENTS_NAME).resolve()
        if candidate in agents_files:
            return candidate
        if current.resolve() == root or current.parent == current:
            return None
        current = current.parent


def check_child_indexes(root: Path = ROOT) -> list[Problem]:
    problems: list[Problem] = []
    agents = _agents_files(root)
    agent_set = {path.resolve() for path in agents}

    for parent in agents:
        for child in _indexed_children(parent):
            if not child.is_file():
                problems.append(Problem(parent, f"Child DOX Index target does not exist: {child}"))

    root_agents = (root / AGENTS_NAME).resolve()
    for child in agents:
        child_resolved = child.resolve()
        if child_resolved == root_agents:
            continue
        parent = _nearest_parent_agents(child, agent_set, root)
        if parent is None:
            problems.append(Problem(child, "has no ancestor AGENTS.md owner"))
            continue
        if child_resolved not in _indexed_children(parent):
            problems.append(
                Problem(
                    child,
                    f"not listed in nearest parent Child DOX Index: {parent.relative_to(root)}",
                )
            )
    return problems


def _is_file_documented_profile(agents_path: Path) -> bool:
    return FILE_PROFILE_MARKER.casefold() in agents_path.read_text(encoding="utf-8").casefold()


def check_file_profiles(root: Path = ROOT) -> list[Problem]:
    problems: list[Problem] = []
    for agents_path in _agents_files(root):
        if not _is_file_documented_profile(agents_path):
            continue
        directory = agents_path.parent
        for source in sorted(directory.glob("*.py")):
            if source.name == "__init__.py":
                continue
            sidecar = source.with_name(f"{source.name}.dox.md")
            if not sidecar.is_file():
                problems.append(Problem(source, f"missing required DOX sidecar {sidecar.name}"))
    return problems


def check_sidecars(root: Path = ROOT) -> list[Problem]:
    problems: list[Problem] = []
    ignored_parts = {".git", ".venv", "node_modules", "downloads", "backups"}
    for sidecar in sorted(root.rglob("*.py.dox.md")):
        if any(part in ignored_parts for part in sidecar.relative_to(root).parts):
            continue
        source = sidecar.with_name(sidecar.name.removesuffix(".dox.md"))
        if not source.is_file():
            problems.append(Problem(sidecar, f"orphaned sidecar; source does not exist: {source.name}"))
            continue
        text = sidecar.read_text(encoding="utf-8")
        for heading in MINIMUM_SIDECAR_HEADINGS:
            if heading not in text:
                problems.append(Problem(sidecar, f"missing required section: {heading}"))
    return problems


def validate(root: Path = ROOT) -> list[Problem]:
    return [
        *check_child_indexes(root),
        *check_file_profiles(root),
        *check_sidecars(root),
    ]


def main() -> int:
    problems = validate()
    if problems:
        print("DOX validation failed:")
        for problem in problems:
            print(f"  - {problem.render()}")
        return 1
    print("DOX validation passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
