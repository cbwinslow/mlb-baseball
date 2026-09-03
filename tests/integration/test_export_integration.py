"""Integration tests for Research Database Exporter & Interoperability Layer (EXPORT-01)."""

import json
import zipfile

import pytest

openpyxl = pytest.importorskip("openpyxl")
pq = pytest.importorskip("pyarrow.parquet")

from mlb_baseball.export import (  # noqa: E402
    export_backbone_bundle,
    export_bundle,
    export_relation,
    resolve_relation,
)


def _seed_test_data(db_conn):
    """Seed minimal core and gold test data for export round-trips."""
    with db_conn.cursor() as cur:
        # Seed core.team
        cur.execute(
            """
            INSERT INTO core.team (id, retro_team_id, league, city, nickname, first_year, last_year)
            VALUES (900101, 'NYA', 'AL', 'New York', 'Yankees', 1903, 2026),
                   (900102, 'BOS', 'AL', 'Boston', 'Red Sox', 1901, 2026)
            ON CONFLICT (id) DO NOTHING;
            """
        )
        # Seed core.player
        cur.execute(
            """
            INSERT INTO core.player (id, retro_id, last_name, first_name)
            VALUES (990001, 'judga001', 'Judge', 'Aaron'),
                   (990002, 'coleg001', 'Cole', 'Gerrit')
            ON CONFLICT (id) DO NOTHING;
            """
        )
        # Seed core.game
        cur.execute(
            """
            INSERT INTO core.game (
                id, retro_game_id, season, game_date, game_number, home_team_id, away_team_id,
                home_score, away_score, game_type
            )
            VALUES (
                980001, 'NYA202406010', 2024, '2024-06-01', 0, 900101, 900102, 5, 3, 'R'
            )
            ON CONFLICT (id) DO NOTHING;
            """
        )
    db_conn.commit()


