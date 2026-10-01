"""Run one season of event files through the engine and Chadwick and report mismatches.

Development-time only (needs ``cwevent`` on PATH and a Retrosheet event zip):

    uv run --package retrosheetpy python packages/retrosheetpy/tests/reference/season_report.py \
        ZIP YEAR [--out report.json] [--fields A,B,...]

Prints one summary line per event file and a total; ``--out`` writes the full JSON
(field counts and example plays). Exit status is 1 if any mismatch, misaligned game
or engine error is found, so a season is "validated" only when it exits 0.
"""

import argparse
import json
import re
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

from chadwick_reference import ChadwickReference  # noqa: E402
from implemented_fields import IMPLEMENTED  # noqa: E402
from retrosheetpy import iter_zip_members, read_event_file  # noqa: E402
from retrosheetpy.errors import ParseError  # noqa: E402
from retrosheetpy.records import is_event_filename  # noqa: E402
from retrosheetpy.state import event_rows  # noqa: E402
from retrosheetpy.validation import compare_rows  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("zip")
    ap.add_argument("year", type=int)
    ap.add_argument("--out")
    ap.add_argument("--fields")
    args = ap.parse_args()
    fields = args.fields.split(",") if args.fields else list(IMPLEMENTED)
    ref = ChadwickReference.find()
    if ref is None:
        sys.exit("cwevent not found on PATH")
    pattern = re.compile(rf"{args.year}", re.I)
    report: dict[str, object] = {"chadwick": ref.version, "year": args.year, "files": {}}
    bad = 0
    totals = {"plays": 0, "mismatches": 0, "misaligned": 0, "errors": 0}
    with tempfile.TemporaryDirectory() as tmp:
        for name, member in iter_zip_members(args.zip):
            if not is_event_filename(name) or not pattern.search(name):
                continue
            path = Path(tmp) / Path(name).name
            path.write_bytes(member.read())
            entry: dict[str, object] = {}
            try:
                ours = list(event_rows(read_event_file(path)))
                theirs = ref.events(path, args.year)
                result = compare_rows(f"chadwick {ref.version}", ours, theirs, fields)
                entry = result.to_dict()
                problems = result.mismatches + result.games_misaligned
                problems += result.games_only_ours + result.games_only_reference
                totals["plays"] += result.plays_compared
                totals["mismatches"] += result.mismatches
                totals["misaligned"] += result.games_misaligned
            except (ParseError, ValueError, RuntimeError) as exc:
                entry = {"error": str(exc)}
                problems = 1
                totals["errors"] += 1
            bad += problems
            report["files"][name] = entry  # type: ignore[index]
            note = (
                entry.get("error")
                or f"plays={entry['plays_compared']} mismatches={entry['mismatches']} "
                f"misaligned={entry['games_misaligned']}"
            )
            print(f"{name}: {'OK' if not problems else 'FAIL'} {note}")
            path.unlink()
    report["totals"] = totals
    print("TOTAL", totals)
    if args.out:
        Path(args.out).write_text(json.dumps(report, indent=2) + "\n")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
