#!/usr/bin/env python3
"""Advisory metric-catalog completeness + visibility-lint check
(metric-catalog, ADR-291; openspec/changes/metric-catalog/).

Two independent checks:

1. **Completeness (hard, non-zero exit on gaps).** Walks
   `mlb_baseball/model/*.py` and reports, per file, whether any
   `mlb_baseball/metrics/*.yaml` entry's `formula` field points at it (a
   `::function_name` suffix on `formula` is stripped before comparing). This
   is the drift guard from the proposal: a `model/` module with no catalog
   entry should be visible, not silently missing.

   Deliberately NOT an exhaustive hand-audit of every non-metric infra file
   in `model/` -- this first pass excludes a small, documented set of
   modules that are clearly orchestration/harness code rather than a single
   named statistic (`EXCLUDED_MODULES` below), and otherwise treats every
   remaining `*.py` file as a metric-shaped module that should eventually
   get an entry. Undercounting real gaps slightly (an infra file this list
   missed) is an acceptable, expected cost of this first pass -- the point
   of this script is to exist and run, not to already pass; the full
   ~155-module triage is a tracked, batched follow-up
   (openspec/project.md NEXT queue), not this change's job.

2. **Visibility lint (Decision 2, advisory only -- never changes the exit
   code).** Flags an entry whose `citation` matches a small allow-list of
   known-public-source substrings but is marked `visibility: internal`, or
   the reverse (no recognizable public citation, but `visibility: public`).
   Judgment calls exist on both sides of this line, so this only surfaces
   the mismatch for human review -- it does not fail CI on its own.

3. **Validated test_ref check (Decision 3).** For every `status: validated`
   entry (schema already requires `test_ref` to be set): hard-fail if
   `test_ref`'s file does not exist on disk; otherwise, best-effort
   (advisory only, never changes the exit code) flag entries whose named
   test's source has no recognizable external-fixture marker (a cited
   public source, a `source_url` field, or similar) -- a static proxy for
   "this test only hand-derives its own expected value" (design.md
   Decision 3). A human/reviewing agent makes the final call; this narrows
   the review, it does not replace it.

Wired into CI (`.github/workflows/ci.yml`, `lint` job) as an advisory
(`|| true`) step: it must run and report every PR, but must not block merge
until the first full triage pass has landed (design.md Migration Plan step
3; tasks.md 3.4).
"""

from __future__ import annotations

import sys
from pathlib import Path

from mlb_baseball.catalog import METRICS_DIR, CatalogError, MetricEntry, load_all

REPO_ROOT = Path(__file__).resolve().parent.parent
MODEL_DIR = REPO_ROOT / "mlb_baseball" / "model"

# Modules under mlb_baseball/model/ that are orchestration/harness/research
# infrastructure, not a single named statistic with its own citation --
# excluded from the completeness check rather than left to accumulate false
# "gap" noise. Each entry names the concrete reason it isn't metric-shaped.
# This list is deliberately small and will not catch every infra file on
# the first pass (see module docstring) -- a later batched triage narrows
# it further as each remaining module is actually read.
EXCLUDED_MODULES = {
    "__init__.py",
    "experiment.py",  # snapshot/fold/CLI harness (mlb experiment), not a metric
    "evaluation.py",  # cross-model scoring harness, not a metric
    "backtest.py",  # walk-forward harness plumbing, not a metric
    "feature_select.py",  # feature-selection stability harness, not a metric
    "feature_select_stepwise.py",  # ditto, stepwise variant
    "identity.py",  # cross-source ID reconciliation, not a metric
    "provenance.py",  # source/citation bookkeeping, not a metric itself
    "market.py",  # copies core.market.implied_probability into gold.prediction as a
    # comparison baseline; the odds->probability conversion itself lives in conform.py,
    # not here -- this module has no formula of its own (metric-catalog batch 4)
    "parlay.py",  # same-game-parlay joint-probability/EV wagering calculator -- bet
    # payout math, not a baseball statistic (metric-catalog batch 4)
    "portfolio.py",  # fractional-Kelly bankroll/staking allocator -- money-management
    # math, not a baseball statistic (metric-catalog batch 4)
    "nrfi.py",  # NRFI/YRFI fair-odds and recommended-side betting calculator, not a
    # descriptive stat -- its own code comment calls it a "Bucket B exploratory
    # calculator" (metric-catalog batch 4)
}

# Small allow-list of substrings that, if present in `citation`, indicate a
# real, already-elsewhere-cited public source (design.md Decision 2). Not
# exhaustive -- a citation naming a real source this list doesn't recognize
# just doesn't get flagged either way, which is the intended conservative
# behavior for an advisory lint.
PUBLIC_CITATION_MARKERS = (
    "FanGraphs",
    "Baseball-Reference",
    "Tango",
    "Retrosheet",
    "Lahman",
    "Baseball Prospectus",
)

# Substrings that, if present anywhere in a `test_ref` test's source file,
# indicate the test compares against a real externally-sourced value rather
# than one it derives from its own inputs (design.md Decision 3). Reuses the
# same public-source names as PUBLIC_CITATION_MARKERS plus the field/comment
# conventions this project's own tie-out tests already use to name their
# source (e.g. `scripts/verify_baseball_reference_tie_out.py`'s `source_url`).
# Best-effort and advisory only -- a citation-shaped string in a test's
# source is evidence, not proof, that the comparison value itself came from
# that source.
EXTERNAL_FIXTURE_MARKERS = PUBLIC_CITATION_MARKERS + (
    "source_url",
    "tie_out",
    "tie-out",
)


