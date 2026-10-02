"""The port's boxscore builder (``box.c``) against Chadwick's own.

``tests/reference/box_dump.c`` is compiled against the real Chadwick sources and prints every
field of the ``CWBoxscore`` that ``cw_box_create`` builds; ``box_dump.py`` prints the same from the
port. Both must agree on the fixtures and on randomly damaged copies of them, including whether the
C crashes or exits (the port raises ``ValueError`` where Chadwick ``exit(1)``s or dereferences
``NULL``). Runs only where ``gcc`` and the Chadwick sources (``CHADWICK_SRC``) are available.
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
sys.path.insert(0, str(HERE))
from box_dump import dump  # noqa: E402
from test_reader_differential import damage, event_sample  # noqa: E402

FIXTURES = HERE / "fixtures" / "events"
SRC = Path(os.environ.get("CHADWICK_SRC", Path.home() / "workspace/tmp/chadwick/src"))

pytestmark = pytest.mark.skipif(
    shutil.which("gcc") is None or not (SRC / "cwlib" / "box.c").exists(),
    reason="needs gcc and the Chadwick sources (CHADWICK_SRC)",
)

# Records that exercise the substitution, DH and boxscore-file paths of box.c
PIECES = [
    b"sub,x,Nobody,0,3,1\n", b"sub,x,Nobody,1,0,1\n", b"sub,x,Nobody,0,10,11\n",
    b"sub,x,Nobody,0,2,13\n", b"sub,x,Nobody,2,1,1\n", b"sub,x,Nobody,0,1,1\n",
    b"start,x,Nobody,0,3,1\n", b"stat,bline,x,0,3,1,4,1,1,0,0,0,0,0,0,0,0,0,0,0,0,0\n",
    b"stat,pline,x,0,2,3,0,4,1,0,0,0,1,1,0,0,0,0,0,0,0\n", b"stat,dline,x,0,1,5,3,1,0,0,0,0,0\n",
    b"stat,phline,x,7,0\n", b"stat,prline,x,7,0\n", b"stat,tline,0,3,1,0,0\n",
    b"line,0,1,0,2\n", b"event,dpline,0,a,b\n", b"event,tpline,1,a,b,c\n",
]  # fmt: skip


def build(tmp_path_factory, name: str, *flags: str) -> Path:
    out = tmp_path_factory.mktemp(name) / "box_dump"
    cmd = ["gcc", "-O1", "-w", *flags, "-I", str(SRC / "cwlib"), "-I", str(SRC)]
    cmd += [str(HERE / "reference" / "box_dump.c"), *map(str, sorted((SRC / "cwlib").glob("*.c")))]
    subprocess.run([*cmd, "-o", str(out)], check=True, capture_output=True)
    return out


@pytest.fixture(scope="module")
def harness(tmp_path_factory):
    return build(tmp_path_factory, "plain")


@pytest.fixture(scope="module")
def sanitized(tmp_path_factory):
    """The same harness under ASAN/UBSAN: inputs where Chadwick has undefined behaviour are
    skipped, as nothing meaningful can be compared there."""
    try:
        return build(
            tmp_path_factory,
            "san",
            "-fsanitize=address,undefined",
            "-fno-sanitize-recover=all",
        )
    except subprocess.CalledProcessError:
        pytest.skip("this gcc cannot build with sanitizers")


def c_dump(harness: Path, data: bytes, tmp: Path) -> tuple[list[str], bool]:
    path = tmp / "f.evt"
    path.write_bytes(data)
    run = subprocess.run([str(harness), str(path)], capture_output=True)
    return run.stdout.decode("latin-1").splitlines(), run.returncode != 0


def c_is_defined(sanitized: Path, tmp: Path) -> bool:
    env = {**os.environ, "ASAN_OPTIONS": "detect_leaks=0"}
    run = subprocess.run([str(sanitized), str(tmp / "f.evt")], capture_output=True, env=env)
    return run.returncode == 0


@pytest.fixture(autouse=True)
def quiet():
    logging.disable(logging.CRITICAL)
    yield
    logging.disable(logging.NOTSET)


@pytest.mark.parametrize("path", sorted(FIXTURES.glob("*.evt")), ids=lambda p: p.stem)
def test_fixture_boxscore_equals_chadwick(harness, tmp_path, path):
    data = path.read_bytes()
    expected = c_dump(harness, data, tmp_path)
    assert expected[1] is False
    assert dump(data) == expected


def check(harness, sanitized, tmp_path, data: bytes) -> bool:
    """Compare on ``data`` unless Chadwick has undefined behaviour on it; True if compared."""
    expected = c_dump(harness, data, tmp_path)
    if not c_is_defined(sanitized, tmp_path):
        return False
    assert dump(data) == expected, data
    return True


def test_damaged_files_build_like_chadwick(harness, sanitized, tmp_path):
    rnd = random.Random(5)
    files = [p.read_bytes() for p in sorted(FIXTURES.glob("*.evt"))]
    compared = 0
    for _ in range(400):
        d = event_sample(rnd, files)
        for _ in range(rnd.randint(0, 3)):
            at = d.find(b"\n", rnd.randrange(len(d))) + 1
            d[at:at] = rnd.choice(PIECES)
        if rnd.random() < 0.5:
            d = damage(rnd, d)
        if not d.startswith(b"id,"):
            d[0:0] = b"id,X\n"
        compared += check(harness, sanitized, tmp_path, bytes(d))
    assert compared > 200


PLAYS = [
    b"NP", b"K", b"S8", b"HR", b"W", b"SB2", b"WP.1-2", b"6-4-3/GDP", b"E5", b"BK.1-2",
    b"PO1(13)", b"CS2(24)", b"FC5/G.1X2(54)", b"64(1)3/GDP", b"S9.2-H;1-3", b"DGR",
    b"K+WP.B-1", b"SF8.3-H",
]  # fmt: skip


def mutate(rnd: random.Random, data: bytes) -> bytes:
    """Edit slots, teams and positions of sub/start records, swap player ids, replace plays."""
    lines = data.split(b"\n")

    def indexes() -> list[int]:
        return [i for i, x in enumerate(lines) if x.startswith((b"sub,", b"start,", b"play,"))]

    for _ in range(rnd.randint(1, 4)):
        i = rnd.choice(indexes())
        parts, kind = lines[i].split(b","), rnd.randrange(5)
        if lines[i].startswith(b"play,") and len(parts) >= 7:
            if kind == 0:
                parts[6] = rnd.choice(PLAYS)
            elif kind == 1:
                parts[3] = b"nobody01"
            elif kind == 2 and parts[2] in (b"0", b"1"):
                parts[2] = b"1" if parts[2] == b"0" else b"0"
            elif kind == 3:
                del lines[i]
                continue
            elif kind == 4:
                lines.insert(i, lines[i])
                continue
            lines[i] = b",".join(parts)
        elif len(parts) >= 6 and not lines[i].startswith(b"play,"):
            if kind == 0:
                parts[3] = str(rnd.randint(0, 2)).encode()
            elif kind == 1:
                parts[4] = str(rnd.randint(0, 10)).encode()
            elif kind == 2:
                parts[5] = str(rnd.randint(0, 13)).encode()
            elif kind == 3:
                other = lines[rnd.choice(indexes())].split(b",")
                if len(other) >= 6 and not other[0] == b"play":
                    parts[1] = other[1]
            else:
                del lines[i]
                continue
            lines[i] = b",".join(parts)
    return b"\n".join(lines)


def test_mutated_lineups_and_plays_build_like_chadwick(harness, sanitized, tmp_path):
    rnd = random.Random(1)
    files = [p.read_bytes() for p in sorted(FIXTURES.glob("*.evt"))]
    compared = sum(
        check(harness, sanitized, tmp_path, mutate(rnd, rnd.choice(files))) for _ in range(300)
    )
    assert compared > 200
