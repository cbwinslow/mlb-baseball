from mlb_baseball.connectors.retrosheet_gamelog import GAMELOG_FIELDS


def test_field_count_matches_documented_layout():
    assert len(GAMELOG_FIELDS) == 161


def test_field_names_are_unique():
    assert len(GAMELOG_FIELDS) == len(set(GAMELOG_FIELDS))


def test_known_field_positions_match_the_documented_layout():
    # Spot-checked against retrosheet.org/gamelogs/glfields.txt and verified
    # against real downloaded data (see connector module docstring).
    assert GAMELOG_FIELDS[0] == "date"
    assert GAMELOG_FIELDS[3] == "v_team"  # field 4
    assert GAMELOG_FIELDS[9] == "v_score"  # field 10
    assert GAMELOG_FIELDS[16] == "park_id"  # field 17
    assert GAMELOG_FIELDS[159] == "additional_info"  # field 160
    assert GAMELOG_FIELDS[160] == "acquisition_info"  # field 161
