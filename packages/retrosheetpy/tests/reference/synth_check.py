# ruff: noqa: E501
"""Synthetic games: the real Chadwick tools against the port, stdout + stderr + exit status.

Development-time only.  ``synth_games.py`` writes random well-formed games that reach Chadwick
code real seasons never do (hand records, backward advances, pinch hitters, roster-less players).
Every tool is run with several option sets on the same files, by the real program and by
``python -m retrosheetpy.cw``.

    python synth_check.py FIRST_SEED LAST_SEED [--gcov-bin DIR] [--cov PREFIX] [--keep DIR]

``--gcov-bin`` also runs gcov-instrumented tools (``scratchpad/gcovbuild.sh``) over the files, to
see which lines of Chadwick the games reach; ``--cov PREFIX`` runs the port under ``coverage``
(data files ``PREFIX.*``); ``--keep DIR`` saves the files of every disagreement.
"""

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))

from chadwick_tool import real_tool  # noqa: E402
from synth_games import YEAR, make_file  # noqa: E402


def _real(tool: str) -> str:
    # Never fall back to a bare name: inside the venv that is the port, not the C tool.
    found = real_tool(tool)
    if found is None:
        raise SystemExit(f"real Chadwick {tool} not found (set CHADWICK_BIN)")
    return str(found)


CASES: list[tuple[str, list[str]]] = [
    ("cwevent", ["-n"]),
    ("cwevent", ["-n", "-f", "0-96", "-x", "0-66"]),
    ("cwevent", ["-ft", "-f", "0-96", "-x", "0-66"]),
    ("cwgame", ["-n", "-f", "0-84", "-x", "0-96"]),
    ("cwgame", ["-ft", "-f", "0-84", "-x", "0-96"]),
    ("cwbox", []),
    ("cwbox", ["-X"]),
    ("cwdaily", ["-n"]),
    ("cwdaily", ["-ft"]),
    ("cwsub", ["-n"]),
    ("cwcomment", ["-n"]),
]


def run(cmd: list[str], work: Path, perturb: int = 0) -> tuple[int, bytes, bytes]:
    env = {**os.environ, "MALLOC_PERTURB_": str(perturb)} if perturb else None
    done = subprocess.run(cmd, cwd=work, capture_output=True, check=False, env=env)
    return done.returncode, done.stdout, done.stderr


def normalise(tool: str, args: list[str], out: bytes) -> bytes:
    if tool == "cwbox" and "-X" in args:
        import re

        return re.sub(rb' pb="[^"]*"', b"", out)
    return out


def one(
    spec: tuple[int, Path | None, str | None, Path | None],
) -> tuple[int, int, list[str], list[str], list[str]]:
    seed, gcov_bin, cov, keep = spec
    data, support = make_file(seed)
    bad: list[str] = []
    crashed: list[str] = []
    uninit: list[str] = []
    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp)
        (work / f"{YEAR}XXX.EVN").write_bytes(data)
        (work / f"TEAM{YEAR}").write_bytes(b"")
        for name, content in support.items():
            (work / name).write_bytes(content)
        for tool, args in CASES:
            argv = ["-q", "-y", str(YEAR), *args, f"{YEAR}XXX.EVN"]
            real = run([_real(tool), *argv], work)
            port_cmd = [sys.executable, "-m", "retrosheetpy.cw", tool, *argv]
            if cov:
                port_cmd = [
                    sys.executable, "-m", "coverage", "run", "--parallel-mode",
                    f"--data-file={cov}", "--branch", "--include=*/retrosheetpy/*",
                    "-m", "retrosheetpy.cw", tool, *argv,
                ]  # fmt: skip
            port = run(port_cmd, work)
            if gcov_bin is not None:
                run([str(gcov_bin / tool), *argv], work)
            if real[0] < 0:
                crashed.append(
                    f"seed {seed}: {tool} {' '.join(args)} (C killed by signal {-real[0]})"
                )
                continue
            if (
                real[0] != port[0]
                or real[2] != port[2]
                or normalise(tool, args, real[1]) != normalise(tool, args, port[1])
            ):
                again = run([_real(tool), *argv], work, perturb=85)
                if again[:2] != real[:2]:
                    uninit.append(f"seed {seed}: {tool} {' '.join(args)}")
                    continue
                bad.append(f"seed {seed}: {tool} {' '.join(args)} (status {real[0]} vs {port[0]})")
                if keep:
                    dest = keep / f"seed{seed}"
                    shutil.copytree(work, dest, dirs_exist_ok=True)
    return seed, len(CASES), bad, crashed, uninit


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("first", type=int)
    ap.add_argument("last", type=int)
    ap.add_argument("--gcov-bin", type=Path)
    ap.add_argument("--cov")
    ap.add_argument("--keep", type=Path)
    ap.add_argument("--jobs", type=int, default=8)
    a = ap.parse_args()
    if a.keep:
        a.keep.mkdir(parents=True, exist_ok=True)
    specs = [(s, a.gcov_bin, a.cov, a.keep) for s in range(a.first, a.last + 1)]
    runs = diffs = crashes = reads = 0
    with ThreadPoolExecutor(a.jobs) as pool:
        for _, n, bad, crashed, uninit in pool.map(one, specs):
            runs += n
            diffs += len(bad)
            crashes += len(crashed)
            reads += len(uninit)
            for line in bad:
                print("DIFF", line, flush=True)
    print(
        f"{len(specs)} seeds, {runs} runs, {diffs} differences, {crashes} runs where the C crashed and {reads} where its output changes with the allocator fill (uninitialised memory); both skipped"
    )


if __name__ == "__main__":
    main()
