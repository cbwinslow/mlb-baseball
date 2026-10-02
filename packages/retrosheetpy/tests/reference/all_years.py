"""Run every ported Chadwick tool over every Retrosheet season, the real C tool against the port.

Development-time only. Needs the real Chadwick tools (``real_tool``: ``CHADWICK_BIN`` or ``PATH``
outside the virtualenv), gcc plus the Chadwick sources (``CHADWICK_SRC``) for ``cwbox -X/-S``, and
the Retrosheet decade event zips:

    uv run --package retrosheetpy python packages/retrosheetpy/tests/reference/all_years.py \
        ZIPDIR [--from 1910] [--to 2025] [--jobs 4] [--out DIR]

For each season and each tool the matching ``*_season.py`` script is run (it compares every event
file of the season, with the season's real team and roster files, byte for byte). Every output
line ``FILE FORMAT: N bytes ok|DIFFERENT`` is counted; a script that exits non-zero, prints a line
in another shape (a traceback, a skipped file) or finds no files is a failure and its output is
kept in ``OUT/logs``. Writes ``OUT/all_years.md`` (table) and ``OUT/all_years.json``.

Exit status 1 if anything differs or failed, so the proof holds only when this exits 0.
"""

import argparse
import json
import re
import subprocess
import sys
import zipfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
TOOLS = {
    "cwevent": "event_season.py",
    "cwgame": "game_season.py",
    "cwbox": "box_text_season.py",
    "cwdaily": "daily_season.py",
    "cwsub": "sub_season.py",
    "cwcomment": "comment_season.py",
}
LINE = re.compile(r"^(\S+) (\S+): (\d+) bytes (ok|DIFFERENT)$")
NOTE = re.compile(r"^\d+ xml files depend on uninitialised memory")
TEAM = re.compile(r"(?:^|/)TEAM(\d{4})$", re.I)


def seasons(zip_dir: Path) -> dict[int, Path]:
    """Season -> the decade zip holding its team file."""
    found: dict[int, Path] = {}
    for path in sorted(zip_dir.glob("*seve.zip")):
        with zipfile.ZipFile(path) as zf:
            for name in zf.namelist():
                match = TEAM.search(name)
                if match:
                    found[int(match.group(1))] = path
    return found


def run_one(job: tuple[int, str, Path, Path]) -> dict[str, object]:
    year, tool, zip_path, logs = job
    run = subprocess.run(
        [sys.executable, str(HERE / TOOLS[tool]), str(zip_path), str(year)],
        capture_output=True,
        text=True,
        encoding="latin-1",
        check=False,
    )
    files: set[str] = set()
    checks = ok = diff = 0
    odd: list[str] = []
    for line in run.stdout.splitlines():
        match = LINE.match(line)
        if match:
            files.add(match.group(1))
            checks += 1
            ok += match.group(4) == "ok"
            diff += match.group(4) == "DIFFERENT"
        elif line.strip() and not NOTE.match(line):
            odd.append(line)
    failed = run.returncode != 0 or diff > 0 or checks == 0 or bool(odd)
    if failed:
        logs.mkdir(parents=True, exist_ok=True)
        (logs / f"{year}_{tool}.log").write_text(run.stdout + "\n--- stderr ---\n" + run.stderr)
    return {
        "year": year,
        "tool": tool,
        "files": len(files),
        "checks": checks,
        "ok": ok,
        "diff": diff,
        "odd_lines": odd[:5],
        "exit": run.returncode,
        "failed": failed,
    }


def table(results: list[dict[str, object]]) -> str:
    tools = list(TOOLS)
    by = {(r["year"], r["tool"]): r for r in results}
    years = sorted({int(str(r["year"])) for r in results})
    lines = [
        "| year | " + " | ".join(tools) + " |",
        "|---|" + "---|" * len(tools),
    ]
    for year in years:
        cells = []
        for tool in tools:
            r = by.get((year, tool))
            if r is None:
                cells.append("-")
            elif r["failed"]:
                cells.append(f"**FAIL** {r['diff']} diff, exit {r['exit']}")
            else:
                cells.append(f"{r['files']} files, {r['checks']} checks, 0 diffs")
        lines.append(f"| {year} | " + " | ".join(cells) + " |")
    total = {t: sum(int(str(r["checks"])) for r in results if r["tool"] == t) for t in tools}
    lines.append("| **checks** | " + " | ".join(str(total[t]) for t in tools) + " |")
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("zip_dir", type=Path)
    parser.add_argument("--from", dest="first", type=int, default=1910)
    parser.add_argument("--to", dest="last", type=int, default=9999)
    parser.add_argument("--jobs", type=int, default=4)
    parser.add_argument("--out", type=Path, default=Path("all_years_out"))
    parser.add_argument("--tools", default=",".join(TOOLS))
    args = parser.parse_args()
    available = seasons(args.zip_dir)
    years = [y for y in sorted(available) if args.first <= y <= args.last]
    if not years:
        print("no seasons found", file=sys.stderr)
        return 1
    chosen = args.tools.split(",")
    args.out.mkdir(parents=True, exist_ok=True)
    jobs = [(y, t, available[y], args.out / "logs") for y in years for t in chosen]
    print(f"{len(years)} seasons {years[0]}-{years[-1]}, {len(jobs)} runs, {args.jobs} at a time")
    results: list[dict[str, object]] = []
    with ThreadPoolExecutor(args.jobs) as pool:
        for r in pool.map(run_one, jobs):
            results.append(r)
            status = "FAIL" if r["failed"] else "ok"
            print(
                f"{r['year']} {r['tool']}: {r['files']} files {r['checks']} checks {status}",
                flush=True,
            )
    (args.out / "all_years.json").write_text(json.dumps(results, indent=1))
    (args.out / "all_years.md").write_text(table(results))
    failures = [r for r in results if r["failed"]]
    print(f"{len(results) - len(failures)} runs clean, {len(failures)} failed; table in {args.out}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
