from mlb_baseball.connectors.bref import _repair_name_mojibake


def test_repairs_a_real_mangled_name():
    # Reproduced directly from pybaseball.batting_stats_bref(2023): the real
    # UTF-8 bytes for "Jos\xc3\xa9 Abreu" (b'Jos\xc3\xa9 Abreu') pass through
    # pybaseball's own str(bytes).encode() bug and land here as this exact
    # 17-character literal string (see issue #6 / bref.py's module docstring
    # on _repair_name_mojibake for the full mechanism).
    assert _repair_name_mojibake("Jos\\xc3\\xa9 Abreu") == "José Abreu"


def test_leaves_a_plain_ascii_name_unchanged():
    assert _repair_name_mojibake("Mike Trout") == "Mike Trout"


def test_leaves_non_string_values_unchanged():
    assert _repair_name_mojibake(None) is None


def test_leaves_a_name_with_no_escape_sequence_unchanged_even_with_backslashes():
    # Guards the "\\x" substring check itself: a name with a literal
    # backslash but no hex-escape shouldn't be touched or raise.
    assert _repair_name_mojibake("O'Brien\\Smith") == "O'Brien\\Smith"


def test_leaves_an_unrecoverable_escape_sequence_unchanged_instead_of_raising():
    # \xff is not valid as a standalone UTF-8 continuation byte -- the final
    # decode('utf-8') would raise; the function must fall back to returning
    # the input as-is rather than crashing the whole load.
    assert _repair_name_mojibake("bad\\xffname") == "bad\\xffname"
