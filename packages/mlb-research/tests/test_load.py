"""Unit tests for mlb_research.load() -- the package's own contract tests.

Standalone: no mlb_baseball import, no database. hf_hub_download is always
mocked; a fixture Parquet file is written with duckdb (no pyarrow needed).
"""

from pathlib import Path

import duckdb
import mlb_research
import pandas as pd
import pytest


def _write_parquet(path: Path, rows: list[dict]) -> None:
    df = pd.DataFrame(rows)  # noqa: F841 -- read by duckdb's replacement scan below
    con = duckdb.connect()
    escaped = mlb_research._escape_duckdb_literal(path.as_posix())
    con.execute(f"COPY (SELECT * FROM df) TO '{escaped}' (FORMAT PARQUET)")


@pytest.fixture(autouse=True)
def _clear_download_cache():
    mlb_research._DOWNLOAD_CACHE.clear()
    yield
    mlb_research._DOWNLOAD_CACHE.clear()


def test_load_unknown_table_names_it_and_lists_valid_tables():
    with pytest.raises(ValueError, match="Unknown table 'not_a_table'") as exc_info:
        mlb_research.load("not_a_table")
    for name in mlb_research.BACKBONE_TABLES:
        assert name in str(exc_info.value)


def test_load_unreachable_version_wraps_the_underlying_error(monkeypatch):
    def _raise(**kwargs):
        raise OSError("404 Client Error: repository not found")

    monkeypatch.setattr("huggingface_hub.hf_hub_download", _raise, raising=False)

    with pytest.raises(RuntimeError, match="Could not load 'batting_game'") as exc_info:
        mlb_research.load("batting_game", version="v9.9.9")
    assert "404 Client Error" in str(exc_info.value)


def test_load_returns_dataframe_filtered_by_season(monkeypatch, tmp_path):
    parquet_path = tmp_path / "batting_game.parquet"
    _write_parquet(
        parquet_path,
        [
            {"game_id": 1, "player_id": 1, "season": 2022, "h": 1},
            {"game_id": 2, "player_id": 1, "season": 2023, "h": 2},
        ],
    )
    monkeypatch.setattr(
        "huggingface_hub.hf_hub_download",
        lambda **kwargs: str(parquet_path),
        raising=False,
    )

    df = mlb_research.load("batting_game", season=2023)

    assert list(df["season"]) == [2023]
    assert list(df["h"]) == [2]


def test_load_without_season_returns_every_row(monkeypatch, tmp_path):
    parquet_path = tmp_path / "batting_game.parquet"
    _write_parquet(
        parquet_path,
        [
            {"game_id": 1, "player_id": 1, "season": 2022, "h": 1},
            {"game_id": 2, "player_id": 1, "season": 2023, "h": 2},
        ],
    )
    monkeypatch.setattr(
        "huggingface_hub.hf_hub_download",
        lambda **kwargs: str(parquet_path),
        raising=False,
    )

    df = mlb_research.load("batting_game")

    assert len(df) == 2


def test_load_caches_within_process_no_repeat_network_call(monkeypatch, tmp_path):
    """A repeat load() of the same (table, version) does no network I/O
    (task 3.4): the mocked downloader is patched to raise on a second call,
    and load() must still return."""
    parquet_path = tmp_path / "batting_game.parquet"
    _write_parquet(parquet_path, [{"game_id": 1, "player_id": 1, "season": 2023, "h": 1}])

    calls = []
    monkeypatch.setattr(
        "huggingface_hub.hf_hub_download",
        lambda **kwargs: calls.append(kwargs) or str(parquet_path),
        raising=False,
    )

    first = mlb_research.load("batting_game", version="v0.1.0")
    assert len(calls) == 1

    monkeypatch.setattr(
        "huggingface_hub.hf_hub_download",
        lambda **kwargs: (_ for _ in ()).throw(
            AssertionError("hf_hub_download must not be called for a cached table+version")
        ),
        raising=False,
    )

    second = mlb_research.load("batting_game", version="v0.1.0")
    assert len(first) == len(second) == 1


def test_load_different_version_is_not_cached_together(monkeypatch, tmp_path):
    """A different version is a cache miss and does hit the downloader again."""
    parquet_path = tmp_path / "batting_game.parquet"
    _write_parquet(parquet_path, [{"game_id": 1, "player_id": 1, "season": 2023, "h": 1}])

    calls = []
    monkeypatch.setattr(
        "huggingface_hub.hf_hub_download",
        lambda **kwargs: calls.append(kwargs) or str(parquet_path),
        raising=False,
    )

    mlb_research.load("batting_game", version="v0.1.0")
    mlb_research.load("batting_game", version="v0.2.0")

    assert len(calls) == 2
    assert calls[0]["revision"] == "v0.1.0"
    assert calls[1]["revision"] == "v0.2.0"


def test_load_rejects_season_on_career_tables():
    """batting_career/pitching_career have no season column (first_season/
    last_season instead) -- load() must raise its own clear error rather
    than let DuckDB's raw binder error surface."""
    for table in ("batting_career", "pitching_career"):
        with pytest.raises(ValueError, match="has no season column"):
            mlb_research.load(table, season=2024)


def test_load_escapes_a_single_quote_in_the_cache_path(monkeypatch, tmp_path):
    """A local cache path containing a single quote must not break the
    interpolated DuckDB SQL literal."""
    quoted_dir = tmp_path / "o'brien"
    quoted_dir.mkdir()
    parquet_path = quoted_dir / "batting_game.parquet"
    _write_parquet(parquet_path, [{"game_id": 1, "player_id": 1, "season": 2023, "h": 1}])

    monkeypatch.setattr(
        "huggingface_hub.hf_hub_download",
        lambda **kwargs: str(parquet_path),
        raising=False,
    )

    df = mlb_research.load("batting_game", season=2023)

    assert len(df) == 1


def test_load_default_version_resolves_to_main_revision(monkeypatch, tmp_path):
    parquet_path = tmp_path / "batting_game.parquet"
    _write_parquet(parquet_path, [{"game_id": 1, "player_id": 1, "season": 2023, "h": 1}])

    calls = []
    monkeypatch.setattr(
        "huggingface_hub.hf_hub_download",
        lambda **kwargs: calls.append(kwargs) or str(parquet_path),
        raising=False,
    )

    mlb_research.load("batting_game")

    assert calls[0]["revision"] == "main"
    assert calls[0]["repo_type"] == "dataset"
    assert calls[0]["repo_id"] == mlb_research.DEFAULT_REPO_ID
    assert calls[0]["filename"] == "data/batting_game.parquet"
