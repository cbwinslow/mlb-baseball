"""Parity (dlt-ingestion-layer 4.1): register and lahman on the staged layer produce the
same rows as the old loaders, into scratch tables. Known, intended differences are asserted
explicitly (the old path lets pandas rewrite values; the new path keeps the source text)."""

import zipfile

import psycopg
import pytest

from mlb_baseball import load
from mlb_baseball.connectors import chadwick_register as register_old
from mlb_baseball.connectors import lahman as lahman_old
from mlb_baseball.ingest_layer.sources.lahman import land_zip
from mlb_baseball.ingest_layer.sources.register import land_register


@pytest.fixture
def connect(db_conn):
    info = db_conn.info
    return lambda: psycopg.connect(info.dsn, password=info.password)


def _rows(db_conn, table, cols):
    order = ", ".join(str(i + 1) for i in range(len(cols)))
    with db_conn.cursor() as cur:
        cur.execute(f"SELECT {', '.join(cols)} FROM {table} ORDER BY {order}")
        out = cur.fetchall()
    db_conn.rollback()
    return out


def _drop(db_conn, tables):
    with db_conn.cursor() as cur:
        for t in tables:
            cur.execute(f"DROP TABLE IF EXISTS {t}")
        cur.execute("DELETE FROM meta.ingestion_item WHERE source IN ('lahman', 'register')")
    db_conn.commit()


PEOPLE_CSV = (
    "playerID,birthYear,nameFirst,nameLast,bats,lgID\n"
    "aaronha01,1934,Hank,Aaron,R,NL\n"
    "abbotji01,,Jim,Abbott,L,\n"
    'ruthba01,1895,"George ""Babe""","Ruth, Jr",L,AL\n'
    "napl01,1871,007,Pad,,NA\n"
)


def _lahman_zip(tmp_path):
    path = tmp_path / "lahman_test.zip"
    with zipfile.ZipFile(path, "w") as zf:
        for _table, filename in lahman_old.TABLES:
            zf.writestr(f"baseballdatabank/{filename}", PEOPLE_CSV)
    return path


def test_lahman_is_typed_and_fixes_what_pandas_corrupted(db_conn, connect, tmp_path):
    zip_path = _lahman_zip(tmp_path)
    new_tables = [t.replace("raw.lahman_", "raw.pnew_lahman_") for t, _f in lahman_old.TABLES]
    try:
        with zipfile.ZipFile(zip_path) as zf:
            frame = lahman_old._read_from_zip(zf, "People.csv")
        load.load_dataframe(db_conn, "raw.pold_lahman_people", frame)
        db_conn.commit()
        counts = land_zip(connect, zip_path, table_prefix="raw.pnew_lahman_")
        assert set(counts) == set(new_tables)
        assert all(n == 4 for n in counts.values())

        cols = ["playerid", "birthyear", "namefirst", "namelast", "bats", "lgid"]
        old = {r[0]: r for r in _rows(db_conn, "raw.pold_lahman_people", cols)}
        new = {r[0]: r for r in _rows(db_conn, "raw.pnew_lahman_people", cols)}
        assert len(old) == len(new) == 4
        # typed: the new column is an integer, not text
        with db_conn.cursor() as cur:
            cur.execute(
                "SELECT data_type FROM information_schema.columns WHERE table_schema = 'raw' "
                "AND table_name = 'pnew_lahman_people' AND column_name = 'birthyear'"
            )
            assert cur.fetchone() == ("integer",)
        db_conn.rollback()
        assert new["aaronha01"] == ("aaronha01", 1934, "Hank", "Aaron", "R", "NL")
        assert old["aaronha01"][1] == "1934.0"  # pandas rewrote the integer as text
        # the old path turned the source text "NA" (National Association) into NULL; ours keeps it
        assert new["napl01"][5] == "NA" and old["napl01"][5] is None
        assert new["napl01"][2] == "007"  # leading zeros in a text column survive
        assert new["abbotji01"][1] is None and new["abbotji01"][5] is None  # blank stays NULL
        assert new["ruthba01"][2] == 'George "Babe"' and new["ruthba01"][3] == "Ruth, Jr"
    finally:
        _drop(db_conn, ["raw.pold_lahman_people", *new_tables])


