"""Retype swap (typed-raw-layer 1.3): load beside, compare cell by cell, rename in one
transaction, keep the old table, roll back by renaming back."""

import zipfile

import psycopg
import pytest

from mlb_baseball import load
from mlb_baseball.connectors import lahman as lahman_old
from mlb_baseball.ingest_layer import schemas
from mlb_baseball.ingest_layer.sources.lahman import land_zip
from mlb_baseball.ingest_layer.swap import compare, swap

CSV = (
    "playerID,birthYear,nameFirst,nameLast,bats,birthCountry\n"
    "aaronha01,1934,Hank,Aaron,R,USA\n"
    "abbotji01,,Jim,Abbott,L,\n"
    "napl01,1871,Nap,Lajoie,,NA\n"
)


@pytest.fixture
def setup(db_conn, tmp_path):
    path = tmp_path / "l.zip"
    with zipfile.ZipFile(path, "w") as zf:
        for _t, filename in lahman_old.TABLES:
            zf.writestr(filename, CSV)
    info = db_conn.info
    connect = lambda: psycopg.connect(info.dsn, password=info.password)  # noqa: E731
    with zipfile.ZipFile(path) as zf:  # the old path: pandas text
        load.load_dataframe(
            db_conn, "raw.sw_lahman_people", lahman_old._read_from_zip(zf, "People.csv")
        )
    db_conn.commit()
    land_zip(connect, path, table_prefix="raw.sw_lahman_", table_suffix="__new")
    yield db_conn
    db_conn.rollback()
    with db_conn.cursor() as cur:
        cur.execute(
            "SELECT format('DROP TABLE %I.%I', table_schema, table_name) "
            "FROM information_schema.tables WHERE table_name LIKE 'sw\\_lahman\\_%%'"
        )
        for (stmt,) in cur.fetchall():
            cur.execute(stmt)
        cur.execute("DELETE FROM meta.ingestion_item WHERE source = 'lahman'")
    db_conn.commit()


def _spec():
    return schemas.load("lahman", prefix=("raw.lahman_", "raw.sw_lahman_"))["raw.lahman_people"]


def test_compare_explains_only_the_known_old_path_corruption(setup):
    spec = _spec()
    diff = compare(setup, "raw.sw_lahman_people", "raw.sw_lahman_people__new", spec)
    assert diff.same and diff.old_rows == diff.new_rows == 3
    # without the NA allowance the difference is visible: that row had league 'NA'
    strict = compare(setup, "raw.sw_lahman_people", "raw.sw_lahman_people__new", spec, null_old=())
    assert not strict.same and strict.only_old == strict.only_new == 1


def test_swap_keeps_the_old_table_and_rolls_back_by_renaming(setup):
    swap(setup, "raw.sw_lahman_people")
    setup.commit()
    with setup.cursor() as cur:
        cur.execute(
            "SELECT data_type FROM information_schema.columns WHERE table_name = "
            "'sw_lahman_people' AND column_name = 'birthyear'"
        )
        assert cur.fetchone() == ("integer",)
        cur.execute(
            "SELECT data_type FROM information_schema.columns WHERE table_name = "
            "'sw_lahman_people__old' AND column_name = 'birthyear'"
        )
        assert cur.fetchone() == ("text",)
    # roll back: same two renames reversed
    with setup.cursor() as cur:
        cur.execute("ALTER TABLE raw.sw_lahman_people RENAME TO sw_lahman_people__new")
        cur.execute("ALTER TABLE raw.sw_lahman_people__old RENAME TO sw_lahman_people")
    setup.commit()
    with setup.cursor() as cur:
        cur.execute(
            "SELECT data_type FROM information_schema.columns WHERE table_name = "
            "'sw_lahman_people' AND column_name = 'birthyear'"
        )
        assert cur.fetchone() == ("text",)