def _seed_backbone_data(db_conn):
    """Seed one row per grain in each of the ten candidate backbone tables."""
    _seed_test_data(db_conn)
    with db_conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO gold.batting_game
                (game_id, player_id, team_id, season, game_date, pa, ab, h)
            VALUES (980001, 990001, 900101, 2024, '2024-06-01', 4, 4, 2)
            ON CONFLICT DO NOTHING;

            INSERT INTO gold.pitching_game (game_id, player_id, team_id, season, game_date, outs, h)
            VALUES (980001, 990002, 900102, 2024, '2024-06-01', 27, 5)
            ON CONFLICT DO NOTHING;

            INSERT INTO gold.batting_season (player_id, season, team_id, is_combined, g, pa, ab, h)
            VALUES (990001, 2024, 900101, false, 1, 4, 4, 2),
                   (990001, 2024, NULL, true, 1, 4, 4, 2)
            ON CONFLICT DO NOTHING;

            INSERT INTO gold.pitching_season (player_id, season, team_id, is_combined, g, outs, h)
            VALUES (990002, 2024, 900102, false, 1, 27, 5),
                   (990002, 2024, NULL, true, 1, 27, 5)
            ON CONFLICT DO NOTHING;

            INSERT INTO gold.batting_team (team_id, season, g, pa, ab, h)
            VALUES (900101, 2024, 1, 4, 4, 2)
            ON CONFLICT DO NOTHING;

            INSERT INTO gold.pitching_team (team_id, season, g, outs, h)
            VALUES (900102, 2024, 1, 27, 5)
            ON CONFLICT DO NOTHING;

            INSERT INTO gold.batting_career
                (player_id, seasons, first_season, last_season, g, pa, ab, h)
            VALUES (990001, 1, 2024, 2024, 1, 4, 4, 2)
            ON CONFLICT DO NOTHING;

            INSERT INTO gold.pitching_career
                (player_id, seasons, first_season, last_season, g, outs, h)
            VALUES (990002, 1, 2024, 2024, 1, 27, 5)
            ON CONFLICT DO NOTHING;

            INSERT INTO gold.player_season (player_id, season, is_pitcher, player_name, team, games)
            VALUES (990001, 2024, false, 'Aaron Judge', 'New York', 1)
            ON CONFLICT DO NOTHING;

            INSERT INTO gold.team_season (team_id, season, team_city, team_nickname, wins, losses)
            VALUES (900101, 2024, 'New York', 'Yankees', 1, 0)
            ON CONFLICT DO NOTHING;
            """
        )
    db_conn.commit()


def _cleanup_backbone_data(db_conn) -> None:
    """Delete exactly the rows _seed_backbone_data (and _seed_test_data)
    inserted, including the core.game/core.player/core.team rows. db_conn is
    function-scoped but the underlying test database is shared for the whole
    pytest run (tests/AGENTS.md) -- without this, these rows outlive the
    test and an unrelated later test's own unconditional
    `DELETE FROM core.game`/`core.team` (a common _reset() pattern in this
    suite) hits a FK violation against whatever of ours is still there.
    Deleting core.game/player/team here is safe: every other test that seeds
    them re-inserts via its own `ON CONFLICT DO NOTHING` call, never assumes
    a prior test already put them there."""
    with db_conn.cursor() as cur:
        cur.execute("DELETE FROM gold.batting_game WHERE game_id = 980001")
        cur.execute("DELETE FROM gold.pitching_game WHERE game_id = 980001")
        cur.execute("DELETE FROM gold.batting_season WHERE player_id = 990001 AND season = 2024")
        cur.execute("DELETE FROM gold.pitching_season WHERE player_id = 990002 AND season = 2024")
        cur.execute("DELETE FROM gold.batting_team WHERE team_id = 900101 AND season = 2024")
        cur.execute("DELETE FROM gold.pitching_team WHERE team_id = 900102 AND season = 2024")
        cur.execute("DELETE FROM gold.batting_career WHERE player_id = 990001")
        cur.execute("DELETE FROM gold.pitching_career WHERE player_id = 990002")
        cur.execute("DELETE FROM gold.player_season WHERE player_id = 990001 AND season = 2024")
        cur.execute("DELETE FROM gold.team_season WHERE team_id = 900101 AND season = 2024")
        cur.execute("DELETE FROM core.game WHERE id = 980001")
        cur.execute("DELETE FROM core.player WHERE id IN (990001, 990002)")
        cur.execute("DELETE FROM core.team WHERE id IN (900101, 900102)")
    db_conn.commit()


def _type_bucket(type_str: str) -> str:
    """Normalize a pyarrow/duckdb type string into a coarse comparison bucket."""
    t = type_str.lower()
    if "bool" in t:
        return "bool"
    if "int" in t:
        return "int"
    if "double" in t or "float" in t or "decimal" in t or "numeric" in t:
        return "float"
    if "timestamp" in t:
        return "timestamp"
    if "date" in t:
        return "date"
    return "text"


def test_export_backbone_bundle_manifest_and_excluded(db_conn, tmp_path):
    """Verify the backbone preset writes one Parquet per eligible table, a
    manifest.json, a README.md dataset card, and records player_season /
    team_season as excluded with their rights reasons (task 1.2)."""
    _seed_backbone_data(db_conn)
    try:
        bundle_dir = tmp_path / "backbone_bundle"

        result = export_backbone_bundle(db_conn, out_dir=bundle_dir)
        assert result == bundle_dir

        eligible = {
            "batting_game",
            "pitching_game",
            "batting_season",
            "pitching_season",
            "batting_team",
            "pitching_team",
            "batting_career",
            "pitching_career",
        }
        for table in eligible:
            assert (bundle_dir / "data" / f"{table}.parquet").exists()
        assert not (bundle_dir / "data" / "player_season.parquet").exists()
        assert not (bundle_dir / "data" / "team_season.parquet").exists()

        manifest = json.loads((bundle_dir / "manifest.json").read_text(encoding="utf-8"))
        assert {t["table"] for t in manifest["tables"]} == eligible
        for entry in manifest["tables"]:
            assert entry["row_count"] >= 1
            assert entry["columns"]

        excluded_by_table = {e["table"]: e["reason"] for e in manifest["excluded"]}
        assert set(excluded_by_table) == {"player_season", "team_season"}
        assert "Baseball-Reference" in excluded_by_table["player_season"]
        assert "Lahman" in excluded_by_table["team_season"]

        card = (bundle_dir / "README.md").read_text(encoding="utf-8")
        assert manifest["schema_version"] in card
        assert "Retrosheet" in card
    finally:
        _cleanup_backbone_data(db_conn)


def test_export_backbone_bundle_removes_stale_files_from_a_prior_run(db_conn, tmp_path):
    """A stale data/player_season.parquet left over from before the
    rights-exclusion gate existed (or a differently-configured earlier run)
    must not survive a re-export -- the publish step uploads the bundle
    directory as-is, so a leftover file would ship despite the manifest
    saying it's excluded."""
    _seed_backbone_data(db_conn)
    try:
        bundle_dir = tmp_path / "backbone_bundle"
        data_dir = bundle_dir / "data"
        data_dir.mkdir(parents=True)
        stale_file = data_dir / "player_season.parquet"
        stale_file.write_bytes(b"stale rights-restricted content")

        export_backbone_bundle(db_conn, out_dir=bundle_dir)

        assert not stale_file.exists()
        assert (data_dir / "batting_game.parquet").exists()
    finally:
        _cleanup_backbone_data(db_conn)


