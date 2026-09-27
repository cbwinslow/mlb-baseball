"""The feature build must refuse an empty source (pipeline-freshness 1.1).

Production incident, 2026-09-27: ``gold.batting_game`` / ``gold.pitching_game``
were empty after a ``conform`` run, and ``mlb build --only-features`` reported
``feat.player_form: 0 rows`` as a success. A DuckDB in-memory database attached
as ``pg`` stands in for the read-only Postgres attachment; only the emptiness
check is under test, not the SQL builds.
"""

from __future__ import annotations

import duckdb
import pytest

from mlb_baseball import feat

_ALL = ("core.game", "gold.batting_game", "gold.pitching_game")


def _con(*, empty: tuple[str, ...] = ()) -> duckdb.DuckDBPyConnection:
    con = duckdb.connect()
    con.execute("ATTACH ':memory:' AS pg")
    for schema in ("core", "gold"):
        con.execute(f"CREATE SCHEMA pg.{schema}")
    for relation in _ALL:
        con.execute(f"CREATE TABLE pg.{relation} (id INTEGER)")
        if relation not in empty:
            con.execute(f"INSERT INTO pg.{relation} VALUES (1)")
    return con


def test_populated_sources_pass():
    feat._require_sources(_con())


@pytest.mark.parametrize("relation", _ALL)
def test_each_empty_source_fails_and_is_named(relation):
    with pytest.raises(feat.EmptySourceError) as excinfo:
        feat._require_sources(_con(empty=(relation,)))
    assert relation in str(excinfo.value)


def test_every_empty_source_is_named_together():
    with pytest.raises(feat.EmptySourceError) as excinfo:
        feat._require_sources(_con(empty=_ALL))
    for relation in _ALL:
        assert relation in str(excinfo.value)
