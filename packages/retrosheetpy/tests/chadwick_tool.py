"""Run a Chadwick text tool (``cwsub``, ``cwgame``, ...) on one event file for differential tests.

Development/test-time only: skips when the binary is not installed. Output is compared
byte for byte with what the port writes.
"""

import re
import shutil
import subprocess
import tempfile
from pathlib import Path


def run_tool(
    tool: str,
    event_file: Path,
    args: list[str],
    support: dict[str, bytes] | None = None,
) -> tuple[int, bytes] | None:
    """(exit status, stdout) of ``<tool> -q -y YEAR <args> <file>``, run in a scratch directory
    with an empty team file (plus ``support`` files); ``None`` if the binary is not installed."""
    exe = shutil.which(tool)
    if exe is None:
        return None
    data = event_file.read_bytes()
    found = re.search(rb"^id,[A-Z0-9]{3}(\d{4})", data, re.M)
    year = found.group(1).decode() if found else "0000"
    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp)
        (work / f"{year}XXX.EVN").write_bytes(data)
        (work / f"TEAM{year}").write_text("")
        for name, content in (support or {}).items():
            (work / name).write_bytes(content)
        run = subprocess.run(
            [exe, "-q", "-y", year, *args, f"{year}XXX.EVN"],
            cwd=work,
            capture_output=True,
            check=False,
        )
        return run.returncode, run.stdout
