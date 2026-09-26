import pytest
from mlb_research.feature_sets import (
    GAME_WIN_V1,
    FeatureField,
    FeatureSet,
    get_feature_set,
    validate_for_game_win,
)


def test_game_win_v1_is_a_complete_game_feature_allow_list():
    assert GAME_WIN_V1.name == "game-win"
    assert GAME_WIN_V1.version == "v1"
    assert len(GAME_WIN_V1.fields) == 8
    assert all(field.ref.startswith("game:") for field in GAME_WIN_V1.fields)
    assert "game:home_win" not in GAME_WIN_V1.refs
    assert all(field.source_relation == "feat.game" for field in GAME_WIN_V1.fields)
    assert all(field.evidence_ref for field in GAME_WIN_V1.fields)


def test_feature_set_rejects_missing_or_duplicate_contract_fields():
    with pytest.raises(ValueError, match="<view>:<column>"):
        FeatureField(
            "bad-ref", "feature", "game", "feat.game", "before", "NULL", "1910-2025", "test"
        )
    with pytest.raises(ValueError, match="must not be empty"):
        FeatureField("game:x", "feature", "", "feat.game", "before", "NULL", "1910-2025", "test")

    field = FeatureField(
        "game:x", "feature", "game", "feat.game", "before", "NULL", "1910-2025", "test"
    )
    with pytest.raises(ValueError, match="duplicate"):
        FeatureSet("x", "v1", "target", "coverage", (field, field), ("label",))
    with pytest.raises(ValueError, match="exclusions"):
        FeatureSet("x", "v1", "target", "coverage", (field,), ())


def test_feature_set_lookup_is_versioned_and_names_available_sets():
    assert get_feature_set("game-win") is GAME_WIN_V1
    with pytest.raises(ValueError, match="game-win:v1"):
        get_feature_set("unknown")


@pytest.mark.parametrize(
    ("ref", "role", "source_relation"),
    [
        ("game:home_win", "label", "feat.game"),
        ("game:final_score", "postgame", "feat.game"),
        ("game:closing_price", "market", "core.market"),
        ("game:legacy_rate", "legacy", "gold.game_feature"),
    ],
)
def test_game_win_validator_rejects_prohibited_feature_categories(ref, role, source_relation):
    field = FeatureField(ref, role, "game", source_relation, "before", "NULL", "1910-2025", "test")
    feature_set = FeatureSet("bad", "v1", "target", "coverage", (field,), ("label",))

    with pytest.raises(ValueError, match="ineligible game-win feature set"):
        validate_for_game_win(feature_set)
