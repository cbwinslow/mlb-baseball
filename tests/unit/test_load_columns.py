from mlb_baseball.load import _pg_column_name


def test_lowercases_and_strips_mixed_case():
    assert _pg_column_name("playerID") == "playerid"


def test_prefixes_names_starting_with_a_digit():
    assert _pg_column_name("2B") == "n2b"
    assert _pg_column_name("3B") == "n3b"


def test_replaces_non_alphanumeric_characters():
    assert _pg_column_name("G_batting") == "g_batting"
