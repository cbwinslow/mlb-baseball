"""Data-rights profiles enforced before connector work begins.

Profiles classify permissions for this project, not universal legal conclusions.
``public_safe`` is deliberately small and fail-closed: a source enters it only
after the project records evidence for public display, commercial use, and ML.
``licensed_full`` contains only sources covered by a documented license; no
current paid/partner feed is silently treated as licensed.  ``local_research``
is for owner-controlled research only and must never be used to create public
artifacts without a lineage review.
"""

from __future__ import annotations

import os
from collections.abc import Iterable

PUBLIC_SAFE = frozenset(
    {
        "retrosheet",
        "retrosheet_box",
        "retrosheet_event",
        "retrosheet_gamelog",
        "retrosheet_reference",
        "retrosheet_roster",
        "retrosheet_schedule",
        "retrosheet_transaction",
    }
)

PROFILES = frozenset({"public_safe", "licensed_full", "local_research"})


class SourceProfileError(ValueError):
    """A source is outside the selected data-rights profile."""


def active_profile() -> str:
    profile = os.environ.get("MLB_DATA_PROFILE", "local_research")
    if profile not in PROFILES:
        raise SourceProfileError(
            f"Unknown MLB_DATA_PROFILE={profile!r}; choose one of {sorted(PROFILES)}"
        )
    return profile


def allowed_sources(profile: str, all_sources: Iterable[str]) -> set[str]:
    if profile not in PROFILES:
        raise SourceProfileError(f"Unknown source profile {profile!r}")
    available = set(all_sources)
    if profile == "local_research":
        return available
    # No separate licensed feed has been approved yet, so licensed_full is
    # intentionally no broader than public_safe rather than a misleading alias
    # for local research.
    return available & PUBLIC_SAFE


def require_sources(profile: str, sources: Iterable[str], *, purpose: str) -> None:
    """Fail before restricted data is ingested or used for a public artifact."""
    requested = set(sources)
    allowed = allowed_sources(profile, requested)
    forbidden = sorted(requested - allowed)
    if forbidden:
        raise SourceProfileError(
            f"{purpose} is forbidden by the {profile} data profile: "
            f"{', '.join(forbidden)}. See docs/SOURCE_RIGHTS.md."
        )
