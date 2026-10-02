"""Run ``cwbox`` and the port over every play-by-play event file of one season, with the season's
real team and roster files, and compare bytes.

Development-time only (needs ``cwbox`` on PATH and a Retrosheet event zip):

    uv run --package retrosheetpy python packages/retrosheetpy/tests/reference/box_text_season.py \
        ZIP YEAR

Both the text and the XML (``-X``) output are checked. Chadwick's ``cwbox -X`` reads
``player->positions[pos]`` (indexed by fielding position) beyond the positions the player
filled, which are never initialised (``cw_box_player_create`` uses ``malloc``): the ``pb``
attribute of a ``<fielding>`` element then depends on the allocator. So the XML is compared
with the sanitised build run with a zero-filled allocator, which is what the port defines
those entries to be; a second run with a different fill must differ only in ``pb`` attributes.
Exit status 1 if any file differs.
"""

import re
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

from chadwick_tool import build_sanitised, run_filled, run_tool  # noqa: E402
from retrosheetpy import iter_zip_members  # noqa: E402
from retrosheetpy.cw.cwbox import box_text  # noqa: E402
from retrosheetpy.cw.tools import read_rosters  # noqa: E402

PB = re.compile(rb' pb="\d+"')


def main() -> int:
    zip_path, year = sys.argv[1], sys.argv[2]
    event_name = re.compile(rf"^{year}.*\.E[A-Z0-9]{{2}}$", re.I)
    members = {Path(n).name: m.read() for n, m in iter_zip_members(zip_path)}
    support = {n: d for n, d in members.items() if not re.search(r"\.E[A-Z0-9]{2}$", n, re.I)}
    league = read_rosters(support[f"TEAM{year}"], year, support.get)
    bad = uninitialised = 0
    with tempfile.TemporaryDirectory() as tmp:
        exe = build_sanitised("cwbox", Path(tmp), ("cwboxxml", "cwboxsml", "xmlwrite"))
        assert exe is not None, "needs gcc and the Chadwick sources"
        for base, data in sorted(members.items()):
            if not event_name.match(base):
                continue
            path = Path(tmp) / base
            path.write_bytes(data)
            run = run_tool("cwbox", path, [], support)
            assert run is not None, "cwbox not on PATH"
            ok = run[1] == "".join(box_text(data, league)).encode("latin-1")
            bad += not ok
            print(f"{base} text: {len(run[1])} bytes {'ok' if ok else 'DIFFERENT'}")
            zero = run_filled(exe, path, ["-X"], 0, support)
            other = run_filled(exe, path, ["-X"], 255, support)
            assert zero is not None and other is not None, "cwbox -X failed under the sanitisers"
            out = "".join(box_text(data, league, use_xml=True)).encode("latin-1")
            ok = zero == out and PB.sub(b"", zero) == PB.sub(b"", other)
            uninitialised += zero != other
            bad += not ok
            print(f"{base} xml: {len(zero)} bytes {'ok' if ok else 'DIFFERENT'}")
    print(f"{uninitialised} xml files depend on uninitialised memory (pb attributes only)")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