def test_export_backbone_bundle_is_deterministic(db_conn, tmp_path):
    """Re-running the backbone export over the same database state produces
    identical row counts and identical first/last rows per table (task 1.3)."""
    _seed_backbone_data(db_conn)
    try:
        dir1 = tmp_path / "run1"
        dir2 = tmp_path / "run2"
        export_backbone_bundle(db_conn, out_dir=dir1)
        export_backbone_bundle(db_conn, out_dir=dir2)

        manifest1 = json.loads((dir1 / "manifest.json").read_text(encoding="utf-8"))
        manifest2 = json.loads((dir2 / "manifest.json").read_text(encoding="utf-8"))
        tables1 = {t["table"]: t for t in manifest1["tables"]}
        tables2 = {t["table"]: t for t in manifest2["tables"]}
        assert tables1.keys() == tables2.keys()

        for table, entry1 in tables1.items():
            entry2 = tables2[table]
            assert entry1["row_count"] == entry2["row_count"]

            parquet1 = pq.read_table(dir1 / entry1["file"])
            parquet2 = pq.read_table(dir2 / entry2["file"])
            assert parquet1.num_rows == parquet2.num_rows
            if parquet1.num_rows == 0:
                continue
            for idx in (0, -1):
                row1 = {col: parquet1.column(col)[idx].as_py() for col in parquet1.column_names}
                row2 = {col: parquet2.column(col)[idx].as_py() for col in parquet2.column_names}
                assert row1 == row2, f"{table} row {idx} differs between export runs"
    finally:
        _cleanup_backbone_data(db_conn)


def test_export_backbone_bundle_duckdb_round_trip(db_conn, tmp_path):
    """Round-trip: write the bundle with pyarrow, read every Parquet back with
    duckdb, assert each table's column names + types match its manifest.json
    entry (task 1.5, guards against the pyarrow/duckdb schema-drift risk in
    design.md)."""
    duckdb = pytest.importorskip("duckdb")
    _seed_backbone_data(db_conn)
    try:
        bundle_dir = tmp_path / "backbone_roundtrip"

        export_backbone_bundle(db_conn, out_dir=bundle_dir)
        manifest = json.loads((bundle_dir / "manifest.json").read_text(encoding="utf-8"))

        for entry in manifest["tables"]:
            parquet_path = bundle_dir / entry["file"]
            relation = duckdb.sql(f"SELECT * FROM read_parquet('{parquet_path.as_posix()}')")
            assert relation.columns == [c["name"] for c in entry["columns"]]
            manifest_types = {c["name"]: c["type"] for c in entry["columns"]}
            for name, duck_type in zip(relation.columns, relation.types, strict=True):
                assert _type_bucket(str(duck_type)) == _type_bucket(manifest_types[name]), (
                    f"{entry['table']}.{name}: duckdb={duck_type} manifest={manifest_types[name]}"
                )
    finally:
        _cleanup_backbone_data(db_conn)


