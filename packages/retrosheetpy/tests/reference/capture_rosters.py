"""Capture ``cwevent`` output with rosters present for the fixtures (needs ``cwevent`` and network).

Run from the repository root:
    uv run --package retrosheetpy python \
        packages/retrosheetpy/tests/reference/capture_rosters.py CACHE_DIR
For each fixture it copies the ``TEAMyyyy`` lines and ``.ROS`` files of the teams in the fixture
from the season's Retrosheet event zip into ``rosters/<fixture>/`` and stores what ``cwevent``
prints with them in ``chadwick_rosters/<fixture>.csv``. The hand columns then come from the
rosters, which the captures in ``chadwick/`` (empty team file) never exercise.
"""

import csv
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

from chadwick_reference import ChadwickReference  # noqa: E402
from retrosheetpy import Client, Product, iter_zip_members, resolve  # noqa: E402

FIXTURES = HERE.parent / "fixtures" / "events"
ROSTERS = HERE / "rosters"
OUT = HERE / "chadwick_rosters"


def main(cache_dir: str) -> None:
    ref = ChadwickReference.find()
    if ref is None:
        sys.exit("cwevent not found on PATH")
    client = Client(cache_dir)
    OUT.mkdir(exist_ok=True)
    for evt in sorted(FIXTURES.glob("*.evt")):
        text = evt.read_bytes()
        year = int(re.search(rb"^id,[A-Z0-9]{3}(\d{4})", text, re.M).group(1))  # type: ignore[union-attr]
        teams = {m.decode() for m in re.findall(rb"^info,(?:visteam|hometeam),(\w+)", text, re.M)}
        support: dict[str, bytes] = {}
        try:
            zip_path = client.download(resolve(Product.EVENTS_DECADE, year)).local_path
        except ValueError:  # seasons before 1910 are not in a decade archive: no rosters
            zip_path = None
        for name, member in iter_zip_members(zip_path) if zip_path else ():
            base = Path(name).name
            if base == f"TEAM{year}":
                lines = member.read().splitlines(keepends=True)
                support[base] = b"".join(ln for ln in lines if ln.split(b",")[0].decode() in teams)
            elif base.endswith(f"{year}.ROS") and base[: -len(f"{year}.ROS")] in teams:
                support[base] = member.read()
        target = ROSTERS / evt.stem
        target.mkdir(parents=True, exist_ok=True)
        for name, data in support.items():
            (target / name).write_bytes(data)
        rows = ref.events(evt, year, support)
        with open(OUT / f"{evt.stem}.csv", "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0]), lineterminator="\n")
            w.writeheader()
            w.writerows(rows)
        print(f"{evt.stem}: {len(rows)} rows, {sorted(support)}")
    print(f"captured with Chadwick {ref.version}")


if __name__ == "__main__":
    main(sys.argv[1])
