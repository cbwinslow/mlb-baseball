import pandas as pd
import pytest

from mlb_baseball.load import (
    SchemaDriftError,
    SchemaDriftWarning,
    append_dataframe,
    load_dataframe,
    replace_dataframe_scopes,
)


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


def test_later_load_with_extra_columns_alters_the_table_instead_of_failing(
    db_conn, drop_tables_after
):
    # Regression: a real bootstrap crashed on "column ... does not exist"
    # because a later year's DataFrame (retrosheet_box.py, cwbox XML output)
    # had a column ("umpire_lf") an earlier year's didn't — some historical
    # games have extra umpire positions others don't. The table's schema,
    # fixed from the first call, must grow to accommodate later columns
    # rather than fail on COPY.
    table = drop_tables_after("raw.test_evolving_schema")
    df1 = pd.DataFrame({"game_id": ["G1"], "umpire_hp": ["ump1"], "_scope": ["a"]})
    load_dataframe(db_conn, table, df1, scope_column="_scope", scope_value="a")
    db_conn.commit()

    df2 = pd.DataFrame(
        {"game_id": ["G2"], "umpire_hp": ["ump2"], "umpire_lf": ["ump3"], "_scope": ["b"]}
    )
    with pytest.warns(SchemaDriftWarning, match="added=.*umpire_lf"):
        load_dataframe(db_conn, table, df2, scope_column="_scope", scope_value="b")
    db_conn.commit()

    with db_conn.cursor() as cur:
        cur.execute(f"SELECT game_id, umpire_hp, umpire_lf FROM {table} ORDER BY game_id")
        assert cur.fetchall() == [("G1", "ump1", None), ("G2", "ump2", "ump3")]


def test_schema_drift_error_preserves_existing_raw_contract(db_conn, drop_tables_after):
    table = drop_tables_after("raw.test_schema_drift")
    load_dataframe(db_conn, table, pd.DataFrame({"stable": ["one"]}))
    db_conn.commit()

    with pytest.raises(SchemaDriftError, match=r"added=\['unexpected'\]"):
        load_dataframe(
            db_conn,
            table,
            pd.DataFrame({"stable": ["two"], "unexpected": ["new"]}),
            schema_drift_policy="error",
        )

    with db_conn.cursor() as cur:
        cur.execute(f"SELECT stable FROM {table}")
        assert cur.fetchall() == [("one",)]


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


def test_scope_column_creates_an_index_so_deletes_stay_cheap_at_scale(db_conn, drop_tables_after):
    # Regression test: without an index on scope_column, every per-chunk DELETE
    # is a full sequential scan — fine on a small table, but on Retrosheet's
    # multi-million-row raw.retrosheet_plays it made bootstrap() look "stuck"
    # partway through (it wasn't; the DELETE was just getting slower every
    # year as the table grew). Found by watching a real bootstrap run, not by
    # inspection.
    table = drop_tables_after("raw.test_indexed_chunks")

    load_dataframe(
        db_conn,
        table,
        pd.DataFrame({"chunk": ["a"], "v": [1]}),
        scope_column="chunk",
        scope_value="a",
    )
    db_conn.commit()

    table_name = table.split(".")[-1]
    with db_conn.cursor() as cur:
        cur.execute(
            "SELECT indexdef FROM pg_indexes WHERE schemaname = 'raw' AND tablename = %s",
            (table_name,),
        )
        indexes = [row[0] for row in cur.fetchall()]

    assert any("chunk" in idx for idx in indexes), indexes


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


def test_bulk_scope_replace_is_idempotent_and_clears_empty_successes(db_conn, drop_tables_after):
    table = drop_tables_after("raw.test_bulk_chunks")
    load_dataframe(
        db_conn,
        table,
        pd.DataFrame({"game_pk": ["one", "two"], "value": ["old", "old"]}),
        scope_column="game_pk",
        scope_value="one",
    )
    load_dataframe(
        db_conn,
        table,
        pd.DataFrame({"game_pk": ["two"], "value": ["old"]}),
        scope_column="game_pk",
        scope_value="two",
    )
    db_conn.commit()

    replace_dataframe_scopes(
        db_conn,
        table,
        pd.DataFrame({"game_pk": ["one"], "value": ["new"]}),
        scope_column="game_pk",
        scope_values=["one", "two"],
    )
    db_conn.commit()

    with db_conn.cursor() as cur:
        cur.execute(f"SELECT game_pk, value FROM {table} ORDER BY game_pk")
        assert cur.fetchall() == [("one", "new")]


