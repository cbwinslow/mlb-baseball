import time
import zipfile

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

    fake = [(table_a, "A.csv"), (table_b, "B.csv")]
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


def test_downloads_the_mirror_when_no_local_zip(tmp_path, monkeypatch, fake_tables, db_conn):
    table_a, table_b = fake_tables
    monkeypatch.setattr(lahman, "DOWNLOADS_DIR", tmp_path / "empty")
    mirror = tmp_path / "mirror.zip"
    _write_zip(
        mirror,
        "lahman-database-csv-main/data",
        {"A.csv": "id,name\n1,mirror\n", "B.csv": "id\n5\n"},
    )
    called = {"n": 0}

    def _download():
        called["n"] += 1
        return mirror

    monkeypatch.setattr(lahman, "download_release", _download)

    counts = lahman.update()

    assert called["n"] == 1
    assert counts == {table_a: 1, table_b: 1}
    with db_conn.cursor() as cur:
        cur.execute(f"SELECT name FROM {table_a}")
        assert cur.fetchone() == ("mirror",)
