"""Wraps the Chadwick Baseball Bureau's `cwevent`/`cwgame` CLI tools to parse
Retrosheet's raw event files into structured play- and game-level records.

The CLI tools are used directly (already installed on this machine) rather
than the `pychadwick` pip package, which fails to build against modern CMake
(an upstream packaging bug) — see docs/DECISIONS.md ADR-004. Both tools
resolve each game's roster and team files (`{TTT}{year}.ROS`, `TEAM{year}`)
relative to their working directory rather than as explicit arguments, so
they must be run with cwd set to the directory the event files were
extracted into (Retrosheet's per-year zips already bundle the matching
roster/team files alongside the event files, so nothing extra needs fetching).
"""

import io
import shutil
import subprocess
from pathlib import Path

import pandas as pd

CWEVENT_FIELDS = "0-96"
CWEVENT_EXTENDED_FIELDS = "0-66"

REQUIRED_TOOLS = ("cwevent", "cwgame")

INSTALL_HINT = (
    "build from source: https://github.com/chadwickbureau/chadwick "
    "(./configure && make && sudo make install) — the pip package `pychadwick` "
    "does not work here, see docs/DECISIONS.md ADR-004"
)


def missing_tools() -> list[str]:
    """Which of REQUIRED_TOOLS aren't on PATH, if any — used by
    retrosheet_event.health_check() so a missing system dependency shows up
    in `mlb doctor` before a multi-hour bootstrap, not as a cryptic
    FileNotFoundError partway through one."""
    return [tool for tool in REQUIRED_TOOLS if shutil.which(tool) is None]


def _run(tool: str, args: list[str], event_dir: Path) -> pd.DataFrame:
    try:
        result = subprocess.run(
            [tool, *args],
            cwd=event_dir,
            capture_output=True,
            text=True,
        )
    except FileNotFoundError as exc:
        raise RuntimeError(f"{tool} is not installed or not on PATH — {INSTALL_HINT}") from exc
    if result.returncode != 0:
        raise RuntimeError(f"{tool} failed in {event_dir}: {result.stderr.strip()}")
    if not result.stdout.strip():
        raise RuntimeError(f"{tool} produced no output in {event_dir}: {result.stderr.strip()}")
    return pd.read_csv(io.StringIO(result.stdout))


def _event_files(event_dir: Path) -> list[str]:
    # .EV? = full play-by-play; .ED? = deduced play-by-play (reconstructed from
    # newspaper accounts/box scores for seasons where the real record is
    # missing — same record format, same tools, see retrosheet.org/about.html
    # and the connector docstring in connectors/retrosheet_event.py).
    files = sorted(p.name for p in event_dir.glob("*.EV?")) + sorted(
        p.name for p in event_dir.glob("*.ED?")
    )
    if not files:
        raise RuntimeError(f"no event files (*.EV?/*.ED?) found in {event_dir}")
    return files


def run_cwevent(event_dir: Path, year: int) -> pd.DataFrame:
    """Parses every .EVA/.EVN/.EVF/.EVR/.EDA/.EDN file in event_dir into one play-level
    DataFrame. Requests the full field set (base 0-96, extended 0-66) rather
    than a curated subset — this lands in a raw layer table and should stay
    source-faithful and complete, not a hand-picked slice of what cwevent
    can produce."""
    args = ["-y", str(year), "-f", CWEVENT_FIELDS, "-x", CWEVENT_EXTENDED_FIELDS, "-n"]
    return _run("cwevent", [*args, *_event_files(event_dir)], event_dir)


def run_cwgame(event_dir: Path, year: int) -> pd.DataFrame:
    """Parses every .EVA/.EVN/.EVF/.EVR/.EDA/.EDN file in event_dir into one
    game-level DataFrame (date, umpires, attendance, lineups, final score, etc.)."""
    return _run("cwgame", ["-y", str(year), "-n", *_event_files(event_dir)], event_dir)
