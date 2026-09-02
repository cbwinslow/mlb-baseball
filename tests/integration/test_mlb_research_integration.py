"""Cross-package integration test: mlb_research.load() against a real
backbone bundle produced by mlb_baseball.export.export_backbone_bundle
(delivery-surface change, task 3.2). mlb_research itself never imports
mlb_baseball -- this test is the one place that legitimately needs both.
"""

import json

import pytest

mlb_research = pytest.importorskip("mlb_research")
pytest.importorskip("pyarrow.parquet")

from mlb_baseball.export import export_backbone_bundle  # noqa: E402

from .test_export_integration import _seed_backbone_data  # noqa: E402


def test_load_pitching_season_from_a_locally_produced_bundle(db_conn, tmp_path, monkeypatch):
    """load("pitching_season", season=2023) against a real task-1 bundle
    returns a DataFrame with only 2023 rows and the documented columns."""
    _seed_backbone_data(db_conn)
    with db_conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO gold.pitching_season (player_id, season, team_id, is_combined, g, outs, h)
            VALUES (90002, 2023, 102, false, 1, 27, 5),
                   (90002, 2023, NULL, true, 1, 27, 5)
            ON CONFLICT DO NOTHING;
            """
        )
    db_conn.commit()

    bundle_dir = tmp_path / "backbone_bundle"
    export_backbone_bundle(db_conn, out_dir=bundle_dir)

    manifest = json.loads((bundle_dir / "manifest.json").read_text(encoding="utf-8"))
    manifest_columns = next(
        t["columns"] for t in manifest["tables"] if t["table"] == "pitching_season"
    )
    documented_columns = {c["name"] for c in manifest_columns}

    monkeypatch.setattr(
        "huggingface_hub.hf_hub_download",
        lambda **kwargs: str(bundle_dir / "data" / "pitching_season.parquet"),
        raising=False,
    )
    mlb_research._DOWNLOAD_CACHE.clear()

    df = mlb_research.load("pitching_season", season=2023)

    assert set(df["season"].unique()) == {2023}
    assert set(df.columns) == documented_columns
    assert len(df) >= 1
