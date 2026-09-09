"""Where the local DuckDB feature database lives, and how callers find it.

`mlb build` writes it, `mlb verify` and :func:`mlb_research.get_historical_features`
read it. One file holds every ``feature_version``. Resolution order, highest
precedence first:

1. an explicit path passed by the caller (``--db`` on the CLI, ``db=`` in the API);
2. the ``MLB_DUCKDB_PATH`` environment variable;
3. ``~/.mlb/mlb.duckdb``.

See ``openspec/changes/feature-store-v1/`` (ADR: features live in DuckDB).
"""

from __future__ import annotations

import os
from pathlib import Path

ENV_VAR = "MLB_DUCKDB_PATH"
DEFAULT_PATH = Path.home() / ".mlb" / "mlb.duckdb"


def resolve_db_path(explicit: str | os.PathLike[str] | None = None) -> Path:
    """Return the DuckDB feature-database path, and ensure its parent exists.

    ``explicit`` (a ``--db`` argument or an API ``db=`` keyword) wins; then
    ``$MLB_DUCKDB_PATH``; then ``~/.mlb/mlb.duckdb``. The parent directory is
    created if missing so a first ``mlb build`` does not fail on a fresh machine.
    The file itself is not created here.
    """
    if explicit is not None:
        chosen = Path(explicit).expanduser()
    elif os.environ.get(ENV_VAR):
        chosen = Path(os.environ[ENV_VAR]).expanduser()
    else:
        chosen = DEFAULT_PATH

    chosen = chosen.resolve()
    chosen.parent.mkdir(parents=True, exist_ok=True)
    return chosen
