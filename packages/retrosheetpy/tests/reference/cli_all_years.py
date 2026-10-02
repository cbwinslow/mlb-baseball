"""End-to-end check of the INSTALLED commands: the real Chadwick program against the port's console
script, the way a user runs them (``cwevent -y 1950 1950*.EV*`` in a directory holding the season's
event, team and roster files), for every season and several option sets per tool. Compares stdout,
stderr and exit status byte for byte.

Development-time only. ``PORT_BIN`` is the ``bin`` directory of a clean virtualenv with the built
wheel installed; the real tools are found with ``real_tool`` (``CHADWICK_BIN`` or ``PATH``):

    python cli_all_years.py ZIPDIR PORT_BIN [--from 1910] [--to 2025] [--jobs 16] [--out DIR]

``cwbox -S`` is left out because the real program segfaults on nearly every game (a Chadwick
defect, see ``chadwick_tool.SPORTSML_PATCH``); ``cwbox -X`` is compared without the ``pb``
attribute, which depends on uninitialised memory in the C. Exit status 1 on any difference.
"""

import argparse
import json
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

from chadwick_tool import real_tool  # noqa: E402

TEAM = re.compile(r"(?:^|/)TEAM(\d{4})$", re.I)
EVENT = re.compile(r"\.E[A-Z0-9]{2}$", re.I)
PB = re.compile(rb' pb="\d+"')

# name -> (tool, arguments between "-y YEAR" and the files)
OPTION_SETS: dict[str, tuple[str, list[str]]] = {
    "cwevent default": ("cwevent", []),
    "cwevent all": ("cwevent", ["-n", "-f", "0-96", "-x", "0-66"]),
    "cwevent fixed June": ("cwevent", ["-ft", "-s", "0601", "-e", "0630"]),
    "cwevent quiet fields": ("cwevent", ["-q", "-f", "0,1,2,3,4,5,6,13,14,26,29,34"]),
    "cwgame default": ("cwgame", []),
    "cwgame all": ("cwgame", ["-n", "-f", "0-84", "-x", "0-96"]),
    "cwgame fixed": ("cwgame", ["-ft", "-q"]),
    "cwdaily default": ("cwdaily", []),
    "cwdaily ascii": ("cwdaily", ["-n"]),
    "cwsub default": ("cwsub", []),
    "cwsub ascii": ("cwsub", ["-n", "-q"]),
    "cwcomment default": ("cwcomment", []),
    "cwcomment ascii": ("cwcomment", ["-n", "-q"]),
    "cwbox default": ("cwbox", []),
    "cwbox quiet": ("cwbox", ["-q"]),
    "cwbox xml": ("cwbox", ["-X", "-q"]),
}


def seasons(zip_dir: Path) -> dict[int, Path]:
    found: dict[int, Path] = {}
    for path in sorted(zip_dir.glob("*seve.zip")):
        with zipfile.ZipFile(path) as zf:
            for name in zf.namelist():
                match = TEAM.search(name)
                if match:
                    found[int(match.group(1))] = path
    return found


def run(tool: str, bin_dir: str, args: list[str], cwd: Path) -> tuple[int, bytes, bytes]:
    """Run ``tool`` by its bare name with only ``bin_dir`` on PATH, as a user would: the C program
    prints ``argv[0]`` as typed in its usage text, so both must be started the same way (a Python
    console script always sees its full path in ``sys.argv[0]``; the port prints the bare name)."""
    env = {"PATH": bin_dir, "LC_ALL": "C"}
    done = subprocess.run([tool, *args], cwd=cwd, capture_output=True, check=False, env=env)
    return done.returncode, done.stdout, done.stderr


def check(job: tuple[int, Path, str, str, str, list[str]]) -> dict[str, object]:
    year, zip_path, label, tool, port_bin, extra = job
    real = real_tool(tool)
    assert real is not None, f"{tool} (the real Chadwick program) not found"
    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp)
        files: list[str] = []
        with zipfile.ZipFile(zip_path) as zf:
            for name in zf.namelist():
                base = Path(name).name
                if not base or not base.upper().startswith(("TEAM", str(year))):
                    continue
                if base.upper().startswith("TEAM") and base[4:] != str(year):
                    continue
                if base.upper().startswith(str(year)) and not (
                    EVENT.search(base) or re.search(r"\.ROS$", base, re.I)
                ):
                    continue
                (work / base).write_bytes(zf.read(name))
                if EVENT.search(base):
                    files.append(base)
        files.sort()
        args = ["-y", str(year), *extra, *files]
        a = run(tool, str(Path(real).parent), args, work)
        b = run(tool, port_bin, args, work)
    if tool == "cwbox" and "-X" in extra:
        a, b = (a[0], PB.sub(b"", a[1]), a[2]), (b[0], PB.sub(b"", b[1]), b[2])
    same = a == b
    return {
        "year": year,
        "set": label,
        "files": len(files),
        "stdout_bytes": len(a[1]),
        "status": [a[0], b[0]],
        "same": same,
        "stderr_same": a[2] == b[2],
        "first_diff": next(
            (i for i, (x, y) in enumerate(zip(a[1], b[1], strict=False)) if x != y), None
        )
        if not same
        else None,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("zip_dir", type=Path)
    parser.add_argument("port_bin", type=Path)
    parser.add_argument("--from", dest="first", type=int, default=1910)
    parser.add_argument("--to", dest="last", type=int, default=9999)
    parser.add_argument("--jobs", type=int, default=16)
    parser.add_argument("--out", type=Path, default=Path("cli_all_years_out"))
    args = parser.parse_args()
    for tool in {t for t, _ in OPTION_SETS.values()}:
        if shutil.which(tool, path=str(args.port_bin)) is None:
            print(f"port command {tool} not in {args.port_bin}", file=sys.stderr)
            return 1
    available = seasons(args.zip_dir)
    years = [y for y in sorted(available) if args.first <= y <= args.last]
    jobs = [
        (y, available[y], label, tool, str(args.port_bin), extra)
        for y in years
        for label, (tool, extra) in OPTION_SETS.items()
    ]
    args.out.mkdir(parents=True, exist_ok=True)
    print(f"{len(years)} seasons, {len(jobs)} comparisons, {args.jobs} at a time", flush=True)
    results: list[dict[str, object]] = []
    with ThreadPoolExecutor(args.jobs) as pool:
        for r in pool.map(check, jobs):
            results.append(r)
            if not r["same"] or not r["stderr_same"]:
                print("DIFFERENT", r, flush=True)
    (args.out / "cli_all_years.json").write_text(json.dumps(results, indent=1))
    bad = [r for r in results if not r["same"] or not r["stderr_same"]]
    empty = [r for r in results if r["stdout_bytes"] == 0]
    total = sum(int(str(r["stdout_bytes"])) for r in results)
    print(
        f"{len(results)} comparisons, {len(bad)} different, {len(empty)} with empty output, "
        f"{total} bytes of real-tool output compared"
    )
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
