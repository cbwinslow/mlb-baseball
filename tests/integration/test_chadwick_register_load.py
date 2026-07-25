"""Integration test for the register connector's DB-loading behavior.
Network is mocked (fixture CSV content) — fetch_csv itself is a thin,
already-covered wrapper around requests.get; what needs real coverage here
is that the fetched CSVs actually land correctly in Postgres."""

from unittest.mock import patch

import pytest

from mlb_baseball.connectors import chadwick_register as register

FIXTURES = {
    "people-0.csv": "key_person,key_retro\nabc123,retroid1\n",
    "people-1.csv": "key_person,key_retro\ndef456,retroid2\n",
    "names.csv": "key_person,name_last\nabc123,Smith\n",
    "links.csv": "key_person,source,value\nabc123,tsncards,111\n",
    "countries.csv": "key_iso_alpha2,name_full_en\nUS,United States\n",
}


def _fake_get(url, timeout=30):
    filename = url.rsplit("/", 1)[-1]
    response = type("Response", (), {})()
    response.text = FIXTURES.get(filename, "key_person,key_retro\n")
    response.raise_for_status = lambda: None
    return response


@pytest.fixture(autouse=True)
def _fewer_shards(monkeypatch):
    # Real code pulls 16 people shards; two is enough to prove the loop works.
    monkeypatch.setattr(register, "PEOPLE_SHARDS", "01")


@pytest.fixture(autouse=True)
def _clean_register_tables(db_conn):
    yield
    with db_conn.cursor() as cur:
        cur.execute(
            "TRUNCATE raw.register_people, raw.register_names, "
            "raw.register_links, raw.register_countries"
        )
    db_conn.commit()


def test_bootstrap_loads_all_four_tables(db_conn):
    with patch.object(register.requests, "get", side_effect=_fake_get):
        counts = register.bootstrap()

    assert counts == {
        "raw.register_people": 2,
        "raw.register_names": 1,
        "raw.register_links": 1,
        "raw.register_countries": 1,
    }
    with db_conn.cursor() as cur:
        cur.execute("SELECT key_person, key_retro FROM raw.register_people ORDER BY key_person")
        assert cur.fetchall() == [("abc123", "retroid1"), ("def456", "retroid2")]


def test_rerunning_truncates_instead_of_duplicating(db_conn):
    with patch.object(register.requests, "get", side_effect=_fake_get):
        register.bootstrap()
        register.update()

    with db_conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM raw.register_people")
        assert cur.fetchone() == (2,)
