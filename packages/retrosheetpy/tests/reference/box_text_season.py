"""Run ``cwbox`` and the port over every play-by-play event file of one season, with the season's
real team and roster files, and compare bytes.

Development-time only (needs ``cwbox`` on PATH and a Retrosheet event zip):

    uv run --package retrosheetpy python packages/retrosheetpy/tests/reference/box_text_season.py \
        ZIP YEAR

Exit status 1 if any file differs.
"""

import re
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

from chadwick_tool import run_tool  # noqa: E402
from retrosheetpy import iter_zip_members  # noqa: E402
from retrosheetpy.cw.cwbox import box_text  # noqa: E402
from retrosheetpy.cw.tools import read_rosters  # noqa: E402


def main() -> int:
    zip_path, year = sys.argv[1], sys.argv[2]
    event_name = re.compile(rf"^{year}.*\.E[A-Z0-9]{{2}}$", re.I)
    members = {Path(n).name: m.read() for n, m in iter_zip_members(zip_path)}
    support = {n: d for n, d in members.items() if not re.search(r"\.E[A-Z0-9]{2}$", n, re.I)}
    league = read_rosters(support[f"TEAM{year}"], year, support.get)
    bad = 0
    with tempfile.TemporaryDirectory() as tmp:
        for base, data in sorted(members.items()):
            if not event_name.match(base):
                continue
            path = Path(tmp) / base
            path.write_bytes(data)
            run = run_tool("cwbox", path, [], support)
            assert run is not None, "cwbox not on PATH"
            out = "".join(box_text(data, league)).encode("latin-1")
            ok = run[1] == out
            bad += not ok
            print(f"{base}: {len(run[1])} bytes {'ok' if ok else 'DIFFERENT'}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
