#!/usr/bin/env python3
"""Flags inline SQL in mlb_baseball/*.py that should probably be a named
.sql resource under mlb_baseball/sql/ instead (issue #10).

docs/SQL_OWNERSHIP.md draws the line: stable, deterministic business-logic
mutations belong in a named .sql file; parameterized-identifier,
operational/diagnostic, and procedural-composition SQL stays inline.
SQLFluff already checks that the named .sql resources themselves are valid
SQL -- this script checks the other half docs/POLICY_REVIEW_2026-08.md
found nothing off-the-shelf could: whether a *new* piece of inline SQL
should have been extracted per that taxonomy.

Deliberately narrow, not a generic "detect all inline SQL" linter (the
policy review found no such tool exists because the taxonomy is
project-specific, and building one was explicitly out of scope for issue
#10): flags only a multi-line string literal passed directly to
`.execute(...)` that contains a mutating statement (INSERT/UPDATE/DELETE)
targeting `core.*`/`gold.*` -- an f-string, a `.format()` call, or a plain
variable is dynamic composition, which docs/SQL_OWNERSHIP.md's "Retain in
Python" section already allows to stay inline, and a single-line statement
is far more often a small operational/diagnostic one-liner than a business
mutation worth its own file.

Two ways to mark a real, already-reviewed exception:
- A single call site: a `# sql-ownership: allow -- <reason>` comment on
  the line immediately before the flagged `.execute(` call (matching this
  project's existing `# noqa`/`# type: ignore`-style inline-suppression
  convention) -- self-documenting at the point of use.
- An entire module: add it to EXEMPT_MODULES below, with a comment citing
  the exact docs/SQL_OWNERSHIP.md category/entry that already covers it.
  Used for the two modules (as of issue #10) whose *every* current
  mutation is one already-documented, whole-file exception -- e.g.
  conform.py's own "Remaining extraction queue" entry -- where 16
  individual near-identical inline comments would just be diff noise on
  a file this check isn't asking anyone to change yet, not real
  per-site justification.
"""

from __future__ import annotations

import ast
import re
import sys
from pathlib import Path
from typing import TypeGuard

MUTATING_TARGET_RE = re.compile(
    r"\b(INSERT\s+INTO|UPDATE|DELETE\s+FROM)\s+(core|gold)\.\w+",
    re.IGNORECASE,
)
ALLOW_COMMENT_RE = re.compile(r"#\s*sql-ownership:\s*allow\b")

EXEMPT_MODULES = {
    # docs/SQL_OWNERSHIP.md "Remaining extraction queue" #1: conform.py's
    # writes stay inline until identity/surrogate-ID contracts have
    # dedicated parity gates -- a deferred future milestone, not a gap
    # this check should flag today.
    "mlb_baseball/conform.py",
    # docs/SQL_OWNERSHIP.md "Retain in Python": "Multi-pass game/team
    # identity reconciliation and market snapshot matching."
    "mlb_baseball/model/identity.py",
}


def _is_execute_call(node: ast.AST) -> TypeGuard[ast.Call]:
    return (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "execute"
    )


def _sql_literal(call: ast.Call) -> str | None:
    """Return the SQL text if `call`'s first argument is a plain (non
    f-string, non-.format()) string literal -- Python already folds
    adjacent string literals like "a" "b" into one ast.Constant at parse
    time, so multi-piece literals are covered without extra handling."""
    if not call.args:
        return None
    first = call.args[0]
    if isinstance(first, ast.Constant) and isinstance(first.value, str):
        return first.value
    return None


def _allowed(lines: list[str], lineno: int) -> bool:
    """True if a `# sql-ownership: allow` comment sits on the line
    immediately above the flagged call (1-indexed lineno)."""
    if lineno - 2 < 0:
        return False
    return bool(ALLOW_COMMENT_RE.search(lines[lineno - 2]))


def check_file(path: Path, label: str) -> list[str]:
    source = path.read_text(encoding="utf-8")
    lines = source.splitlines()
    try:
        tree = ast.parse(source, filename=label)
    except SyntaxError as exc:
        return [f"{label}: could not parse ({exc})"]

    findings = []
    for node in ast.walk(tree):
        if not _is_execute_call(node):
            continue
        sql = _sql_literal(node)
        if sql is None or "\n" not in sql:
            continue
        if not MUTATING_TARGET_RE.search(sql):
            continue
        if _allowed(lines, node.lineno):
            continue
        findings.append(
            f"{label}:{node.lineno}: multi-line inline SQL mutates core.*/gold.* -- "
            "extract to a named mlb_baseball/sql/*.sql resource (docs/SQL_OWNERSHIP.md), "
            "or add '# sql-ownership: allow -- <reason>' on the line above if this is "
            "genuinely procedural/operational per that doc's 'Retain in Python' categories"
        )
    return findings


def main() -> int:
    repo_root = Path(__file__).resolve().parent.parent
    package_root = repo_root / "mlb_baseball"
    findings: list[str] = []
    for path in sorted(package_root.rglob("*.py")):
        if "/sql/" in str(path):
            continue
        relative = path.relative_to(repo_root).as_posix()
        if relative in EXEMPT_MODULES:
            continue
        findings.extend(check_file(path, relative))

    if findings:
        print("SQL ownership check failed:\n")
        for finding in findings:
            print(f"  {finding}")
        print(f"\n{len(findings)} finding(s). See docs/SQL_OWNERSHIP.md.")
        return 1

    print("SQL ownership check passed: no unjustified inline mutating SQL found.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
