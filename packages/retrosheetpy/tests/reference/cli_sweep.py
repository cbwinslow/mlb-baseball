"""Option sweep: the real Chadwick program against the installed port command, every option of every
tool (valid, repeated, conflicting and malformed values), on real seasons. Compares stdout, stderr
and exit status byte for byte.

Development-time only (see ``cli_all_years.py`` for the set-up of ``PORT_BIN`` and the real tools):

    python cli_sweep.py ZIPDIR PORT_BIN [--years 1910,1950,...] [--files 3] [--random 60]

Per tool and season: a fixed list of single-option cases (each option, with good and bad values),
plus ``--random`` combinations drawn with a fixed seed from every option the tool accepts. Event
files are the first ``--files`` of the season. ``cwbox -S`` is not run (the real program
segfaults) and the ``pb`` attribute of ``cwbox -X`` is ignored (uninitialised memory in the C).
"""

import argparse
import json
import random
import re
import sys
import tempfile
import zipfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))

from chadwick_tool import real_tool  # noqa: E402
from cli_all_years import EVENT, PB, run, seasons  # noqa: E402

# tool -> options it understands; each entry: (flag, takes a value, [values to try])
FIELDS = ["0", "0-3", "3,1,2", "0-96", "5-2", "999", "1,,2", "x", "", "-1", "0-"]
DATES = ["0601", "0630", "0101", "1231", "13", "abc", "", "00000", "0229"]
COMMON: list[tuple[str, bool, list[str]]] = [
    ("-q", False, []),
    ("-a", False, []),
    ("-ft", False, []),
    ("-s", True, DATES),
    ("-e", True, DATES),
    ("-y", True, ["{year}", "1", "abcd", "20251", "", "0"]),
    ("-i", True, ["{game}", "XXX000000000", "", "{game_other}"]),
]
OPTIONS: dict[str, list[tuple[str, bool, list[str]]]] = {
    "cwevent": [*COMMON, ("-n", False, []), ("-f", True, FIELDS), ("-x", True, FIELDS)],
    "cwgame": [*COMMON, ("-n", False, []), ("-f", True, FIELDS), ("-x", True, FIELDS)],
    "cwdaily": [*COMMON, ("-n", False, [])],
    "cwsub": [*COMMON, ("-n", False, [])],
    "cwcomment": [*COMMON, ("-n", False, [])],
    "cwbox": [*COMMON, ("-X", False, [])],
}
STANDALONE = [["-h"], ["-d"], ["-z"], ["-"], ["--help"], ["-hq"], ["-d", "-q"], ["-q", "-h"]]


def cases(tool: str, rng: random.Random, n_random: int) -> list[list[str]]:
    out: list[list[str]] = [list(a) for a in STANDALONE]
    out.append([])
    for flag, valued, values in OPTIONS[tool]:
        if valued:
            out += [[flag, v] for v in values]
            out.append([flag])  # value missing
        else:
            out.append([flag])
            out.append([flag, flag])
    for _ in range(n_random):
        picked = rng.sample(OPTIONS[tool], rng.randint(2, min(6, len(OPTIONS[tool]))))
        args: list[str] = []
        for flag, valued, values in picked:
            args.append(flag)
            if valued:
                args.append(rng.choice(values))
        out.append(args)
    return out


def game_ids(data: bytes) -> list[str]:
    return re.findall(r"^id,([A-Z0-9]{12})", data.decode("latin-1"), re.M)


def job(spec: tuple[int, Path, str, list[str], str, int]) -> dict[str, object]:
    year, zip_path, tool, args, port_bin, n_files = spec
    real = real_tool(tool)
    assert real is not None
    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp)
        files: list[str] = []
        ids: list[str] = []
        with zipfile.ZipFile(zip_path) as zf:
            for name in sorted(zf.namelist()):
                base = Path(name).name
                keep = (base.upper() == f"TEAM{year}") or (
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
                    ids += game_ids(data)
                (work / base).write_bytes(data)
        game = ids[len(ids) // 2] if ids else "XXX000000000"
        other = ids[-1] if ids else "XXX000000000"
        base = [] if "-y" in args or args in STANDALONE else ["-y", "{year}"]
        argv = [a.format(year=year, game=game, game_other=other) for a in [*base, *args]]
        no_files = argv[:1] in (["-h"], ["-d"]) or "-h" in argv or "-d" in argv
        argv += [] if no_files else files
        a = run(tool, str(Path(real).parent), argv, work)
        b = run(tool, port_bin, argv, work)
    if tool == "cwbox" and "-X" in argv:
        a, b = (a[0], PB.sub(b"", a[1]), a[2]), (b[0], PB.sub(b"", b[1]), b[2])
    return {
        "year": year,
        "tool": tool,
        "args": argv[: len(argv) - len(files)] if not no_files else argv,
        "same": a == b,
        "status": [a[0], b[0]],
        "stdout_bytes": len(a[1]),
        "stderr_bytes": len(a[2]),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("zip_dir", type=Path)
    parser.add_argument("port_bin", type=Path)
    parser.add_argument("--years", default="1910,1950,1976,1998,2007,2020,2025")
    parser.add_argument("--files", type=int, default=3)
    parser.add_argument("--random", type=int, default=60)
    parser.add_argument("--jobs", type=int, default=16)
    parser.add_argument("--seed", type=int, default=20261002)
    parser.add_argument("--out", type=Path, default=Path("cli_sweep_out"))
    args = parser.parse_args()
    available = seasons(args.zip_dir)
    rng = random.Random(args.seed)
    specs = [
        (int(y), available[int(y)], tool, case, str(args.port_bin), args.files)
        for y in args.years.split(",")
        for tool in OPTIONS
        for case in cases(tool, rng, args.random)
    ]
    args.out.mkdir(parents=True, exist_ok=True)
    print(f"{len(specs)} comparisons, {args.jobs} at a time", flush=True)
    results: list[dict[str, object]] = []
    with ThreadPoolExecutor(args.jobs) as pool:
        for r in pool.map(job, specs):
            results.append(r)
            if not r["same"]:
                print("DIFFERENT", r, flush=True)
    (args.out / "cli_sweep.json").write_text(json.dumps(results))
    bad = [r for r in results if not r["same"]]
    quiet = sum(1 for r in results if r["stdout_bytes"] == 0 and r["stderr_bytes"] == 0)
    errors = sum(1 for r in results if r["status"][0] != 0)  # type: ignore[index]
    print(
        f"{len(results)} comparisons, {len(bad)} different; {errors} where the real tool exits "
        f"non-zero, {quiet} with no output at all"
    )
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
