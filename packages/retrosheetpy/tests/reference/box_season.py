"""Build every boxscore of one season with the port and with Chadwick's ``cw_box_create``, compare.

Development-time only (needs gcc, the Chadwick sources and a Retrosheet event zip):

    uv run --package retrosheetpy python packages/retrosheetpy/tests/reference/box_season.py \
        ZIP YEAR [--c-src DIR]

Covers every ``YEARxxx.E??`` file in the zip (play-by-play, deduced and boxscore event files).
Exit status 1 if any file differs, so a season is "validated" only when it exits 0.
"""

import argparse
import difflib
import re
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from box_dump import dump  # noqa: E402
from retrosheetpy import iter_zip_members  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("zip")
    ap.add_argument("year", type=int)
    ap.add_argument("--c-src", default=str(Path.home() / "workspace/tmp/chadwick/src"))
    args = ap.parse_args()
    src = Path(args.c_src)
    name = re.compile(rf"^{args.year}.*\.E[A-Z0-9]{{2}}$", re.I)
    bad = 0
    with tempfile.TemporaryDirectory() as tmp:
        exe = Path(tmp) / "box_dump"
        subprocess.run(
            ["gcc", "-O1", "-w", "-I", str(src / "cwlib"), "-I", str(src), str(HERE / "box_dump.c"),
             *map(str, sorted((src / "cwlib").glob("*.c"))), "-o", str(exe)],
            check=True,
        )  # fmt: skip
        for member_name, member in iter_zip_members(args.zip):
            base = Path(member_name).name
            if not name.match(base):
                continue
            data = member.read()
            path = Path(tmp) / base
            path.write_bytes(data)
            run = subprocess.run([str(exe), str(path)], capture_output=True)
            expected = run.stdout.decode("latin-1").splitlines()
            lines, crashed = dump(data)
            ok = lines == expected and crashed == (run.returncode != 0)
            games = sum(1 for x in expected if x.startswith("BOX "))
            verdict = "ok" if ok else "DIFFERENT"
            print(f"{base}: {games} games {verdict} (C rc={run.returncode}, port raised={crashed})")
            if not ok:
                bad += 1
                diff = difflib.unified_diff(expected, lines, "chadwick", "port", lineterm="", n=2)
                print("\n".join(list(diff)[:40]))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
