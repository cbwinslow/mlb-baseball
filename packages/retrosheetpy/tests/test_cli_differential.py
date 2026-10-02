"""The command-line drivers against the real tools: stdout, stderr and exit status, byte for byte.

Each case runs the installed Chadwick binary and ``retrosheetpy.cw.cli.main`` in scratch
directories holding the same files (an event file, a team file and rosters synthesised from it)
and compares everything. Runs only where the Chadwick tools (0.10) are installed.
"""

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
from retrosheetpy.cw.cli import IO, TOOLS, main  # noqa: E402
from test_cwbox_differential import synthetic_rosters, year_of  # noqa: E402

FIXTURES = HERE / "fixtures" / "events"
EVENT = (FIXTURES / "regular_2007.evt").read_bytes()
SECOND = (FIXTURES / "negro_league.evt").read_bytes()

pytestmark = pytest.mark.skipif(
    any(shutil.which(t) is None for t in TOOLS), reason="needs the Chadwick tools on PATH"
)

ALL_TOOLS = sorted(TOOLS)

# (arguments after the tool name; event files are named a.evt and b.evt)
CASES = {
    "plain": ["-y", "2007", "a.evt"],
    "quiet": ["-q", "-y", "2007", "a.evt"],
    "two_files": ["-y", "2007", "a.evt", "b.evt"],
    "missing_file": ["-q", "-y", "2007", "nothere.evt", "a.evt"],
    "empty_file": ["-q", "-y", "2007", "empty.evt"],
    "no_year": ["a.evt"],
    "help": ["-h"],
    "list_fields": ["-d"],
    "bad_option": ["-z"],
    "game_id": ["-q", "-y", "2007", "-i", "TOR200705310", "a.evt"],
    "dates": ["-q", "-y", "2007", "-s", "0601", "-e", "0630", "a.evt"],
    "header": ["-q", "-y", "2007", "-n", "a.evt"],
    "fixed": ["-q", "-y", "2007", "-ft", "a.evt"],
    "ascii": ["-q", "-y", "2007", "-a", "a.evt"],
    "fields": ["-q", "-y", "2007", "-n", "-f", "0-3,7,9", "a.evt"],
    "fields_bad_range": ["-q", "-y", "2007", "-f", "5-2", "a.evt"],
    "fields_too_big": ["-q", "-y", "2007", "-f", "999", "a.evt"],
    "fields_garbage": ["-q", "-y", "2007", "-f", "1,,2", "a.evt"],
    "fields_missing_arg": ["-q", "-y", "2007", "a.evt", "-f"],
    "ext_fields": ["-q", "-y", "2007", "-n", "-x", "0-3", "a.evt"],
    "xml": ["-q", "-y", "2007", "-X", "a.evt"],
    "sportsml_unfixed": ["-q", "-y", "2007", "-S", "-X", "a.evt"],
    "year_five_chars": ["-q", "-y", "20071", "a.evt"],
}


def scratch(tmp: Path, name: str) -> Path:
    work = tmp / name
    work.mkdir()
    (work / "a.evt").write_bytes(EVENT)
    (work / "b.evt").write_bytes(SECOND)
    (work / "empty.evt").write_bytes(b"")
    for filename, content in synthetic_rosters(EVENT).items():
        (work / filename).write_bytes(content)
    assert year_of(EVENT) == "2007"
    return work


def run_real(tool: str, args: list[str], work: Path) -> tuple[int, bytes, bytes]:
    exe = shutil.which(tool)
    assert exe is not None
    run = subprocess.run([exe, *args], cwd=work, capture_output=True, check=False)
    return run.returncode, run.stdout, run.stderr


def run_port(tool: str, args: list[str], work: Path) -> tuple[int, bytes, bytes]:
    exe = shutil.which(tool)
    out: list[str] = []
    err: list[str] = []
    here = Path.cwd()
    os.chdir(work)
    try:
        status = main(TOOLS[tool], [exe or tool, *args], IO(out.append, err.append))
    finally:
        os.chdir(here)
    return status, "".join(out).encode("latin-1"), "".join(err).encode("latin-1")


@pytest.mark.parametrize("case", CASES)
@pytest.mark.parametrize("tool", ALL_TOOLS)
def test_cli_matches_chadwick(tmp_path: Path, tool: str, case: str) -> None:
    args = CASES[case]
    real = run_real(tool, args, scratch(tmp_path, "real"))
    port = run_port(tool, args, scratch(tmp_path, "port"))
    assert real[0] == port[0], (real, port)
    assert real[2] == port[2], "stderr"
    assert real[1] == port[1], "stdout"
