"""Read-only evidence gates for versioned research feature sets.

This module composes checks that already protect the feature store into a
portable, model-admission report.  It deliberately does not build features,
ingest data, or write to PostgreSQL: callers must name an existing DuckDB
artifact and provide explicit backbone tie-out evidence.
"""

from __future__ import annotations

import os
import subprocess
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import duckdb
from mlb_research.feature_sets import FeatureSet, validate_for_game_win
from mlb_research.leakage_checks import CheckResult
from mlb_research.leakage_checks import run_all as run_leakage_checks

from mlb_baseball.feat import _quote, health_check
from mlb_baseball.health import Check

TieOutRunner = Callable[[], Check]
FeatureSetValidator = Callable[[FeatureSet], None]


@dataclass(frozen=True)
class ReadinessCheck:
    """One required piece of evidence for a feature-set admission decision."""

    name: str
    ok: bool
    detail: str


@dataclass(frozen=True)
class FeatureCoverage:
    """Observed seasonal coverage and null-policy evidence for one field."""

    ref: str
    season: int | None
    rows: int
    in_window_rows: int
    excluded_rows: int
    null_rows: int
    expected_null_rows: int
    unexplained_null_rows: int


@dataclass(frozen=True)
class ReadinessReport:
    """Stable, read-only result for one declared feature set and artifact."""

    feature_set: str
    feature_version: str
    artifact: Path
    checks: tuple[ReadinessCheck, ...]
    coverage: tuple[FeatureCoverage, ...] = ()

    @property
    def ready(self) -> bool:
        """Whether every required admission check passed."""
        return all(check.ok for check in self.checks)

    @property
    def status(self) -> str:
        """Machine-readable admission decision."""
        return "ready" if self.ready else "not_ready"

    @property
    def blockers(self) -> tuple[ReadinessCheck, ...]:
        """Every named failed requirement, preserving evaluation order."""
        return tuple(check for check in self.checks if not check.ok)

    def to_dict(self) -> dict[str, object]:
        """Return the stable, secret-safe JSON representation of this report."""
        return {
            "schema_version": "v1",
            "status": self.status,
            "feature_set": {"name": self.feature_set, "version": self.feature_version},
            # An absolute path often exposes a username or machine layout.  The
            # basename identifies the supplied build without serializing that.
            "artifact": {"name": self.artifact.name},
            "checks": [
                {"name": check.name, "ok": check.ok, "detail": check.detail}
                for check in self.checks
            ],
            "blockers": [check.name for check in self.blockers],
            "coverage": [
                {
                    "ref": item.ref,
                    "season": item.season,
                    "rows": item.rows,
                    "in_window_rows": item.in_window_rows,
                    "excluded_rows": item.excluded_rows,
                    "null_rows": item.null_rows,
                    "expected_null_rows": item.expected_null_rows,
                    "unexplained_null_rows": item.unexplained_null_rows,
                }
                for item in self.coverage
            ],
        }


def run_backbone_tie_out(*, database_url: str, script_path: Path | None = None) -> Check:
    """Run the existing cited backbone gate against one explicit database URL.

    The URL is passed only to the child process environment and is never
    included in the returned detail, so callers can safely serialize reports.
    """
    if not database_url.strip():
        return Check("backbone_tie_out", False, "an explicit database URL is required")
    script = (
        script_path
        or Path(__file__).resolve().parent.parent
        / "scripts"
        / "verify_baseball_reference_tie_out.py"
    )
    proc = subprocess.run(
        [sys.executable, str(script)],
        check=False,
        capture_output=True,
        text=True,
        env={**os.environ, "DATABASE_URL": database_url},
    )
    if proc.returncode == 0:
        return Check("backbone_tie_out", True, "Baseball-Reference backbone tie-out passed")
    detail = proc.stderr.strip().splitlines()[-1] if proc.stderr.strip() else "tie-out failed"
    detail = detail.replace(database_url, "<redacted>")
    return Check("backbone_tie_out", False, f"Baseball-Reference backbone tie-out failed: {detail}")


