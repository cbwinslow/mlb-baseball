"""The port of ``cwcomment`` against the real ``cwcomment`` binary, byte for byte.

Both output formats, on every fixture event file and on randomly damaged copies of them.
Runs only where ``cwcomment`` (Chadwick 0.10) is installed.
"""

import random
import shutil
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
from chadwick_tool import run_tool  # noqa: E402
from retrosheetpy.cw.comment import comment_lines, header_line  # noqa: E402
from test_reader_differential import damage  # noqa: E402

pytestmark = pytest.mark.skipif(shutil.which("cwcomment") is None, reason="needs cwcomment on PATH")

FIXTURES = sorted((HERE / "fixtures" / "events").glob("*.evt"))


def port_output(data: bytes, ascii_: bool) -> bytes:
    head = header_line() + "\n" if ascii_ else ""
    return (head + "".join(line + "\n" for line in comment_lines(data, ascii_=ascii_))).encode(
        "latin-1"
    )


@pytest.mark.parametrize("ascii_", [True, False], ids=["ascii", "fixed"])
@pytest.mark.parametrize("fixture", FIXTURES, ids=lambda p: p.stem)
def test_fixture_matches_cwcomment(fixture: Path, ascii_: bool) -> None:
    run = run_tool("cwcomment", fixture, ["-n"] if ascii_ else ["-ft"])
    assert run is not None
    assert run[0] == 0
    assert run[1] == port_output(fixture.read_bytes(), ascii_)


def test_damaged_files_match_cwcomment(tmp_path: Path) -> None:
    rng = random.Random(7)
    checked = 0
    for fixture in FIXTURES:
        for i in range(20):
            data = bytes(damage(rng, bytearray(fixture.read_bytes())))
            path = tmp_path / f"{fixture.stem}_{i}.evt"
            path.write_bytes(data)
            run = run_tool("cwcomment", path, ["-n"])
            assert run is not None
            try:
                out = port_output(data, True)
            except (ValueError, IndexError):
                continue  # Chadwick exits or reads out of bounds here (undefined); the port raises
            if run[0] == 0:  # Chadwick crashed otherwise: undefined, nothing to compare
                assert run[1] == out, path.name
                checked += 1
    assert checked > 50
