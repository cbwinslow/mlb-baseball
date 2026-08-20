"""Unit coverage for scripts/lint_sql_ownership.py's pure AST-inspection
logic -- not a package, so loaded directly by path (same pattern as
tests/unit/test_verify_markov_calibration.py, the existing precedent for
testing a scripts/*.py file's real logic in isolation)."""

import importlib.util
from pathlib import Path

_SCRIPT_PATH = Path(__file__).parents[2] / "scripts" / "lint_sql_ownership.py"
_spec = importlib.util.spec_from_file_location("lint_sql_ownership", _SCRIPT_PATH)
assert _spec is not None and _spec.loader is not None
lint_sql_ownership = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(lint_sql_ownership)

check_file = lint_sql_ownership.check_file


def _write(tmp_path: Path, source: str) -> Path:
    path = tmp_path / "module.py"
    path.write_text(source)
    return path


def test_flags_multiline_insert_into_core(tmp_path):
    path = _write(
        tmp_path,
        'cur.execute(\n    """\n    INSERT INTO core.game (id)\n    VALUES (%s)\n    """\n)\n',
    )
    findings = check_file(path, "module.py")
    assert len(findings) == 1
    assert "module.py:1" in findings[0]


def test_flags_multiline_update_gold(tmp_path):
    path = _write(
        tmp_path,
        'cur.execute(\n    """\n    UPDATE gold.game_feature\n    SET home_win = %s\n    """\n)\n',
    )
    assert len(check_file(path, "module.py")) == 1


def test_flags_multiline_delete_from_core(tmp_path):
    path = _write(
        tmp_path,
        'cur.execute(\n    """\n    DELETE FROM core.game\n    WHERE id = %s\n    """\n)\n',
    )
    assert len(check_file(path, "module.py")) == 1


def test_does_not_flag_single_line_mutation(tmp_path):
    # A one-line operational/diagnostic statement, not a business mutation
    # worth its own .sql resource -- matches docs/SQL_OWNERSHIP.md's
    # "Parameterized operational statements and doctor/inventory
    # diagnostics" staying inline.
    path = _write(tmp_path, 'cur.execute("DELETE FROM core.game WHERE id = %s", (game_id,))\n')
    assert check_file(path, "module.py") == []


def test_does_not_flag_multiline_select(tmp_path):
    path = _write(
        tmp_path,
        'cur.execute(\n    """\n    SELECT id FROM core.game\n    WHERE season = %s\n    """\n)\n',
    )
    assert check_file(path, "module.py") == []


def test_does_not_flag_a_dynamically_composed_fstring(tmp_path):
    # f-strings/`.format()` are dynamic identifier composition, which
    # docs/SQL_OWNERSHIP.md's "Retain in Python" explicitly allows to stay
    # inline (parameterized queries can't bind identifiers at all).
    path = _write(
        tmp_path,
        'cur.execute(\n    f"""\n    INSERT INTO core.{table}\n    VALUES (%s)\n    """\n)\n',
    )
    assert check_file(path, "module.py") == []


def test_does_not_flag_a_mutation_outside_core_or_gold(tmp_path):
    path = _write(
        tmp_path,
        'cur.execute(\n    """\n    INSERT INTO raw.mlb_schedule (id)\n'
        '    VALUES (%s)\n    """\n)\n',
    )
    assert check_file(path, "module.py") == []


def test_allow_comment_on_the_line_above_suppresses_the_finding(tmp_path):
    path = _write(
        tmp_path,
        "# sql-ownership: allow -- reviewed, procedural per docs/SQL_OWNERSHIP.md\n"
        'cur.execute(\n    """\n    INSERT INTO core.game (id)\n    VALUES (%s)\n    """\n)\n',
    )
    assert check_file(path, "module.py") == []


def test_allow_comment_elsewhere_in_the_file_does_not_suppress_it(tmp_path):
    # The comment must be immediately above the flagged call, not just
    # present anywhere in the file -- otherwise one allow comment would
    # silently blanket-exempt the whole module.
    path = _write(
        tmp_path,
        "# sql-ownership: allow -- unrelated\n"
        "x = 1\n"
        'cur.execute(\n    """\n    INSERT INTO core.game (id)\n    VALUES (%s)\n    """\n)\n',
    )
    assert len(check_file(path, "module.py")) == 1