def _declared_columns_check(path: Path, feature_set: FeatureSet) -> ReadinessCheck:
    """Check that every declared field exists in its declared ``feat`` relation."""
    con = duckdb.connect()
    try:
        con.execute(f"ATTACH '{_quote(str(path))}' AS readiness_artifact (READ_ONLY)")
        con.execute("USE readiness_artifact")
        missing: list[str] = []
        for field in feature_set.fields:
            schema, _, table = field.source_relation.partition(".")
            _, _, column = field.ref.partition(":")
            columns = {
                row[0]
                for row in con.execute(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_schema = ? AND table_name = ?",
                    [schema, table],
                ).fetchall()
            }
            if column not in columns:
                missing.append(f"{field.source_relation}.{column}")
    except (duckdb.Error, OSError) as exc:
        detail = str(exc).replace(str(path), path.name)
        return ReadinessCheck(
            "declared_columns", False, f"cannot inspect feature artifact: {detail}"
        )
    finally:
        con.close()
    if missing:
        return ReadinessCheck(
            "declared_columns", False, "missing declared columns: " + ", ".join(missing)
        )
    return ReadinessCheck("declared_columns", True, "all declared feature columns are present")


def _as_readiness_check(
    prefix: str, check: Check | CheckResult, *, artifact: Path | None = None
) -> ReadinessCheck:
    detail = check.detail
    if artifact is not None:
        detail = detail.replace(str(artifact), artifact.name)
    return ReadinessCheck(f"{prefix}/{check.name}", check.ok, detail)


def _identifier(value: str) -> str:
    if not value.isidentifier():
        raise ValueError(f"unsupported feature relation identifier {value!r}")
    return f'"{value}"'


def profile_feature_coverage(
    path: Path, feature_set: FeatureSet, feature_version: str
) -> tuple[FeatureCoverage, ...]:
    """Measure declared-field coverage without assigning a universal threshold.

    A null is expected only when its declaration's audit denominator is zero.
    Rows outside the feature set's explicit coverage years are reported but do
    not block admission; this makes an intentional era boundary visible.
    """
    con = duckdb.connect()
    observations: list[FeatureCoverage] = []
    try:
        con.execute(f"ATTACH '{_quote(str(path))}' AS readiness_artifact (READ_ONLY)")
        for field in feature_set.fields:
            schema, _, table = field.source_relation.partition(".")
            _, _, column = field.ref.partition(":")
            relation = f"{_identifier(schema)}.{_identifier(table)}"
            rate = _identifier(column)
            denominator = _identifier(field.null_denominator)
            rows = con.execute(
                f"""
                SELECT
                    season,
                    count(*) AS rows,
                    count(*) FILTER (WHERE season BETWEEN ? AND ?) AS in_window_rows,
                    count(*) FILTER (WHERE season IS NULL OR season NOT BETWEEN ? AND ?)
                        AS excluded_rows,
                    count(*) FILTER (WHERE {rate} IS NULL) AS null_rows,
                    count(*) FILTER (
                        WHERE season BETWEEN ? AND ? AND {rate} IS NULL AND {denominator} = 0
                    ) AS expected_null_rows,
                    count(*) FILTER (
                        WHERE season BETWEEN ? AND ? AND {rate} IS NULL
                          AND {denominator} IS DISTINCT FROM 0
                    ) AS unexplained_null_rows
                FROM readiness_artifact.{relation}
                WHERE feature_version = ?
                GROUP BY season
                ORDER BY season
                """,
                [
                    feature_set.coverage_start,
                    feature_set.coverage_end,
                    feature_set.coverage_start,
                    feature_set.coverage_end,
                    feature_set.coverage_start,
                    feature_set.coverage_end,
                    feature_set.coverage_start,
                    feature_set.coverage_end,
                    feature_version,
                ],
            ).fetchall()
            observations.extend(
                FeatureCoverage(
                    ref=field.ref,
                    season=row[0],
                    rows=int(row[1]),
                    in_window_rows=int(row[2]),
                    excluded_rows=int(row[3]),
                    null_rows=int(row[4]),
                    expected_null_rows=int(row[5]),
                    unexplained_null_rows=int(row[6]),
                )
                for row in rows
            )
    finally:
        con.close()
    return tuple(observations)


