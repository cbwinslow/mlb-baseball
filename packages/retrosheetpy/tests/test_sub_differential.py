"""The port of ``cwsub`` against the real ``cwsub`` binary, byte for byte.

Both output formats, on every fixture event file and on randomly damaged copies of them.
Runs only where ``cwsub`` (Chadwick 0.10) is installed.
"""

import random
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
from chadwick_tool import build_sanitised, real_tool, run_clean, run_tool  # noqa: E402
from retrosheetpy.cw.sub import header_line, sub_lines  # noqa: E402
from test_reader_differential import damage  # noqa: E402

pytestmark = pytest.mark.skipif(real_tool("cwsub") is None, reason="needs cwsub on PATH")

FIXTURES = sorted((HERE / "fixtures" / "events").glob("*.evt"))


def port_output(data: bytes, ascii_: bool) -> bytes:
    head = header_line() + "\n" if ascii_ else ""
    return (head + "".join(line + "\n" for line in sub_lines(data, ascii_=ascii_))).encode(
        "latin-1"
    )


@pytest.mark.parametrize("ascii_", [True, False], ids=["ascii", "fixed"])
@pytest.mark.parametrize("fixture", FIXTURES, ids=lambda p: p.stem)
def test_fixture_matches_cwsub(fixture: Path, ascii_: bool) -> None:
    run = run_tool("cwsub", fixture, ["-n"] if ascii_ else ["-ft"])
    assert run is not None
    assert run[0] == 0
    assert run[1] == port_output(fixture.read_bytes(), ascii_)


def test_damaged_files_match_cwsub(tmp_path: Path) -> None:
    exe = build_sanitised("cwsub", tmp_path)
    if exe is None:
        pytest.skip("needs gcc and the Chadwick sources (CHADWICK_SRC)")
    rng = random.Random(7)
    checked = 0
    for fixture in FIXTURES:
        for i in range(20):
            data = bytes(damage(rng, bytearray(fixture.read_bytes())))
            path = tmp_path / f"{fixture.stem}_{i}.evt"
            path.write_bytes(data)
            expected = run_clean(exe, path, ["-n"])
            if expected is None:
                continue  # Chadwick exits, crashes or has undefined behaviour here
            try:
                out = port_output(data, True)
            except (ValueError, IndexError):
                continue  # the port raises where Chadwick would misbehave silently
            assert expected == out, path.name
            checked += 1
    assert checked > 30
