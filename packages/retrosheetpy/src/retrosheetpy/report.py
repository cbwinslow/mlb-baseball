"""Machine-readable coverage report: records, plays, unsupported syntax, mismatches.

    python -m retrosheetpy.report FILE_OR_ZIP... [--chadwick-csv F] [--plays-csv F]

Reference CSVs are optional inputs (``cwevent -n`` output, Retrosheet
``plays.csv``); no native tool is run. The report is JSON on stdout.
"""

import argparse
import csv
import json
import sys
from collections.abc import Iterator, Sequence
from pathlib import Path
from typing import Any

from retrosheetpy.coverage import PlayCoverage
from retrosheetpy.records import Record, RecordStats, iter_event_zip, read_event_file
from retrosheetpy.validation import Comparison, compare_chadwick, compare_plays_csv


def _records(path: Path, stats: RecordStats) -> Iterator[Record]:
    if path.suffix.lower() == ".zip":
        return iter_event_zip(path, strict=False, stats=stats)
    return read_event_file(path, strict=False, stats=stats)


def _read_csv(path: Path) -> Iterator[dict[str, str]]:
    with open(path, newline="", encoding="utf-8") as f:
        yield from csv.DictReader(f)


def build_report(
    paths: Sequence[str | Path],
    *,
    chadwick_csv: str | Path | None = None,
    chadwick_version: str = "",
    plays_csv: str | Path | None = None,
) -> dict[str, Any]:
    """Parse ``paths`` (event files or zips) and summarise coverage and disagreements."""
    stats = RecordStats()
    coverage = PlayCoverage()
    keep: list[Record] = []
    wanted = chadwick_csv is not None or plays_csv is not None
    for path in map(Path, paths):
        for rec in _records(path, stats):
            coverage.add_records([rec])
            if wanted:
                keep.append(rec)
    comparisons: list[Comparison] = []
    if chadwick_csv is not None:
        comparisons.append(
            compare_chadwick(keep, _read_csv(Path(chadwick_csv)), version=chadwick_version)
        )
    if plays_csv is not None:
        comparisons.append(compare_plays_csv(keep, _read_csv(Path(plays_csv))))
    return {
        "inputs": [Path(p).name for p in paths],
        "records": {
            "lines": stats.lines,
            "by_type": dict(sorted(stats.by_type.items())),
            "unsupported": dict(sorted(stats.unsupported.items())),
        },
        "plays": coverage.to_dict(),
        "reference_mismatches": [c.to_dict() for c in comparisons],
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m retrosheetpy.report", description=__doc__)
    parser.add_argument("paths", nargs="+")
    parser.add_argument("--chadwick-csv")
    parser.add_argument("--chadwick-version", default="")
    parser.add_argument("--plays-csv")
    args = parser.parse_args(argv)
    report = build_report(
        args.paths,
        chadwick_csv=args.chadwick_csv,
        chadwick_version=args.chadwick_version,
        plays_csv=args.plays_csv,
    )
    json.dump(report, sys.stdout, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