def evaluate_feature_set(
    *,
    artifact: str | os.PathLike[str],
    feature_set: FeatureSet,
    feature_version: str,
    backbone_tie_out: TieOutRunner | None = None,
    validator: FeatureSetValidator = validate_for_game_win,
) -> ReadinessReport:
    """Evaluate one explicit feature artifact without modifying any data.

    ``backbone_tie_out`` is intentionally supplied by the caller.  Omitting it
    is a failed requirement, preventing a readiness claim based only on a
    local DuckDB file.  Future feature families may supply their own
    declaration validator while reusing the same report/check contract.
    """
    path = Path(artifact).expanduser()
    checks: list[ReadinessCheck] = []
    try:
        validator(feature_set)
    except ValueError as exc:
        checks.append(ReadinessCheck("feature_admission", False, str(exc)))
    else:
        checks.append(
            ReadinessCheck("feature_admission", True, "declared feature set is admissible")
        )

    if not path.exists():
        checks.append(
            ReadinessCheck("feature_artifact", False, f"no DuckDB feature build at {path.name}")
        )
        return ReadinessReport(feature_set.name, feature_version, path, tuple(checks))

    checks.append(ReadinessCheck("feature_artifact", True, f"using explicit artifact {path.name}"))
    checks.append(_declared_columns_check(path, feature_set))
    try:
        coverage = profile_feature_coverage(path, feature_set, feature_version)
    except (duckdb.Error, OSError, ValueError) as exc:
        coverage = ()
        detail = str(exc).replace(str(path), path.name)
        checks.append(
            ReadinessCheck("feature_coverage", False, f"cannot profile coverage: {detail}")
        )
    else:
        missing_coverage = sorted(
            field.ref
            for field in feature_set.fields
            if not any(item.ref == field.ref and item.in_window_rows for item in coverage)
        )
        unexplained = sum(item.unexplained_null_rows for item in coverage)
        checks.append(
            ReadinessCheck(
                "feature_coverage",
                not missing_coverage,
                "all declared fields have rows in their coverage window"
                if not missing_coverage
                else "no in-window rows for: " + ", ".join(missing_coverage),
            )
        )
        checks.append(
            ReadinessCheck(
                "feature_null_policy",
                unexplained == 0,
                "all observed nulls match declared denominator policies"
                if unexplained == 0
                else f"{unexplained} unexplained in-window null(s)",
            )
        )
    for check in health_check(path):
        checks.append(_as_readiness_check("feature_integrity", check, artifact=path))
    try:
        leakage_results = run_leakage_checks(path, feature_version=feature_version)
    except (duckdb.Error, FileNotFoundError, OSError) as exc:
        detail = str(exc).replace(str(path), path.name)
        checks.append(
            ReadinessCheck("feature_leakage", False, f"cannot run leakage checks: {detail}")
        )
    else:
        checks.extend(
            _as_readiness_check("feature_leakage", check, artifact=path)
            for check in leakage_results
        )

    if backbone_tie_out is None:
        checks.append(
            ReadinessCheck("backbone_tie_out", False, "tie-out evidence was not supplied")
        )
    else:
        checks.append(_as_readiness_check("backbone", backbone_tie_out()))
    return ReadinessReport(feature_set.name, feature_version, path, tuple(checks), coverage)


__all__ = [
    "ReadinessCheck",
    "ReadinessReport",
    "FeatureCoverage",
    "evaluate_feature_set",
    "profile_feature_coverage",
    "run_backbone_tie_out",
]
