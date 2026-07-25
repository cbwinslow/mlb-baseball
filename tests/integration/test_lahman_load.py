import time
import zipfile

import pandas as pd
import pytest

from mlb_baseball.connectors import lahman


def _write_zip(path, folder, files):
    with zipfile.ZipFile(path, "w") as zf:
        for filename, content in files.items():
            zf.writestr(f"{folder}/{filename}", content)


def test_find_local_zip_picks_the_most_recently_modified(tmp_path, monkeypatch):
    monkeypatch.setattr(lahman, "DOWNLOADS_DIR", tmp_path)
    older = tmp_path / "lahman_1871-2024_csv.zip"
    newer = tmp_path / "lahman_1871-2025_csv.zip"
    older.write_bytes(b"old")
    time.sleep(0.01)
    newer.write_bytes(b"new")

    assert lahman.find_local_zip() == newer


def test_find_local_zip_returns_none_when_empty(tmp_path, monkeypatch):
    monkeypatch.setattr(lahman, "DOWNLOADS_DIR", tmp_path)
    assert lahman.find_local_zip() is None


@pytest.fixture
def fake_tables(monkeypatch, drop_tables_after):
    table_a = drop_tables_after("raw.test_lahman_a")
    table_b = drop_tables_after("raw.test_lahman_b")

    def _network_fallback(*_args, **_kwargs):
        raise AssertionError("network fallback should not be called when a local zip exists")

    fake = [
        (table_a, "A.csv", _network_fallback),
        (table_b, "B.csv", _network_fallback),
    ]
    monkeypatch.setattr(lahman, "TABLES", fake)
    return table_a, table_b


def test_bootstrap_loads_from_local_zip(tmp_path, monkeypatch, fake_tables, db_conn):
    table_a, table_b = fake_tables
    monkeypatch.setattr(lahman, "DOWNLOADS_DIR", tmp_path)
    _write_zip(
        tmp_path / "lahman_1871-2099_csv.zip",
        "lahman_1871-2099_csv",
        {"A.csv": "id,name\n1,foo\n", "B.csv": "id,value\n1,9\n2,10\n"},
    )

    counts = lahman.bootstrap()

    assert counts == {table_a: 1, table_b: 2}
    with db_conn.cursor() as cur:
        cur.execute(f"SELECT id, name FROM {table_a}")
        assert cur.fetchone() == ("1", "foo")


def test_falls_back_to_network_when_no_local_zip(tmp_path, monkeypatch, drop_tables_after, db_conn):
    monkeypatch.setattr(lahman, "DOWNLOADS_DIR", tmp_path)
    table = drop_tables_after("raw.test_lahman_network")
    fetch_called = {"count": 0}

    def _fake_fetch():
        fetch_called["count"] += 1
        return pd.DataFrame({"id": [1], "name": ["from-network"]})

    monkeypatch.setattr(lahman, "TABLES", [(table, "A.csv", _fake_fetch)])

    counts = lahman.update()

    assert fetch_called["count"] == 1
    assert counts == {table: 1}
    with db_conn.cursor() as cur:
        cur.execute(f"SELECT name FROM {table}")
        assert cur.fetchone() == ("from-network",)
