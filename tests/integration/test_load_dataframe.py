import pandas as pd

from mlb_baseball.load import load_dataframe


def test_creates_table_and_loads_rows(db_conn, drop_tables_after):
    table = drop_tables_after("raw.test_widgets")
    df = pd.DataFrame({"widget_id": [1, 2], "name": ["a", "b"]})

    rowcount = load_dataframe(db_conn, table, df)
    db_conn.commit()

    assert rowcount == 2
    with db_conn.cursor() as cur:
        cur.execute(f"SELECT widget_id, name FROM {table} ORDER BY widget_id")
        assert cur.fetchall() == [("1", "a"), ("2", "b")]


def test_rerunning_truncates_instead_of_duplicating(db_conn, drop_tables_after):
    table = drop_tables_after("raw.test_widgets_rerun")
    df = pd.DataFrame({"widget_id": [1, 2, 3]})

    load_dataframe(db_conn, table, df)
    db_conn.commit()
    load_dataframe(db_conn, table, df)
    db_conn.commit()

    with db_conn.cursor() as cur:
        cur.execute(f"SELECT count(*) FROM {table}")
        assert cur.fetchone() == (3,)


def test_handles_digit_prefixed_and_mixed_case_columns(db_conn, drop_tables_after):
    table = drop_tables_after("raw.test_stat_columns")
    df = pd.DataFrame({"playerID": ["abc01"], "2B": [12], "3B": [3]})

    load_dataframe(db_conn, table, df)
    db_conn.commit()

    with db_conn.cursor() as cur:
        cur.execute(f"SELECT playerid, n2b, n3b FROM {table}")
        assert cur.fetchone() == ("abc01", "12", "3")


def test_handles_reserved_sql_keywords_as_column_names(db_conn, drop_tables_after):
    # Regression test: Retrosheet's parkcode.txt has a column literally named
    # "end", which broke the unquoted CREATE TABLE this function used to
    # generate — found by actually running the reference connector against
    # real data, not by inspection. Covers scope_column too, since it's a
    # separate quoting path in load_dataframe.
    table = drop_tables_after("raw.test_reserved_words")
    df = pd.DataFrame({"start": ["2020"], "end": ["2021"], "select": ["x"]})

    load_dataframe(db_conn, table, df, scope_column="end", scope_value="2021")
    db_conn.commit()

    with db_conn.cursor() as cur:
        cur.execute(f'SELECT "start", "end", "select" FROM {table}')
        assert cur.fetchone() == ("2020", "2021", "x")


def test_scope_column_replaces_only_matching_rows(db_conn, drop_tables_after):
    table = drop_tables_after("raw.test_chunked")

    load_dataframe(
        db_conn,
        table,
        pd.DataFrame({"chunk": ["a"], "v": [1]}),
        scope_column="chunk",
        scope_value="a",
    )
    db_conn.commit()
    load_dataframe(
        db_conn,
        table,
        pd.DataFrame({"chunk": ["b"], "v": [2]}),
        scope_column="chunk",
        scope_value="b",
    )
    db_conn.commit()
    # Reloading chunk "a" must not disturb chunk "b".
    load_dataframe(
        db_conn,
        table,
        pd.DataFrame({"chunk": ["a"], "v": [99]}),
        scope_column="chunk",
        scope_value="a",
    )
    db_conn.commit()

    with db_conn.cursor() as cur:
        cur.execute(f"SELECT chunk, v FROM {table} ORDER BY chunk")
        assert cur.fetchall() == [("a", "99"), ("b", "2")]