def test_export_relation_csv_round_trip(db_conn, tmp_path):
    """Verify export_relation writes valid CSV from real database table."""
    _seed_test_data(db_conn)
    out_csv = tmp_path / "players.csv"

    path, count = export_relation(
        db_conn,
        "core.player",
        format="csv",
        out_path=out_csv,
    )
    assert path == out_csv
    assert path.exists()
    assert count >= 2

    lines = path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) >= 3  # header + at least 2 rows
    assert "retro_id" in lines[0]
    assert "Judge" in path.read_text(encoding="utf-8")


def test_export_relation_parquet_round_trip(db_conn, tmp_path):
    """Verify export_relation writes valid Apache Parquet file read by PyArrow."""
    _seed_test_data(db_conn)
    out_parquet = tmp_path / "games.parquet"

    path, count = export_relation(
        db_conn,
        "core.game",
        format="parquet",
        out_path=out_parquet,
        season=2024,
    )
    assert path == out_parquet
    assert path.exists()
    assert count >= 1

    table = pq.read_table(out_parquet)
    assert "retro_game_id" in table.column_names
    assert "season" in table.column_names
    assert table.num_rows == count


def test_export_relation_xlsx_round_trip(db_conn, tmp_path):
    """Verify export_relation writes valid Excel workbook read by openpyxl."""
    _seed_test_data(db_conn)
    out_xlsx = tmp_path / "teams.xlsx"

    path, count = export_relation(
        db_conn,
        "core.team",
        format="xlsx",
        out_path=out_xlsx,
    )
    assert path == out_xlsx
    assert path.exists()
    assert count >= 2

    wb = openpyxl.load_workbook(out_xlsx, read_only=True)
    assert "team" in wb.sheetnames
    ws = wb["team"]
    rows = list(ws.iter_rows(values_only=True))
    assert len(rows) >= 3  # header + rows
    assert "retro_team_id" in rows[0]
    wb.close()


def test_export_bundle_public_safe_with_manifest_and_zip(db_conn, tmp_path):
    """Verify public_safe bundle generation creates manifest, parquets, and clean zip."""
    _seed_test_data(db_conn)
    bundle_dir = tmp_path / "public_safe_bundle"

    zip_path = export_bundle(
        db_conn,
        profile="public_safe",
        out_dir=bundle_dir,
        make_zip=True,
    )
    assert zip_path.exists()
    assert zip_path.name.endswith(".zip")

    # Check manifest contents
    manifest_file = bundle_dir / "MANIFEST.json"
    assert manifest_file.exists()
    manifest = json.loads(manifest_file.read_text(encoding="utf-8"))

    assert manifest["profile"] == "public_safe"
    assert "Retrosheet" in manifest["attribution"]
    assert len(manifest["relations"]) > 0

    exported_rel_names = {r["relation"] for r in manifest["relations"]}
    for r_name in exported_rel_names:
        rel = resolve_relation(r_name)
        assert rel.profile == "public_safe"

    # Assert excluded relations are strictly absent
    excluded = ["raw.mlb_playbyplay", "core.player_war", "core.market", "gold.game_feature"]
    for exc in excluded:
        assert exc not in exported_rel_names
        assert not (bundle_dir / f"{exc}.parquet").exists()

    # Check zip integrity
    with zipfile.ZipFile(zip_path, "r") as zf:
        names = zf.namelist()
        assert "MANIFEST.json" in names
        assert any(n.endswith(".parquet") for n in names)
