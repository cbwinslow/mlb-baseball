#!/usr/bin/env python3
"""Validate the repository's structural DOX/progressive-context contracts.

This intentionally checks objective filesystem invariants only. It does not try
to lint prose quality, decide where a new DOX file should exist, or require every
source file to have a sidecar. Those are design/review decisions.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

_CHILD_INDEX_HEADING = "## Child DOX Index"
_SIDE_CAR_SUFFIX = ".dox.md"
_AGENT_FILE = "AGENTS.md"
_CLAUDE_FILE = "CLAUDE.md"

# Sidecars added as reviewed/verified DOX infrastructure. Keep this list explicit
# until a directory contract intentionally declares mechanically complete
# coverage. The generic orphan/source checks below still apply to every sidecar
# found anywhere in the repository.
REQUIRED_SIDECARS = (
    "mlb_baseball/cli.py.dox.md",
    "mlb_baseball/conform.py.dox.md",
    "mlb_baseball/load.py.dox.md",
    "mlb_baseball/public.py.dox.md",
    "mlb_baseball/registry.py.dox.md",
    "mlb_baseball/connectors/kalshi.py.dox.md",
    "mlb_baseball/connectors/mlb_api.py.dox.md",
    "mlb_baseball/connectors/polymarket.py.dox.md",
    "mlb_baseball/connectors/retrosheet.py.dox.md",
    "mlb_baseball/connectors/retrosheet_box.py.dox.md",
    "mlb_baseball/connectors/retrosheet_event.py.dox.md",
    "mlb_baseball/connectors/retrosheet_gamelog.py.dox.md",
    "mlb_baseball/connectors/retrosheet_reference.py.dox.md",
    "mlb_baseball/connectors/retrosheet_roster.py.dox.md",
    "mlb_baseball/connectors/retrosheet_schedule.py.dox.md",
    "mlb_baseball/connectors/retrosheet_transaction.py.dox.md",
    "mlb_baseball/connectors/statcast.py.dox.md",
    "mlb_baseball/connectors/statcast_leaderboard.py.dox.md",
)

_IGNORED_PARTS = {
    ".git",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".venv",
    "__pycache__",
    "node_modules",
    # Git worktrees under .claude/worktrees/ each hold a full checkout of the
    # repo, including its own AGENTS.md/*.dox.md tree -- scanning into them
    # double-counts every DOX file and reports spurious "not listed in parent
    # index" errors against the worktree's own root.
    ".claude",
    # Frozen historical docs (restructure step 3) -- not part of the live
    # progressive-disclosure contract.
    "archive",
}

# Child AGENTS files use the common DOX profile. The root intentionally has a
# different job: small invariant set + routing map, so it only needs the index.
_REQUIRED_CHILD_AGENT_HEADINGS = (
    "## Purpose",
    "## Child DOX Index",
)
_REQUIRED_SIDECAR_HEADINGS = (
    "## Purpose",
    "## Ownership",
    "## Verification",
    "## Child DOX Index",
)

_MARKDOWN_LINK_RE = re.compile(r"\[[^\]]+\]\(([^)]+)\)")


def _ignored(path: Path) -> bool:
    return any(part in _IGNORED_PARTS for part in path.parts)


def _files(root: Path, pattern: str) -> list[Path]:
    return sorted(path for path in root.rglob(pattern) if path.is_file() and not _ignored(path))


def _child_index_text(path: Path) -> str:
    text = path.read_text(encoding="utf-8")
    marker = text.find(_CHILD_INDEX_HEADING)
    if marker < 0:
        return ""
    section = text[marker + len(_CHILD_INDEX_HEADING) :]
    next_heading = re.search(r"^##\s+", section, flags=re.MULTILINE)
    return section[: next_heading.start()] if next_heading else section


def _indexed_agent_paths(parent: Path) -> set[Path]:
    indexed: set[Path] = set()
    for target in _MARKDOWN_LINK_RE.findall(_child_index_text(parent)):
        target = target.split("#", 1)[0]
        if not target.endswith(_AGENT_FILE):
            continue
        indexed.add((parent.parent / target).resolve())
    return indexed


def _nearest_parent_agent(path: Path, root: Path) -> Path | None:
    current = path.parent.parent
    root = root.resolve()
    while current == root or root in current.parents:
        candidate = current / _AGENT_FILE
        if candidate.exists():
            return candidate
        if current == root:
            break
        current = current.parent
    return None


def _check_required_headings(path: Path, headings: Iterable[str], errors: list[str]) -> None:
    text = path.read_text(encoding="utf-8")
    for heading in headings:
        if heading not in text:
            errors.append(f"{path}: missing required heading {heading!r}")


def check_dox(
    root: Path = ROOT,
    *,
    required_sidecars: Iterable[str] | None = None,
) -> list[str]:
    """Return structural DOX violations beneath *root*.

    ``required_sidecars`` defaults to this repository's reviewed baseline when
    validating the real repository. Tests/custom callers can pass an explicit
    iterable (including ``()``) for an isolated fixture tree.
    """

    root = root.resolve()
    errors: list[str] = []
    agent_files = _files(root, _AGENT_FILE)

    root_agent = root / _AGENT_FILE
    if root_agent not in agent_files:
        errors.append(f"{root_agent}: root AGENTS.md is missing")
    else:
        _check_required_headings(root_agent, (_CHILD_INDEX_HEADING,), errors)

    for agent in agent_files:
        if agent != root_agent:
            _check_required_headings(agent, _REQUIRED_CHILD_AGENT_HEADINGS, errors)

        # Every linked child must resolve to a real AGENTS.md file.
        for indexed in _indexed_agent_paths(agent):
            if not indexed.exists():
                errors.append(f"{agent}: Child DOX Index points to missing {indexed}")

        if agent == root_agent:
            continue
        parent = _nearest_parent_agent(agent, root)
        if parent is None:
            errors.append(f"{agent}: no ancestor AGENTS.md owns this child")
            continue
        if agent.resolve() not in _indexed_agent_paths(parent):
            errors.append(f"{agent}: not listed in nearest parent index {parent}")

    sidecars = _files(root, f"*{_SIDE_CAR_SUFFIX}")
    for sidecar in sidecars:
        source = Path(str(sidecar)[: -len(_SIDE_CAR_SUFFIX)])
        if not source.exists():
            errors.append(f"{sidecar}: orphan sidecar; source file {source} does not exist")
        _check_required_headings(sidecar, _REQUIRED_SIDECAR_HEADINGS, errors)

    if required_sidecars is None:
        required_sidecars = REQUIRED_SIDECARS if root == ROOT.resolve() else ()
    for relative in required_sidecars:
        sidecar = root / relative
        if not sidecar.exists():
            errors.append(f"{sidecar}: required DOX sidecar is missing")

    # Claude's native hierarchy is intentionally separate, but wherever a local
    # shared AGENTS.md exists the local Claude file must import that adjacent
    # shared contract rather than fork/duplicate it silently.
    for claude in _files(root, _CLAUDE_FILE):
        adjacent_agent = claude.with_name(_AGENT_FILE)
        if adjacent_agent.exists() and "@AGENTS.md" not in claude.read_text(encoding="utf-8"):
            errors.append(f"{claude}: adjacent AGENTS.md exists but '@AGENTS.md' is not imported")

    return sorted(errors)


def main() -> int:
    errors = check_dox()
    if errors:
        print("DOX validation failed:")
        for error in errors:
            print(f"- {error}")
        return 1
    print("DOX validation passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
