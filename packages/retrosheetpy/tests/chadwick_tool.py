"""Run a Chadwick text tool (``cwsub``, ``cwgame``, ...) on one event file for differential tests.

Development/test-time only: skips when the binary is not installed. Output is compared
byte for byte with what the port writes.
"""

import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

SRC = Path(os.environ.get("CHADWICK_SRC", Path.home() / "workspace/tmp/chadwick/src"))


# Two defects of ``cwbox -S`` (``cwbox_action_baseball_play`` in ``cwboxsml.c``) that the reference
# build for it works around, so that everything else can be compared:
# 1. ``state->runners[1]`` and ``[2]`` (whole structs) are passed to a ``%s`` conversion, which
#    segfaults on nearly every game; the fix uses the member the line means, ``.runner``, as the
#    line for ``runners[3]`` already does.
# 2. A play whose pitch string is shorter than the previous event's (real data has some, e.g.
#    1915SLA) is read from past its terminating NUL, whose contents are undefined; the fix stops
#    the skip at the end of the string, i.e. no pitch elements for that play.
SPORTSML_PATCH = {
    "cwboxsml.c": [
        ("gameiter->state->runners[1]);", "gameiter->state->runners[1].runner);"),
        ("gameiter->state->runners[2]);", "gameiter->state->runners[2].runner);"),
        (
            "pitches += strlen(gameiter->event->prev->pitches);",
            "pitches += (strlen(gameiter->event->prev->pitches) < strlen(pitches)) ? "
            "strlen(gameiter->event->prev->pitches) : strlen(pitches);",
        ),
    ]
}


def build_sanitised(
    tool: str,
    out_dir: Path,
    extra: tuple[str, ...] = (),
    patches: dict[str, list[tuple[str, str]]] | None = None,
) -> Path | None:
    """Compile ``<tool>.c`` with the Chadwick library under ASAN/UBSAN, or ``None`` without gcc
    or the sources. Damaged inputs can trigger undefined behaviour in the C (reads out of bounds,
    ``NULL`` dereferences); the sanitised build says when it did, so those inputs can be skipped.

    ``patches`` maps a ``cwtools`` source file name to ``(old, new)`` text replacements applied to
    a copy that is compiled instead (each ``old`` must occur)."""
    if shutil.which("gcc") is None or not (SRC / "cwtools" / f"{tool}.c").exists():
        return None
    exe = out_dir / f"{tool}_san"
    cmd = [
        "gcc",
        "-g",
        "-O0",
        "-w",
        '-DVERSION="0.10.0"',
        "-DHAVE_STRUCT_TM_TM_GMTOFF",
        "-fsanitize=address,undefined",
    ]
    cmd += ["-I", str(SRC), "-I", str(SRC / "cwlib"), "-I", str(SRC / "cwtools")]
    sources = [f"{tool}.c", "cwtools.c", *(f"{name}.c" for name in extra)]
    for name in sources:
        path = SRC / "cwtools" / name
        for old, new in (patches or {}).get(name, []):
            text = path.read_text()
            assert old in text, f"{old!r} not in {name}"
            path = out_dir / name
            path.write_text(text.replace(old, new))
        cmd.append(str(path))
    cmd += [*map(str, sorted((SRC / "cwlib").glob("*.c"))), "-o", str(exe)]
    subprocess.run(cmd, check=True, capture_output=True)
    return exe


def run_filled(
    exe: Path,
    event_file: Path,
    args: list[str],
    fill: int,
    support: dict[str, bytes] | None = None,
) -> bytes | None:
    """stdout of a sanitised build whose allocator fills new heap memory with byte ``fill``, or
    ``None`` if it failed or hit undefined behaviour. ``support`` files go next to the event file
    (an empty team file unless given)."""
    data = event_file.read_bytes()
    found = re.search(rb"^id,[A-Z0-9]{3}(\d{4})", data, re.M)
    year = found.group(1).decode() if found else "0000"
    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp)
        (work / f"{year}XXX.EVN").write_bytes(data)
        (work / f"TEAM{year}").write_text("")
        for name, content in (support or {}).items():
            (work / name).write_bytes(content)
        env = {**os.environ, "ASAN_OPTIONS": f"detect_leaks=0:malloc_fill_byte={fill}"}
        run = subprocess.run(
            [str(exe), "-q", "-y", year, *args, f"{year}XXX.EVN"],
            cwd=work,
            capture_output=True,
            check=False,
            env=env,
        )
    if run.returncode != 0 or b"runtime error" in run.stderr or b"AddressSanitizer" in run.stderr:
        return None
    return run.stdout


def run_clean(exe: Path, event_file: Path, args: list[str]) -> bytes | None:
    """stdout of a sanitised build, or ``None`` if it failed, hit undefined behaviour, or read
    uninitialised heap memory (its output changes when the allocator's fill byte does)."""
    outputs = [run_filled(exe, event_file, args, fill) for fill in (0, 255)]
    return outputs[0] if outputs[0] is not None and outputs[0] == outputs[1] else None


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
