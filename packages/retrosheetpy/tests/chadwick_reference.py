"""Dev/test-only adapter around Chadwick's ``cwevent`` (never a runtime dependency).

Chadwick is used only as an independent reference to check ``retrosheetpy``.
If the tool is absent, ``ChadwickReference.find()`` returns ``None`` and tests
that need a live run skip; the captured reference files under
``tests/reference/chadwick/`` keep normal CI deterministic without any tools.
"""

import csv
import io
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

FIELDS = "0-96"  # every standard cwevent field (see `cwevent -d`)
EXTENDED = "0-66"  # every extended (-x) field


class ChadwickReference:
    def __init__(self, cwevent: str):
        self.cwevent = cwevent
        out = subprocess.run([cwevent, "-h"], capture_output=True, text=True, check=False)
        found = re.search(r"version\s+(\d+(?:\.\d+)+)", out.stdout + out.stderr)
        if not found:
            raise RuntimeError(f"cannot read the version of {cwevent}")
        self.version = found.group(1)

    @classmethod
    def find(cls) -> "ChadwickReference | None":
        path = shutil.which("cwevent")
        return cls(path) if path else None

    def events(self, event_file: Path, year: int) -> list[dict[str, str]]:
        """Run ``cwevent`` on one event file and return its rows by field name.

        ``cwevent`` refuses to run without a team file, so an empty one is supplied;
        the event records already carry the team ids this check needs.
        """
        with tempfile.TemporaryDirectory() as tmp:
            work = Path(tmp)
            shutil.copyfile(event_file, work / f"{year}XXX.EVN")
            (work / f"TEAM{year}").write_text("")
            run = subprocess.run(
                [
                    self.cwevent,
                    "-q",
                    "-y",
                    str(year),
                    "-n",
                    "-f",
                    FIELDS,
                    "-x",
                    EXTENDED,
                    f"{year}XXX.EVN",
                ],
                cwd=work,
                capture_output=True,
                text=True,
                check=False,
            )
        if run.returncode != 0:
            raise RuntimeError(f"cwevent failed ({run.returncode}): {run.stderr.strip()}")
        return list(csv.DictReader(io.StringIO(run.stdout)))
