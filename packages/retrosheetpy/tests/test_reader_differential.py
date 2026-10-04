"""The port's reader (``cw_game_read``, ``cw_strtok``, ``fgets`` framing) against Chadwick's own.

``tests/reference/reader_dump.c`` is compiled against the real Chadwick sources and prints every
field of the ``CWGame`` it reads; ``reader_dump.py`` prints the same from the port. Both must
agree on the fixtures and on randomly damaged copies of them (quotes, CRLF, NULs, long lines,
cut files, stray records). Runs only where ``gcc`` and the Chadwick sources
(``CHADWICK_SRC``, default ``~/workspace/tmp/chadwick/src``) are available.
"""

import logging
import os
import random
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE / "reference"))
from reader_dump import MODES, dump  # noqa: E402

FIXTURES = HERE / "fixtures" / "events"
SRC = Path(os.environ.get("CHADWICK_SRC", Path.home() / "workspace/tmp/chadwick/src"))

pytestmark = pytest.mark.skipif(
    shutil.which("gcc") is None or not (SRC / "cwlib" / "game.c").exists(),
    reason="needs gcc and the Chadwick sources (CHADWICK_SRC)",
)

PIECES = [
    b'"', b",", b"\r", b"\n", b" ", b"\t", b"\0", b"\xe9", b"\\", b"|", b"x", b"1", b"-",
    b"id,", b'com,"ej,a,b,c,d"\n', b'com,"umpchange,1,2,3"\n', b"data,er,x,1\n",
    b"stat,a,b, c\n", b"line,a,,b\n", b"event,a, b\n", b"badj,x,\n", b"padj,p,L\n",
    b"radj,r,2\n", b"ladj,1,3\n", b"presadj,p,2\n", b"presadj,p,9\n", b"cw:itb,r,2\n",
    b"zzz\n", b"play,1,0,x,??,,NP\n",
]  # fmt: skip


@pytest.fixture(scope="module")
def harness(tmp_path_factory):
    out = tmp_path_factory.mktemp("harness") / "reader_dump"
    cmd = ["gcc", "-O1", "-w", "-I", str(SRC / "cwlib"), "-I", str(SRC)]
    cmd += [
        str(HERE / "reference" / "reader_dump.c"),
        *map(str, sorted((SRC / "cwlib").glob("*.c"))),
    ]
    subprocess.run([*cmd, "-o", str(out)], check=True)
    return out


def c_dump(harness: Path, data: bytes, tmp: Path, mode: str = "game") -> str | None:
    path = tmp / "f.evt"
    path.write_bytes(data)
    run = subprocess.run([str(harness), str(path), mode], capture_output=True)
    if run.returncode != 0:  # Chadwick crashed on this file (e.g. a sub before any play)
        return None
    return run.stdout.decode("latin-1").rstrip("\n")


@pytest.fixture(autouse=True)
def quiet():
    logging.disable(logging.CRITICAL)
    yield
    logging.disable(logging.NOTSET)


@pytest.mark.parametrize("path", sorted(FIXTURES.glob("*.evt")), ids=lambda p: p.stem)
def test_fixture_read_equals_chadwick(harness, tmp_path, path):
    data = path.read_bytes()
    assert "\n".join(dump(data)) == c_dump(harness, data, tmp_path)


def damage(rnd: random.Random, d: bytearray) -> bytearray:
    for _ in range(rnd.randint(1, 8)):
        kind, pos = rnd.randrange(4), rnd.randrange(len(d) + 1)
        if kind == 0:
            d[pos:pos] = rnd.choice(PIECES)
        elif kind == 1:
            del d[pos : pos + rnd.randint(1, 30)]
        elif kind == 2:
            d[pos:pos] = b"A" * rnd.choice([500, 1023, 1024, 2000])
        else:
            d = d[:pos]
    return d


def event_sample(rnd: random.Random, files: list[bytes]) -> bytearray:
    d = bytearray(rnd.choice(files))
    if len(d) > 6000:
        start = d.find(b"\nid,", rnd.randrange(len(d) - 6000)) + 1
        d = d[start : start + 6000]
    return d


def test_damaged_files_read_like_chadwick(harness, tmp_path):
    rnd = random.Random(7)
    files = [p.read_bytes() for p in sorted(FIXTURES.glob("*.evt"))]
    compared = 0
    for _ in range(300):
        d = damage(rnd, event_sample(rnd, files))
        if not d.startswith(b"id,"):
            d[0:0] = b"id,X\n"
        expected = c_dump(harness, bytes(d), tmp_path)
        if expected is None:
            continue
        assert "\n".join(dump(bytes(d))) == expected, bytes(d)
        compared += 1
    assert compared > 250


def test_scorebook_read_equals_chadwick(harness, tmp_path):
    """``cw_scorebook_read``: leading comments, junk before the first ``id``, empty files"""
    rnd = random.Random(11)
    files = [p.read_bytes() for p in sorted(FIXTURES.glob("*.evt"))]
    heads = [
        b"",
        b'com,"a note"\n',
        b"zzz\n",
        b'com,"x"\ncom,"y"\nid,Q\n',
        b"\n",
        b"x" * 300 + b"\n",
    ]
    compared = 0
    for _ in range(300):
        d = bytearray(rnd.choice(heads) + bytes(event_sample(rnd, files)))
        if rnd.random() < 0.8:
            d = damage(rnd, d)
        expected = c_dump(harness, bytes(d), tmp_path, "book")
        if expected is None:
            continue
        assert "\n".join(MODES["book"](bytes(d))) == expected, bytes(d)
        compared += 1
    assert compared > 250


ROSTERS = sorted((HERE / "reference" / "rosters").glob("*/*"))


@pytest.mark.parametrize("path", ROSTERS, ids=lambda p: f"{p.parent.name}/{p.name}")
def test_roster_and_team_files_equal_chadwick(harness, tmp_path, path):
    mode = "league" if path.name.startswith("TEAM") else "roster"
    data = path.read_bytes()
    assert "\n".join(MODES[mode](data)) == c_dump(harness, data, tmp_path, mode)


@pytest.mark.parametrize("mode", ["roster", "league"])
def test_damaged_roster_files_read_like_chadwick(harness, tmp_path, mode):
    rnd = random.Random(3)
    files = [p.read_bytes() for p in ROSTERS if p.name.startswith("TEAM") == (mode == "league")]
    for _ in range(300):
        d = bytes(damage(rnd, bytearray(rnd.choice(files))))
        assert "\n".join(MODES[mode](d)) == c_dump(harness, d, tmp_path, mode), d
