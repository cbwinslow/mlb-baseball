"""The port's ``cw_game_lint`` (``lint.c``) against Chadwick's own.

``tests/reference/lint_dump.c`` is compiled against the real Chadwick sources and prints, per game,
the stderr messages and the result; ``lint_dump.py`` prints the same from the port. Run on the
fixtures and on damaged and mutated copies (which trip the starter, DP/TP, empty-base and overtaking
checks). Inputs where Chadwick has undefined behaviour are skipped (ASAN/UBSAN build). Runs only
where ``gcc`` and the Chadwick sources (``CHADWICK_SRC``) are available.
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
from lint_dump import dump  # noqa: E402
from test_box_differential import PIECES, mutate  # noqa: E402
from test_reader_differential import damage, event_sample  # noqa: E402

FIXTURES = HERE / "fixtures" / "events"
SRC = Path(os.environ.get("CHADWICK_SRC", Path.home() / "workspace/tmp/chadwick/src"))

pytestmark = pytest.mark.skipif(
    shutil.which("gcc") is None or not (SRC / "cwlib" / "lint.c").exists(),
    reason="needs gcc and the Chadwick sources (CHADWICK_SRC)",
)


def build(tmp_path_factory, name: str, *flags: str) -> Path:
    out = tmp_path_factory.mktemp(name) / "lint_dump"
    cmd = ["gcc", "-O1", "-w", *flags, "-I", str(SRC / "cwlib"), "-I", str(SRC)]
    cmd += [str(HERE / "reference" / "lint_dump.c"), *map(str, sorted((SRC / "cwlib").glob("*.c")))]
    subprocess.run([*cmd, "-o", str(out)], check=True, capture_output=True)
    return out


@pytest.fixture(scope="module")
def harness(tmp_path_factory):
    return build(tmp_path_factory, "plain")


@pytest.fixture(scope="module")
def sanitized(tmp_path_factory):
    try:
        return build(
            tmp_path_factory, "san", "-fsanitize=address,undefined", "-fno-sanitize-recover=all"
        )
    except subprocess.CalledProcessError:
        pytest.skip("this gcc cannot build with sanitizers")


def c_dump(harness: Path, data: bytes, tmp: Path) -> tuple[list[str], bool]:
    path = tmp / "f.evt"
    path.write_bytes(data)
    run = subprocess.run([str(harness), str(path)], capture_output=True)
    text = run.stdout.decode("latin-1")
    # split on "\n" only: warnings echo records that may hold "\r"
    return (text[:-1] if text.endswith("\n") else text).split(
        "\n"
    ) if text else [], run.returncode != 0


def c_is_defined(sanitized: Path, tmp: Path) -> bool:
    env = {**os.environ, "ASAN_OPTIONS": "detect_leaks=0"}
    run = subprocess.run([str(sanitized), str(tmp / "f.evt")], capture_output=True, env=env)
    return run.returncode == 0


@pytest.fixture(autouse=True)
def restore_logging():
    yield
    logging.disable(logging.NOTSET)


@pytest.mark.parametrize("path", sorted(FIXTURES.glob("*.evt")), ids=lambda p: p.stem)
def test_fixture_lint_equals_chadwick(harness, tmp_path, path):
    data = path.read_bytes()
    expected = c_dump(harness, data, tmp_path)
    assert expected[1] is False
    assert dump(data) == expected


def check(harness, sanitized, tmp_path, data: bytes) -> bool:
    expected = c_dump(harness, data, tmp_path)
    if not c_is_defined(sanitized, tmp_path):
        return False
    got = dump(data)
    if got != expected:
        i = next(
            (i for i, (a, b) in enumerate(zip(got[0], expected[0], strict=False)) if a != b), -1
        )
        raise AssertionError(f"differs at line {i}; got {got[0][-3:]} expected {expected[0][-3:]}")
    return True


def test_damaged_files_lint_like_chadwick(harness, sanitized, tmp_path):
    rnd = random.Random(11)
    files = [p.read_bytes() for p in sorted(FIXTURES.glob("*.evt"))]
    compared = 0
    for _ in range(250):
        d = event_sample(rnd, files)
        for _ in range(rnd.randint(0, 3)):
            at = d.find(b"\n", rnd.randrange(len(d))) + 1
            d[at:at] = rnd.choice(PIECES)
        if rnd.random() < 0.5:
            d = damage(rnd, d)
        if not d.startswith(b"id,"):
            d[0:0] = b"id,X\n"
        compared += check(harness, sanitized, tmp_path, bytes(d))
    assert compared > 150


def test_mutated_lineups_and_plays_lint_like_chadwick(harness, sanitized, tmp_path):
    rnd = random.Random(2)
    files = [p.read_bytes() for p in sorted(FIXTURES.glob("*.evt"))]
    compared = 0
    failures = 0
    for _ in range(250):
        data = mutate(rnd, rnd.choice(files))
        expected = c_dump(harness, data, tmp_path)
        failures += any(line == "lint=0" for line in expected[0])
        compared += check(harness, sanitized, tmp_path, data)
    assert compared > 150
    assert failures > 20, "the mutations should exercise the failing checks"
