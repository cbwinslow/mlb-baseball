"""Pure string-processing tests -- no database. Regression coverage for a
real bug: migration 0038's own explanatory comment contained a semicolon
in a plain English sentence, and the old naive `sql.split(";")` treated
it as a statement boundary, producing a confusing "syntax error near
<comment fragment>" that gave no hint the real problem was
comment-unaware splitting."""

from mlb_baseball.migrate import _strip_sql_comments


def test_strips_trailing_comment_on_a_statement_line():
    sql = "CREATE INDEX foo ON bar (baz); -- an index"
    assert _strip_sql_comments(sql) == "CREATE INDEX foo ON bar (baz); "


def test_removes_a_semicolon_hidden_inside_a_comment():
    # The exact real failure: a comment sentence containing "; " was
    # previously split into a bogus second "statement".
    sql = "-- first do X; then do Y\nCREATE INDEX foo ON bar (baz);"
    stripped = _strip_sql_comments(sql)
    statements = [s.strip() for s in stripped.split(";") if s.strip()]
    assert statements == ["CREATE INDEX foo ON bar (baz)"]


def test_a_whole_comment_only_line_becomes_empty():
    sql = "-- mlb:nontransactional\nCREATE INDEX foo ON bar (baz);"
    stripped = _strip_sql_comments(sql)
    statements = [s.strip() for s in stripped.split(";") if s.strip()]
    assert statements == ["CREATE INDEX foo ON bar (baz)"]


def test_preserves_multiple_real_statements():
    sql = "CREATE INDEX a ON t (x); -- first\nCREATE INDEX b ON t (y); -- second"
    stripped = _strip_sql_comments(sql)
    statements = [s.strip() for s in stripped.split(";") if s.strip()]
    assert statements == ["CREATE INDEX a ON t (x)", "CREATE INDEX b ON t (y)"]