def test_append_dataframe_creates_table_and_inserts_rows(db_conn, drop_tables_after):
    table = drop_tables_after("raw.test_append_widgets")
    df = pd.DataFrame({"widget_id": [1, 2], "name": ["a", "b"]})

    rowcount = append_dataframe(db_conn, table, df, identity_columns=("widget_id",))
    db_conn.commit()

    assert rowcount == 2
    with db_conn.cursor() as cur:
        cur.execute(f"SELECT widget_id, name FROM {table} ORDER BY widget_id")
        assert cur.fetchall() == [("1", "a"), ("2", "b")]


def test_append_dataframe_accumulates_instead_of_replacing(db_conn, drop_tables_after):
    # The whole point of append_dataframe vs. load_dataframe: every previous
    # call's rows stay — this is for genuinely event-stream data (e.g. a
    # live-game snapshot captured repeatedly) where the "chunk replaces
    # chunk" model of load_dataframe's scope_column doesn't make sense —
    # every past snapshot is still meaningful, not just the latest.
    table = drop_tables_after("raw.test_append_snapshots")

    append_dataframe(
        db_conn,
        table,
        pd.DataFrame({"game_id": ["G1"], "inning": [1]}),
        identity_columns=("game_id", "inning"),
    )
    db_conn.commit()
    append_dataframe(
        db_conn,
        table,
        pd.DataFrame({"game_id": ["G1"], "inning": [2]}),
        identity_columns=("game_id", "inning"),
    )
    db_conn.commit()
    append_dataframe(
        db_conn,
        table,
        pd.DataFrame({"game_id": ["G1"], "inning": [3]}),
        identity_columns=("game_id", "inning"),
    )
    db_conn.commit()

    with db_conn.cursor() as cur:
        cur.execute(f"SELECT inning FROM {table} WHERE game_id = 'G1' ORDER BY inning")
        assert cur.fetchall() == [("1",), ("2",), ("3",)]


def test_append_dataframe_alters_table_for_a_later_batch_with_extra_columns(
    db_conn, drop_tables_after
):
    # Same schema-drift tolerance as load_dataframe (see
    # test_later_load_with_extra_columns_alters_the_table_instead_of_failing)
    # — append_dataframe shares the underlying _ensure_table_and_columns
    # helper, so this must work identically.
    table = drop_tables_after("raw.test_append_evolving_schema")

    append_dataframe(
        db_conn,
        table,
        pd.DataFrame({"game_id": ["G1"], "balls": [1]}),
        identity_columns=("game_id",),
    )
    db_conn.commit()
    with pytest.warns(SchemaDriftWarning, match="added=.*strikes"):
        append_dataframe(
            db_conn,
            table,
            pd.DataFrame({"game_id": ["G2"], "balls": [2], "strikes": [1]}),
            identity_columns=("game_id",),
        )
    db_conn.commit()

    with db_conn.cursor() as cur:
        cur.execute(f"SELECT game_id, balls, strikes FROM {table} ORDER BY game_id")
        assert cur.fetchall() == [("G1", "1", None), ("G2", "2", "1")]


def test_append_dataframe_rejects_duplicate_or_undeclared_observation_identity(
    db_conn, drop_tables_after
):
    table = drop_tables_after("raw.test_append_identity")
    df = pd.DataFrame({"event_id": ["same", "same"], "value": [1, 2]})

    with pytest.raises(ValueError, match="duplicate append identity"):
        append_dataframe(db_conn, table, df, identity_columns=("event_id",))

    with pytest.raises(ValueError, match="missing from batch"):
        append_dataframe(
            db_conn,
            table,
            pd.DataFrame({"event_id": ["one"]}),
            identity_columns=("captured_at",),
        )
