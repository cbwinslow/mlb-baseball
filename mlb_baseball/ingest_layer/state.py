"""Where the ingestion layer keeps its throwaway ``dlt`` working folders (D10).

Each ``land()`` call uses a fresh folder under ``~/.mlb/dlt`` (or ``$MLB_HOME/dlt``) and
deletes it afterwards, so state is never needed to resume: losing the folder loses nothing,
the ledger in PostgreSQL is the memory. A folder that is still there was left by a killed run.
"""

import os
from pathlib import Path


def state_dir() -> Path:
    base = Path(os.environ.get("MLB_HOME") or Path.home() / ".mlb")
    return base / "dlt"


def leftover_runs() -> list[Path]:
    """Folders left behind by runs that did not finish (informational)."""
    root = state_dir()
    return sorted(p for p in root.iterdir() if p.is_dir()) if root.is_dir() else []
