"""pybaseball-style loader for the MLB Research Statistic Backbone dataset.

Resolves a released version of the dataset published at
https://huggingface.co/datasets/cbwinslow/mlb-research, downloads and caches
its Parquet files, and returns a table as a ``pandas.DataFrame`` via
:func:`load`. Deliberately does not depend on ``mlb_baseball`` -- this
package is meant to be installed standalone (``pip install mlb-research``)
by a researcher who has never cloned that repository.
"""

from __future__ import annotations

from pathlib import Path

import duckdb
import pandas as pd

__version__ = "0.1.0"

DEFAULT_REPO_ID = "cbwinslow/mlb-research"

# The eight backbone tables published in the dataset (delivery-surface
# change). gold.player_season / gold.team_season are not published --
# excluded on source-rights grounds, see
# openspec/changes/delivery-surface/rights-review.md in the source repo.
BACKBONE_TABLES: tuple[str, ...] = (
    "batting_game",
    "pitching_game",
    "batting_season",
    "pitching_season",
    "batting_team",
    "pitching_team",
    "batting_career",
    "pitching_career",
)

# In-process cache: a repeat load() of the same (repo_id, table, revision)
# does no network I/O, even beyond whatever caching huggingface_hub's own
# download does on disk.
_DOWNLOAD_CACHE: dict[tuple[str, str, str], Path] = {}


def _resolve_revision(version: str) -> str:
    """Resolve a public ``version`` argument to an HF Hub revision."""
    return "main" if version == "latest" else version


def _download_table(repo_id: str, table: str, revision: str) -> Path:
    key = (repo_id, table, revision)
    cached = _DOWNLOAD_CACHE.get(key)
    if cached is not None:
        return cached

    from huggingface_hub import hf_hub_download

    downloaded = Path(
        hf_hub_download(
            repo_id=repo_id,
            repo_type="dataset",
            filename=f"data/{table}.parquet",
            revision=revision,
        )
    )
    _DOWNLOAD_CACHE[key] = downloaded
    return downloaded


def load(
    table: str,
    *,
    season: int | None = None,
    version: str = "latest",
    repo_id: str = DEFAULT_REPO_ID,
) -> pd.DataFrame:
    """Load a backbone table as a DataFrame, optionally filtered by season.

    ``version`` is a released tag (e.g. ``"v0.1.0"``) or ``"latest"`` (the
    dataset's default revision). Raises ``ValueError`` for an unknown table
    name, or ``RuntimeError`` wrapping the underlying error for an
    unreachable version/repo.
    """
    if table not in BACKBONE_TABLES:
        raise ValueError(f"Unknown table {table!r}. Valid tables: {', '.join(BACKBONE_TABLES)}")

    revision = _resolve_revision(version)
    try:
        parquet_path = _download_table(repo_id, table, revision)
    except Exception as exc:
        raise RuntimeError(
            f"Could not load {table!r} at version {version!r} from dataset {repo_id!r}: {exc}"
        ) from exc

    con = duckdb.connect()
    posix_path = parquet_path.as_posix()
    if season is not None:
        query = f"SELECT * FROM read_parquet('{posix_path}') WHERE season = ?"
        return con.execute(query, [season]).df()
    return con.execute(f"SELECT * FROM read_parquet('{posix_path}')").df()


__all__ = ["BACKBONE_TABLES", "DEFAULT_REPO_ID", "load"]
