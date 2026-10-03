"""Check that a new season's event files are read completely and cleanly (no Chadwick needed).

    uv run --package retrosheetpy python \
        packages/retrosheetpy/tests/reference/new_season_guard.py ZIP YEAR

Lists every unparsed play, unknown record, unreadable line and game that was not read. Exit
status 1 if anything is listed. Run ``season_report.py`` as well when ``cwevent`` is available.
"""

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from retrosheetpy import iter_zip_members  # noqa: E402
from retrosheetpy.cw.guard import check_event_file  # noqa: E402
from retrosheetpy.records import is_event_filename  # noqa: E402


def main(zip_path: str, year: str) -> int:
    problems: list[str] = []
    files = 0
    for name, member in iter_zip_members(zip_path):
        if is_event_filename(name) and re.search(year, name):
            files += 1
            problems += check_event_file(member.read(), name)
    for line in problems:
        print(line)
    print(f"{files} files, {len(problems)} problems")
    return 1 if problems or not files else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1], sys.argv[2]))
