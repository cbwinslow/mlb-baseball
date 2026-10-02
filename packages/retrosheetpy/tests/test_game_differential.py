"""The port of ``cwgame`` against the real ``cwgame`` binary, byte for byte.

Both output formats, with the default fields, with every field plus every extended field, and with
synthesised rosters (so the player-name fields run); on every fixture event file and on randomly
damaged copies. Runs only where ``cwgame`` (Chadwick 0.10) is installed.
"""

import random
import shutil
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
from chadwick_tool import build_sanitised, run_clean, run_tool  # noqa: E402
from retrosheetpy.cw.cwgame import game_lines, header_line  # noqa: E402
from retrosheetpy.cw.tools import read_rosters  # noqa: E402
from test_cwbox_differential import synthetic_rosters, year_of  # noqa: E402
from test_reader_differential import damage  # noqa: E402

pytestmark = pytest.mark.skipif(shutil.which("cwgame") is None, reason="needs cwgame on PATH")

FIXTURES = sorted((HERE / "fixtures" / "events").glob("*.evt"))
ALL = tuple(range(85))
EXT = tuple(range(97))

# name: (cwgame arguments, ascii, fields, extended fields)
VARIANTS = {
    "ascii_default": (["-n"], True, tuple(range(84)), ()),
    "fixed_default": (["-ft"], False, tuple(range(84)), ()),
    "ascii_all": (["-n", "-f", "0-84", "-x", "0-96"], True, ALL, EXT),
    "fixed_all": (["-ft", "-f", "0-84", "-x", "0-96"], False, ALL, EXT),
}


def port_output(
    data: bytes,
    ascii_: bool,
    fields: tuple[int, ...],
    ext: tuple[int, ...],
    header: bool,
    support: dict[str, bytes] | None = None,
) -> bytes:
    league = None
    if support:
        league = read_rosters(support[f"TEAM{year_of(data)}"], year_of(data), support.get)
    lines = list(game_lines(data, league, ascii_=ascii_, fields=fields, ext_fields=ext))
    if ascii_ and header:
        lines.insert(0, header_line(fields, ext))
    return "".join(line + "\n" for line in lines).encode("latin-1")


@pytest.mark.parametrize("rosters", [False, True], ids=["no_rosters", "rosters"])
@pytest.mark.parametrize("variant", VARIANTS)
@pytest.mark.parametrize("fixture", FIXTURES, ids=lambda p: p.stem)
def test_fixture_matches_cwgame(fixture: Path, variant: str, rosters: bool) -> None:
    args, ascii_, fields, ext = VARIANTS[variant]
    data = fixture.read_bytes()
    support = synthetic_rosters(data) if rosters else None
    run = run_tool("cwgame", fixture, args, support)
    assert run is not None
    assert run[0] == 0
    header = "-n" in args
    assert run[1] == port_output(data, ascii_, fields, ext, header, support)


def test_damaged_files_match_cwgame(tmp_path: Path) -> None:
    exe = build_sanitised("cwgame", tmp_path)
    if exe is None:
        pytest.skip("needs gcc and the Chadwick sources (CHADWICK_SRC)")
    rng = random.Random(13)
    checked = 0
    args, ascii_, fields, ext = VARIANTS["ascii_all"]
    for fixture in FIXTURES:
        for i in range(25):
            data = bytes(damage(rng, bytearray(fixture.read_bytes())))
            path = tmp_path / f"{fixture.stem}_{i}.evt"
            path.write_bytes(data)
            expected = run_clean(exe, path, args)
            if expected is None:
                continue  # Chadwick exits, crashes or has undefined behaviour here
            try:
                out = port_output(data, ascii_, fields, ext, True)
            except (ValueError, IndexError):
                continue  # the port raises where Chadwick would misbehave silently
            assert expected == out, path.name
            checked += 1
    assert checked > 30
