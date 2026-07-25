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
