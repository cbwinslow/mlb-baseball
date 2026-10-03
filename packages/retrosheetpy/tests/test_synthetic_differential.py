"""All six tools against the real Chadwick on synthetic games.

``reference/synth_games.py`` writes random well-formed games (and some deliberately broken ones)
that reach code real seasons never do: ``padj``/``badj`` hand records, switch hitters, backward
runner advances, pinch hitters and runners, roster-less players, the DH rules, suspended games,
box-score-only files. Every tool runs with several option sets, by the real program and by
``python -m retrosheetpy.cw``: stdout, stderr and exit status must agree. Runs where the C
crashes or reads uninitialised memory are skipped (the port raises or defines the value).
"""

import sys
from pathlib import Path

import pytest

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE / "reference"))
from chadwick_tool import real_tool  # noqa: E402
from synth_check import CASES, one  # noqa: E402

TOOLS = sorted({tool for tool, _ in CASES})

pytestmark = pytest.mark.skipif(
    any(real_tool(tool) is None for tool in TOOLS), reason="needs the Chadwick tools on PATH"
)


@pytest.mark.parametrize("seed", range(1, 25))
def test_synthetic_games_match_chadwick(seed: int) -> None:
    _, runs, bad, crashed, uninit = one((seed, None, None, None))
    assert not bad, "\n".join(bad)
    assert runs - len(crashed) - len(uninit) > 0
