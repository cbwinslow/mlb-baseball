"""Standing rights guard for the fangraphs-conform Beat 1 relations (ADR-290).

FanGraphs is `local_research` only (docs/SOURCE_RIGHTS.md, ADR-288): the two
derived lookups `gold.fangraphs_guts` / `gold.fangraphs_park_factors` inherit
that posture and must never be marked `public_safe` in the export registry, nor
may `require_sources` ever admit `fangraphs` under a non-`local_research`
profile. Neither relation is added to `export.RELATIONS` by this change -- this
test is a guard against a future one doing so.

`mlb_baseball/serve.py` has no relation registry (only per-endpoint query
functions), so `export.RELATIONS` is the only allow-list to guard here.
"""

import pytest

from mlb_baseball import export
from mlb_baseball.source_profiles import SourceProfileError, require_sources


def test_no_fangraphs_relation_is_public_safe_in_the_export_registry():
    offenders = [
        r.qualified_name
        for r in export.RELATIONS
        if r.qualified_name.startswith("gold.fangraphs_") and r.profile == "public_safe"
    ]
    assert offenders == [], (
        f"FanGraphs-derived relations must never be public_safe: {offenders}. "
        "FanGraphs is local_research only (ADR-288 / ADR-290)."
    )


def test_no_fangraphs_relation_ships_in_the_backbone_publish_preset():
    # delivery-surface publish preset is a separate rights gate; make sure a
    # gold.fangraphs_* relation can never leak through it either.
    leaked = [name for name in export.BACKBONE_CANDIDATES if name.startswith("gold.fangraphs_")]
    assert leaked == []


def test_require_sources_rejects_fangraphs_under_public_safe():
    with pytest.raises(SourceProfileError) as excinfo:
        require_sources("public_safe", ["fangraphs"], purpose="test")
    assert "fangraphs" in str(excinfo.value)
    assert "docs/SOURCE_RIGHTS.md" in str(excinfo.value)


def test_require_sources_admits_fangraphs_only_under_local_research():
    # local_research is the one profile that may touch FanGraphs-derived data.
    require_sources("local_research", ["fangraphs"], purpose="test")
    with pytest.raises(SourceProfileError):
        require_sources("licensed_full", ["fangraphs"], purpose="test")
