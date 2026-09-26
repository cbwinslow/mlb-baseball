"""Versioned, point-in-time feature-set declarations for public experiments.

The declarations here are deliberately small allow-lists, not a replacement
for the repository metric catalog.  A metric catalog entry explains a formula;
a feature set declares which already-built columns are permitted inputs to one
named experiment.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

FeatureRole = Literal["feature", "label", "metadata", "postgame", "market", "legacy"]


@dataclass(frozen=True)
class FeatureField:
    """One admitted feature and the evidence a researcher needs to use it."""

    ref: str
    role: FeatureRole
    grain: str
    source_relation: str
    availability: str
    null_policy: str
    null_denominator: str
    coverage: str
    evidence_ref: str

    def __post_init__(self) -> None:
        view, separator, column = self.ref.partition(":")
        if not separator or not view or not column:
            raise ValueError("feature ref must be '<view>:<column>'")
        if self.role not in {"feature", "label", "metadata", "postgame", "market", "legacy"}:
            raise ValueError(f"unknown feature role {self.role!r}")
        for field_name in (
            "grain",
            "source_relation",
            "availability",
            "null_policy",
            "null_denominator",
            "coverage",
            "evidence_ref",
        ):
            if not getattr(self, field_name).strip():
                raise ValueError(f"feature field {field_name!r} must not be empty")


@dataclass(frozen=True)
class FeatureSet:
    """A stable, model-specific allow-list of point-in-time feature fields."""

    name: str
    version: str
    target: str
    coverage: str
    coverage_start: int
    coverage_end: int
    fields: tuple[FeatureField, ...]
    exclusions: tuple[str, ...]

    def __post_init__(self) -> None:
        if not self.name or not self.version or not self.target or not self.coverage:
            raise ValueError("feature set name, version, target, and coverage must not be empty")
        if self.coverage_start > self.coverage_end:
            raise ValueError("feature set coverage start must not be after its end")
        if not self.fields:
            raise ValueError("feature set must admit at least one field")
        refs = tuple(field.ref for field in self.fields)
        if len(refs) != len(set(refs)):
            raise ValueError("feature set contains duplicate feature refs")
        if not self.exclusions:
            raise ValueError("feature set must document its exclusions")

    @property
    def refs(self) -> tuple[str, ...]:
        """Feature references accepted by ``get_historical_features``."""
        return tuple(field.ref for field in self.fields)


_GAME_WIN_ADMITTED_REFS = frozenset(
    f"game:{side}_{rate}_30d"
    for side in ("home", "away")
    for rate in ("k_pct", "bb_pct", "obp", "slg")
)


def validate_for_game_win(feature_set: FeatureSet) -> None:
    """Reject fields that cannot be pre-game inputs to the first game-win set.

    Eligibility never rests on the caller-supplied role alone: every field must
    also be one of the team-form columns whose pre-game availability is proven.
    """
    problems: list[str] = []
    for field in feature_set.fields:
        if field.ref not in _GAME_WIN_ADMITTED_REFS:
            problems.append(f"{field.ref}: not an admitted game-win input")
        if field.role != "feature":
            problems.append(f"{field.ref}: role {field.role!r} is not a pre-game feature")
        if field.source_relation == "gold.game_feature":
            problems.append(f"{field.ref}: legacy gold.game_feature is not an admitted source")
        if field.ref == "game:home_win":
            problems.append("game:home_win: outcome labels are never features")
    if problems:
        raise ValueError("ineligible game-win feature set: " + "; ".join(problems))


_TEAM_RATE_EVIDENCE = (
    "tests/integration/test_feat_form.py::test_feat_game_form_columns_match_manual_rollup"
)
_TEAM_RATE_AVAILABILITY = (
    "Entering 30-day regular-season team form; the entire entering calendar day is excluded."
)
_TEAM_RATE_COVERAGE = "Regular season, 1910-2025 where feat.game has a Retrosheet game key."


def _team_rate_field(column: str, denominator: str, null_policy: str) -> FeatureField:
    return FeatureField(
        ref=f"game:{column}",
        role="feature",
        grain="game",
        source_relation="feat.game",
        availability=_TEAM_RATE_AVAILABILITY,
        null_policy=null_policy,
        null_denominator=denominator,
        coverage=_TEAM_RATE_COVERAGE,
        evidence_ref=_TEAM_RATE_EVIDENCE,
    )


GAME_WIN_V1 = FeatureSet(
    name="game-win",
    version="v1",
    target="Pre-game home-win probability",
    coverage="Regular-season games with feat.game coverage, 1910-2025.",
    coverage_start=1910,
    coverage_end=2025,
    fields=(
        _team_rate_field("home_k_pct_30d", "home_pa_30d", "NULL when prior 30-day PA is 0."),
        _team_rate_field("away_k_pct_30d", "away_pa_30d", "NULL when prior 30-day PA is 0."),
        _team_rate_field("home_bb_pct_30d", "home_pa_30d", "NULL when prior 30-day PA is 0."),
        _team_rate_field("away_bb_pct_30d", "away_pa_30d", "NULL when prior 30-day PA is 0."),
        _team_rate_field(
            "home_obp_30d",
            "home_obp_denom_30d",
            "NULL when prior 30-day AB + BB + HBP + SF is 0.",
        ),
        _team_rate_field(
            "away_obp_30d",
            "away_obp_denom_30d",
            "NULL when prior 30-day AB + BB + HBP + SF is 0.",
        ),
        _team_rate_field("home_slg_30d", "home_ab_30d", "NULL when prior 30-day AB is 0."),
        _team_rate_field("away_slg_30d", "away_ab_30d", "NULL when prior 30-day AB is 0."),
    ),
    exclusions=(
        "home_win is the outcome label, never a feature.",
        "Game identifiers, season, and feature clocks are metadata, not features.",
        "Actual-starter columns are excluded until historical probable-starter "
        "availability is proven.",
        "gold.game_feature compatibility columns and market outcomes are not this feature set.",
    ),
)

_FEATURE_SETS = {(GAME_WIN_V1.name, GAME_WIN_V1.version): GAME_WIN_V1}


def get_feature_set(name: str, version: str = "v1") -> FeatureSet:
    """Return a declared feature set or name the available versions."""
    try:
        return _FEATURE_SETS[(name, version)]
    except KeyError as exc:
        available = ", ".join(f"{key[0]}:{key[1]}" for key in sorted(_FEATURE_SETS))
        raise ValueError(f"unknown feature set {name}:{version}; available: {available}") from exc


validate_for_game_win(GAME_WIN_V1)


__all__ = [
    "FeatureField",
    "FeatureRole",
    "FeatureSet",
    "GAME_WIN_V1",
    "get_feature_set",
    "validate_for_game_win",
]
