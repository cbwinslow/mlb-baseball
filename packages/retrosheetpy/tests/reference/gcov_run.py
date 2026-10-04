"""Run only the real (gcov-instrumented) Chadwick tools over the same inputs and option sets as
``cli_all_years.py`` and ``cli_sweep.py``, so ``gcov`` can show which lines of Chadwick the data
reaches. Development-time only.

    python gcov_run.py ZIPDIR GCOV_BIN [--jobs 16]

The instrumented tools write ``.gcda`` files next to their object files when they exit.
"""

import argparse
import random
import re
import subprocess
import sys
import tempfile
import zipfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import cli_sweep  # noqa: E402
from cli_all_years import EVENT, OPTION_SETS, seasons  # noqa: E402


def one(spec: tuple[int, Path, str, list[str], Path, int]) -> int:
    year, zip_path, tool, args, bin_dir, n_files = spec
    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp)
        files: list[str] = []
        ids: list[str] = []
        with zipfile.ZipFile(zip_path) as zf:
            for name in sorted(zf.namelist()):
                base = Path(name).name
                keep = base.upper() == f"TEAM{year}" or (
                    base.startswith(str(year))
                    and (EVENT.search(base) or base.upper().endswith(".ROS"))
                )
                if not keep:
                    continue
                data = zf.read(name)
                if EVENT.search(base):
                    if len(files) >= n_files:
                        continue
                    files.append(base)
                    ids += re.findall(r"^id,([A-Z0-9]{12})", data.decode("latin-1"), re.M)
                (work / base).write_bytes(data)
        game = ids[len(ids) // 2] if ids else "XXX000000000"
        other = ids[-1] if ids else "XXX000000000"
        argv = [a.format(year=year, game=game, game_other=other) for a in args]
        stop = "-h" in argv or "-d" in argv
        done = subprocess.run(
            [str(bin_dir / tool), *argv, *([] if stop else files)],
            cwd=work,
            capture_output=True,
            check=False,
        )
        return done.returncode


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("zip_dir", type=Path)
    parser.add_argument("bin_dir", type=Path)
    parser.add_argument("--jobs", type=int, default=16)
    args = parser.parse_args()
    available = seasons(args.zip_dir)
    specs: list[tuple[int, Path, str, list[str], Path, int]] = []
    for year, zip_path in sorted(available.items()):
        for tool, extra in OPTION_SETS.values():
            specs.append((year, zip_path, tool, ["-y", "{year}", *extra], args.bin_dir, 99))
    rng = random.Random(1)
    for year in (1910, 1950, 1976, 1998, 2007, 2020, 2025):
        for tool in cli_sweep.OPTIONS:
            for case in cli_sweep.cases(tool, rng, 60):
                base = [] if "-y" in case or case in cli_sweep.STANDALONE else ["-y", "{year}"]
                specs.append((year, available[year], tool, [*base, *case], args.bin_dir, 3))
    print(f"{len(specs)} runs", flush=True)
    with ThreadPoolExecutor(args.jobs) as pool:
        codes = list(pool.map(one, specs))
    crashed = [c for c in codes if c < 0]
    print(f"{len(codes)} runs, {len(crashed)} killed by a signal")
    return 0


if __name__ == "__main__":
    sys.exit(main())
