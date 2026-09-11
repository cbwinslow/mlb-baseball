"""Integration coverage for mlb_baseball.catalog.load() -- the meta.metric
idempotent full-rebuild loader (metric-catalog, ADR-291). Uses the real
migrated meta.metric table (migrations/0106_meta_metric.sql), same
db_conn/_test_database fixtures as every other loader test in this suite.
"""

import yaml

from mlb_baseball import catalog

_FIELDS_A = {
    "name": "metric_a",
    "definition": "First fixture metric.",
    "formula": "mlb_baseball/model/fixture_a.py",
    "citation": "project-derived",
    "data_source": "raw.fixture_a",
    "grain": "season",
    "layer": "model",
    "complexity": "arithmetic",
    "implementation": "python",
    "status": "implemented-untested",
    "visibility": "internal",
}
_FIELDS_B = {
    "name": "metric_b",
    "definition": "Second fixture metric.",
    "formula": "mlb_baseball/sql/fixture_b.sql",
    "citation": "FanGraphs, some published constant",
    "data_source": "raw.fixture_b",
    "grain": "game",
    "layer": "gold",
    "complexity": "arithmetic",
    "implementation": "sql",
    "status": "published",
    "visibility": "public",
}


def _reset(db_conn):
    db_conn.rollback()
    with db_conn.cursor() as cur:
        cur.execute("TRUNCATE meta.metric")
    db_conn.commit()


def test_load_populates_meta_metric_from_yaml_fixtures(db_conn, tmp_path):
    _reset(db_conn)
    (tmp_path / "metric_a.yaml").write_text(yaml.safe_dump(_FIELDS_A), encoding="utf-8")
    (tmp_path / "metric_b.yaml").write_text(yaml.safe_dump(_FIELDS_B), encoding="utf-8")

    count = catalog.load(db_conn, directory=tmp_path, commit_sha="deadbeef1234")
    db_conn.commit()

    assert count == 2
    with db_conn.cursor() as cur:
        cur.execute("SELECT name, visibility, source_permalink FROM meta.metric ORDER BY name")
        rows = cur.fetchall()
    assert [r[0] for r in rows] == ["metric_a", "metric_b"]
    assert rows[0][1] == "internal"
    assert rows[1][1] == "public"


def test_load_is_idempotent_full_rebuild(db_conn, tmp_path):
    _reset(db_conn)
    (tmp_path / "metric_a.yaml").write_text(yaml.safe_dump(_FIELDS_A), encoding="utf-8")
    (tmp_path / "metric_b.yaml").write_text(yaml.safe_dump(_FIELDS_B), encoding="utf-8")

    first = catalog.load(db_conn, directory=tmp_path, commit_sha="deadbeef1234")
    db_conn.commit()
    second = catalog.load(db_conn, directory=tmp_path, commit_sha="deadbeef1234")
    db_conn.commit()

    assert first == second == 2
    with db_conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM meta.metric")
        (count,) = cur.fetchone()
    assert count == 2


def test_load_raises_naming_file_and_field_for_invalid_third_fixture(db_conn, tmp_path):
    _reset(db_conn)
    (tmp_path / "metric_a.yaml").write_text(yaml.safe_dump(_FIELDS_A), encoding="utf-8")
    (tmp_path / "metric_b.yaml").write_text(yaml.safe_dump(_FIELDS_B), encoding="utf-8")
    broken = dict(_FIELDS_A)
    broken["name"] = "metric_c"
    del broken["visibility"]
    (tmp_path / "metric_c.yaml").write_text(yaml.safe_dump(broken), encoding="utf-8")

    try:
        catalog.load(db_conn, directory=tmp_path, commit_sha="deadbeef1234")
        raised = False
    except catalog.CatalogError as exc:
        raised = True
        message = str(exc)
    assert raised
    assert "metric_c.yaml" in message
    assert "visibility" in message

    # The failed load must not have partially truncated meta.metric --
    # load_all() validates every entry before load() opens its transaction,
    # so a bad third fixture never touches the table at all.
    db_conn.rollback()
    with db_conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM meta.metric")
        (count,) = cur.fetchone()
    assert count == 0


def test_source_permalink_embeds_exact_fake_commit_sha_not_head(db_conn, tmp_path):
    _reset(db_conn)
    (tmp_path / "metric_b.yaml").write_text(yaml.safe_dump(_FIELDS_B), encoding="utf-8")

    catalog.load(db_conn, directory=tmp_path, commit_sha="0123456789abcdef")
    db_conn.commit()

    with db_conn.cursor() as cur:
        cur.execute("SELECT source_permalink FROM meta.metric WHERE name = 'metric_b'")
        (permalink,) = cur.fetchone()
    assert permalink == (
        "https://github.com/cbwinslow/mlb-baseball/blob/0123456789abcdef/"
        "mlb_baseball/sql/fixture_b.sql"
    )
    assert "HEAD" not in permalink
    assert "/main/" not in permalink