def test_lahman_a_value_that_breaks_its_declared_type_stops_the_load(db_conn, connect, tmp_path):
    bad = PEOPLE_CSV.replace("1934", "nineteen")
    path = tmp_path / "bad.zip"
    with zipfile.ZipFile(path, "w") as zf:
        for _t, filename in lahman_old.TABLES:
            zf.writestr(filename, bad)
    tables = [t.replace("raw.lahman_", "raw.pnew_lahman_") for t, _f in lahman_old.TABLES]
    try:
        with pytest.raises(ValueError, match="birthyear is not a valid integer"):
            land_zip(connect, path, table_prefix="raw.pnew_lahman_")
        with db_conn.cursor() as cur:
            cur.execute("SELECT to_regclass('raw.pnew_lahman_people')")
            assert cur.fetchone() == (None,)  # nothing created, nothing half-loaded
        db_conn.rollback()
    finally:
        _drop(db_conn, tables)


def test_lahman_second_run_changes_nothing_and_ledger_has_provenance(db_conn, connect, tmp_path):
    zip_path = _lahman_zip(tmp_path)
    tables = [t.replace("raw.lahman_", "raw.pnew_lahman_") for t, _f in lahman_old.TABLES]
    try:
        land_zip(connect, zip_path, table_prefix="raw.pnew_lahman_")
        land_zip(connect, zip_path, table_prefix="raw.pnew_lahman_")
        assert (
            len(_rows(db_conn, "raw.pnew_lahman_people", ["playerid"])) == 4
        )  # replaced, not doubled
        with db_conn.cursor() as cur:
            cur.execute(
                "SELECT count(*), bool_and(artifact_sha256 IS NOT NULL), "
                "bool_and(source_url IS NOT NULL) "
                "FROM meta.ingestion_item WHERE source = 'lahman'"
            )
            assert cur.fetchone() == (len(tables), True, True)
        db_conn.rollback()
    finally:
        _drop(db_conn, tables)


def _register_fetch(name: str) -> str:
    if name.startswith("people-"):
        shard = name[len("people-") : -len(".csv")]
        return f"key_person,key_uuid,name_last\n{shard}1,u{shard},Last{shard}\n"
    return {
        "names.csv": "key_name,name\nn1,Name One\n",
        "links.csv": "key_person,link\np1,http://x\np2,http://y\n",
        "countries.csv": "key_country,name\nUS,United States\n",
    }[name]


def test_register_matches_old_loader(db_conn, connect):
    old_tables = ["raw.pold_people", "raw.pold_links"]
    new_tables = ["raw.pnew_people", "raw.pnew_names", "raw.pnew_links", "raw.pnew_countries"]
    try:
        with db_conn.cursor() as cur:
            cur.execute(
                "CREATE TABLE raw.pold_people (key_person text, key_uuid text, name_last text)"
            )
            cur.execute("CREATE TABLE raw.pold_links (key_person text, link text)")
        total = 0
        for shard in register_old.PEOPLE_SHARDS:
            total += register_old.load_csv(
                db_conn, "raw.pold_people", _register_fetch(f"people-{shard}.csv")
            )
        register_old.load_csv(db_conn, "raw.pold_links", _register_fetch("links.csv"))
        db_conn.commit()

        counts = land_register(connect, _register_fetch, table_prefix="raw.pnew_")
        assert counts == {
            "raw.pnew_people": total,
            "raw.pnew_names": 1,
            "raw.pnew_links": 2,
            "raw.pnew_countries": 1,
        }
        assert _rows(db_conn, "raw.pnew_people", ["key_person", "key_uuid", "name_last"]) == _rows(
            db_conn, "raw.pold_people", ["key_person", "key_uuid", "name_last"]
        )
        assert _rows(db_conn, "raw.pnew_links", ["key_person", "link"]) == _rows(
            db_conn, "raw.pold_links", ["key_person", "link"]
        )
        again = land_register(connect, _register_fetch, table_prefix="raw.pnew_")
        assert again == counts  # a full snapshot replaces: same rows, not doubled
        assert len(_rows(db_conn, "raw.pnew_people", ["key_person"])) == total
    finally:
        _drop(db_conn, old_tables + new_tables)


def test_register_failure_midway_publishes_nothing(db_conn, connect):
    tables = ["raw.pnew_people", "raw.pnew_names", "raw.pnew_links", "raw.pnew_countries"]

    def broken(name: str) -> str:
        if name == "countries.csv":
            raise RuntimeError("source down")
        return _register_fetch(name)

    try:
        with pytest.raises(RuntimeError):
            land_register(connect, broken, table_prefix="raw.pnew_")
        for table in tables:
            with db_conn.cursor() as cur:
                cur.execute("SELECT to_regclass(%s)", (table,))
                assert cur.fetchone() == (None,)  # not even created
            db_conn.rollback()
    finally:
        _drop(db_conn, tables)
