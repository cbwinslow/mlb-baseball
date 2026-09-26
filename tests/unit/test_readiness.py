"""Unit coverage for the reusable, read-only feature readiness evaluator."""

from __future__ import annotations

import json
from pathlib import Path

import duckdb
from mlb_research.feature_sets import GAME_WIN_V1, FeatureField, FeatureSet
from mlb_research.leakage_checks import CheckResult

from mlb_baseball.health import Check
from mlb_baseball.readiness import (
    ReadinessCheck,
    ReadinessReport,
    evaluate_feature_set,
    profile_feature_coverage,
)


def _coverage_feature_set() -> FeatureSet:
    field = FeatureField(
        "game:rate",
        "feature",
        "game",
        "feat.game",
        "pre-game",
        "NULL exactly when denominator is zero.",
        "denom",
        "1910-2025",
        "test fixture",
    )
    return FeatureSet("coverage", "v1", "test", "1910-2025", 1910, 2025, (field,), ("label",))


def test_missing_feature_artifact_is_a_named_blocker(tmp_path: Path) -> None:
    report = evaluate_feature_set(
        artifact=tmp_path / "missing.duckdb",
        feature_set=GAME_WIN_V1,
        feature_version="v1",
        backbone_tie_out=lambda: Check("backbone_tie_out", True, "passed"),
    )

    assert report.status == "not_ready"
    assert [check.name for check in report.blockers] == ["feature_artifact"]


def test_failed_required_check_is_reported_as_a_named_blocker(monkeypatch, tmp_path: Path) -> None:
    artifact = tmp_path / "feature.duckdb"
    artifact.touch()
    monkeypatch.setattr(
        "mlb_baseball.readiness._declared_columns_check",
        lambda *_: ReadinessCheck("declared_columns", True, "present"),
    )
    monkeypatch.setattr(
        "mlb_baseball.readiness.health_check",
        lambda _: [Check("feat.game grain", False, "duplicate game keys")],
    )
    monkeypatch.setattr(
        "mlb_baseball.readiness.run_leakage_checks",
        lambda *_args, **_kwargs: [CheckResult("clock_consistency", True, "passed")],
    )
    monkeypatch.setattr("mlb_baseball.readiness.profile_feature_coverage", lambda *_: ())

    report = evaluate_feature_set(
        artifact=artifact,
        feature_set=GAME_WIN_V1,
        feature_version="v1",
        backbone_tie_out=lambda: Check("backbone_tie_out", True, "passed"),
    )

    assert report.status == "not_ready"
    assert ("feature_integrity/feat.game grain", "duplicate game keys") in [
        (check.name, check.detail) for check in report.blockers
    ]


def test_json_representation_redacts_artifact_path() -> None:
    report = ReadinessReport(
        "game-win",
        "v1",
        Path("/private/researcher/mlb.duckdb"),
        (ReadinessCheck("check", True, "passed"),),
    )

    payload = report.to_dict()
    assert payload == {
        "schema_version": "v1",
        "status": "ready",
        "feature_set": {"name": "game-win", "version": "v1"},
        "artifact": {"name": "mlb.duckdb"},
        "checks": [{"name": "check", "ok": True, "detail": "passed"}],
        "blockers": [],
        "coverage": [],
    }
    assert "/private" not in json.dumps(payload)


def test_coverage_profile_distinguishes_expected_unexplained_and_excluded_nulls(
    tmp_path: Path,
) -> None:
    artifact = tmp_path / "coverage.duckdb"
    con = duckdb.connect(artifact)
    try:
        con.execute("CREATE SCHEMA feat")
        con.execute(
            "CREATE TABLE feat.game "
            "(season INTEGER, feature_version VARCHAR, rate DOUBLE, denom INTEGER)"
        )
        con.execute(
            "INSERT INTO feat.game VALUES "
            "(1910, 'v1', NULL, 0), (1911, 'v1', NULL, 5), (2026, 'v1', NULL, 5)"
        )
    finally:
        con.close()

    coverage = profile_feature_coverage(artifact, _coverage_feature_set(), "v1")

    assert [
        (row.season, row.expected_null_rows, row.unexplained_null_rows) for row in coverage
    ] == [
        (1910, 1, 0),
        (1911, 0, 1),
        (2026, 0, 0),
    ]
    assert coverage[-1].excluded_rows == 1
