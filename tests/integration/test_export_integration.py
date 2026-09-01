"""Integration tests for Research Database Exporter & Interoperability Layer (EXPORT-01)."""

import json
import zipfile

import pytest

openpyxl = pytest.importorskip("openpyxl")
pq = pytest.importorskip("pyarrow.parquet")

from mlb_baseball.export import (  # noqa: E402
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
            VALUES (101, 'NYA', 'AL', 'New York', 'Yankees', 1903, 2026),
                   (102, 'BOS', 'AL', 'Boston', 'Red Sox', 1901, 2026)
            ON CONFLICT (id) DO NOTHING;
            """
        )
        # Seed core.player
        cur.execute(
            """
            INSERT INTO core.player (id, retro_id, last_name, first_name)
            VALUES (90001, 'judga001', 'Judge', 'Aaron'),
                   (90002, 'coleg001', 'Cole', 'Gerrit')
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
                800001, 'NYA202406010', 2024, '2024-06-01', 0, 101, 102, 5, 3, 'R'
            )
            ON CONFLICT (id) DO NOTHING;
            """
        )
    db_conn.commit()


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
