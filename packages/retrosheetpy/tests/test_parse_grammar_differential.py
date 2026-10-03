"""The play parser against Chadwick's ``cw_parse_event`` on grammar-generated plays.

``reference/parse_grammar.py`` builds plays from every token the C parser compares against (error
and trajectory modifiers, running plays, advances, malformed forms). The harness is built under
ASAN/UBSAN with strict bounds checks, so a play that makes Chadwick store past the end of one of
its fixed arrays (undefined; the port's arrays are larger) is skipped, not compared.
"""

import random
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE / "reference"))
from chadwick_tool import SRC  # noqa: E402
from parse_fuzz import compare  # noqa: E402
from parse_grammar import generate  # noqa: E402

pytestmark = pytest.mark.skipif(
    shutil.which("gcc") is None or not (SRC / "cwlib" / "parse.c").exists(),
    reason="needs gcc and the Chadwick sources (CHADWICK_SRC)",
)


@pytest.fixture(scope="module")
def harness(tmp_path_factory: pytest.TempPathFactory) -> Path:
    out = tmp_path_factory.mktemp("parse_dump") / "parse_dump"
    cmd = [
        "gcc",
        "-w",
        "-g",
        "-fsanitize=address,undefined,bounds-strict",
        "-fno-sanitize-recover=all",
    ]
    cmd += ["-I", str(SRC / "cwlib"), "-I", str(SRC), str(HERE / "reference" / "parse_dump.c")]
    cmd += [*map(str, sorted((SRC / "cwlib").glob("*.c"))), "-o", str(out)]
    subprocess.run(cmd, check=True, capture_output=True)
    return out


@pytest.mark.parametrize("seed", [1, 2, 3])
def test_grammar_plays_parse_like_chadwick(harness: Path, seed: int) -> None:
    corpus = generate(random.Random(seed), 3000)
    compared, diffs, skipped = compare(corpus, str(harness))
    assert not diffs, "\n".join(diffs[:3])
    assert compared > 2500, (compared, skipped)
