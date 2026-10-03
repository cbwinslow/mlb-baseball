"""Run ``cwcomment`` and the port over every play-by-play event file of one season, compare bytes.

Development-time only (needs ``cwcomment`` on PATH and a Retrosheet event zip):

    uv run --package retrosheetpy python packages/retrosheetpy/tests/reference/comment_season.py \
        ZIP YEAR

Both output formats (default ascii with header, and ``-ft`` fixed width) are checked.
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
from retrosheetpy.cw.comment import comment_lines, header_line  # noqa: E402


def main() -> int:
    zip_path, year = sys.argv[1], sys.argv[2]
    name = re.compile(rf"^{year}.*\.E[A-Z0-9]{{2}}$", re.I)
    bad = 0
    with tempfile.TemporaryDirectory() as tmp:
        for member_name, member in iter_zip_members(zip_path):
            base = Path(member_name).name
            if not name.match(base):
                continue
            path = Path(tmp) / base
            data = member.read()
            path.write_bytes(data)
            for ascii_, args in ((True, ["-n"]), (False, ["-ft"])):
                run = run_tool("cwcomment", path, args)
                assert run is not None, "cwcomment not on PATH"
                ref = run[1]
                head = header_line() + "\n" if ascii_ else ""
                out = head + "".join(line + "\n" for line in comment_lines(data, ascii_=ascii_))
                ok = ref == out.encode("latin-1")
                bad += not ok
                fmt, verdict = "ascii" if ascii_ else "fixed", "ok" if ok else "DIFFERENT"
                print(f"{base} {fmt}: {len(ref)} bytes {verdict}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