def _formula_path(formula: str) -> str:
    """Strip an optional `::function_name` suffix, leaving the file path."""
    return formula.split("::", 1)[0]


def find_model_files(model_dir: Path = MODEL_DIR) -> list[Path]:
    return sorted(path for path in model_dir.glob("*.py") if path.name not in EXCLUDED_MODULES)


def find_gaps(
    model_files: list[Path], entries: list[MetricEntry], repo_root: Path = REPO_ROOT
) -> list[str]:
    """Return the relative path of every `model_files` entry with no
    catalog entry whose `formula` points at it."""
    covered = {_formula_path(entry.formula) for entry in entries}
    gaps = []
    for path in model_files:
        relative = path.relative_to(repo_root).as_posix()
        if relative not in covered:
            gaps.append(relative)
    return gaps


def lint_visibility(entries: list[MetricEntry]) -> list[str]:
    """Decision-2 lint: citation/visibility mismatches. Advisory only."""
    warnings = []
    for entry in entries:
        looks_public = any(marker in entry.citation for marker in PUBLIC_CITATION_MARKERS)
        if looks_public and entry.visibility == "internal":
            warnings.append(
                f"{entry.name}: citation {entry.citation!r} names a recognized public "
                "source but visibility is 'internal' -- double check this shouldn't be 'public'"
            )
        elif not looks_public and entry.visibility == "public":
            warnings.append(
                f"{entry.name}: visibility is 'public' but citation {entry.citation!r} does not "
                "match a recognized public-source marker -- double check this is really citable"
            )
    return warnings


def check_validated_test_refs(
    entries: list[MetricEntry], repo_root: Path = REPO_ROOT
) -> tuple[list[str], list[str]]:
    """Decision-3 check for every `status: validated` entry.

    Returns `(errors, warnings)`:

    - `errors` (hard-fail, contributes to the exit code): `test_ref`'s file
      does not exist on disk, or resolves outside `repo_root` (an absolute
      path or a `../` escape -- CodeRabbit review, PR #224: an existing file
      outside the repository would otherwise satisfy this check and let a
      `validated` entry bypass the "real, in-repository test" requirement
      entirely) -- the schema already requires `status: validated` to set
      `test_ref` (see `MetricEntry`), so either case means the named test
      cannot be a real, currently-passing one.
    - `warnings` (advisory, never changes the exit code): the named test's
      source file has no recognizable external-fixture marker -- a static,
      best-effort proxy for "this test only hand-derives its own expected
      value" rather than comparing against a real externally-sourced one.
    """
    errors = []
    warnings = []
    resolved_root = repo_root.resolve()
    for entry in entries:
        if entry.status != "validated":
            continue
        test_ref = entry.test_ref
        assert test_ref is not None  # enforced by MetricEntry's own validator
        test_path = (repo_root / test_ref.split("::", 1)[0]).resolve()
        try:
            test_path.relative_to(resolved_root)
        except ValueError:
            errors.append(f"{entry.name}: test_ref {test_ref!r} resolves outside the repository")
            continue
        if not test_path.is_file():
            errors.append(f"{entry.name}: test_ref {test_ref!r} does not exist on disk")
            continue
        source = test_path.read_text(encoding="utf-8")
        if not any(marker in source for marker in EXTERNAL_FIXTURE_MARKERS):
            warnings.append(
                f"{entry.name}: test_ref {test_ref!r} has no recognizable "
                "external-fixture marker -- double check it isn't a self-referential "
                "test that only compares against a value it derives itself"
            )
    return errors, warnings


def main() -> int:
    try:
        entries = load_all(METRICS_DIR)
    except CatalogError as exc:
        print(f"check_metric_catalog: could not load catalog entries -- {exc}")
        return 1

    model_files = find_model_files()
    gaps = find_gaps(model_files, entries)
    visibility_warnings = lint_visibility(entries)
    test_ref_errors, test_ref_warnings = check_validated_test_refs(entries)

    warnings = visibility_warnings + test_ref_warnings
    if warnings:
        print("Advisory lint (does not fail this check):")
        for warning in warnings:
            print(f"  {warning}")
        print()

    if test_ref_errors:
        print("Validated test_ref check: entries with a missing test_ref file:")
        for error in test_ref_errors:
            print(f"  {error}")
        print()

    if gaps:
        print(
            f"Metric catalog completeness: {len(gaps)} of {len(model_files)} "
            "mlb_baseball/model/*.py module(s) have no catalog entry:"
        )
        for gap in gaps:
            print(f"  {gap}")
        print(
            "\nAdd a mlb_baseball/metrics/<name>.yaml entry whose `formula` points at "
            "each file above (or add it to EXCLUDED_MODULES in this script with a reason, "
            "if it is genuinely not a single named statistic)."
        )

    if gaps or test_ref_errors:
        return 1

    print(f"Metric catalog completeness: {len(model_files)} module(s), no gaps.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
