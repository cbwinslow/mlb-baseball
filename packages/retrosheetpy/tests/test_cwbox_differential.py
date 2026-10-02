"""The port of ``cwbox`` (plain text) against the real ``cwbox`` binary, byte for byte.

On every fixture event file, without rosters and with synthesised ones (so the city, name and
first-initial paths run), and on randomly damaged copies of them. Runs only where ``cwbox``
(Chadwick 0.10) is installed.
"""

import random
import re
import shutil
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
from chadwick_tool import build_sanitised, run_clean, run_tool  # noqa: E402
from retrosheetpy.cw.cwbox import box_text  # noqa: E402
from retrosheetpy.cw.game import read_games  # noqa: E402
from retrosheetpy.cw.tools import read_rosters  # noqa: E402
from test_reader_differential import damage  # noqa: E402

pytestmark = pytest.mark.skipif(shutil.which("cwbox") is None, reason="needs cwbox on PATH")

PB = re.compile(rb' pb="\d+"')
FIXTURES = sorted((HERE / "fixtures" / "events").glob("*.evt"))


def year_of(data: bytes) -> str:
    found = re.search(rb"^id,[A-Z0-9]{3}(\d{4})", data, re.M)
    return found.group(1).decode() if found else "0000"


def synthetic_rosters(data: bytes) -> dict[str, bytes]:
    """A team file and roster files covering the teams and the starters/substitutes of the games.
    Every other player gets an empty first name, and the team cities are made long."""
    year = year_of(data)
    teams: dict[str, dict[str, tuple[str, str]]] = {}
    for game in read_games(data):
        for team_key, team in (("visteam", 0), ("hometeam", 1)):
            team_id = game.info_lookup(team_key)
            if team_id is None:
                continue
            players = teams.setdefault(team_id, {})
            apps = list(game.starters) + [s for e in game.events for s in e.subs]
            for app in apps:
                if app.team == team and app.player_id not in players:
                    last, _, first = app.name.partition(" ")
                    players[app.player_id] = (last, first if len(players) % 2 else "")
    support = {f"TEAM{year}": "".join(f"{t},A,City of {t},Nick\n" for t in teams).encode()}
    for team_id, players in teams.items():
        rows = "".join(f"{p},{ln},{fn},R,R,{team_id}\n" for p, (ln, fn) in players.items())
        support[f"{team_id}{year}.ROS"] = rows.encode()
    return support


def port_output(
    data: bytes, support: dict[str, bytes] | None = None, use_xml: bool = False
) -> bytes:
    league = None
    if support:
        league = read_rosters(support[f"TEAM{year_of(data)}"], year_of(data), support.get)
    return "".join(box_text(data, league, use_xml=use_xml)).encode("latin-1")


@pytest.mark.parametrize("xml", [False, True], ids=["text", "xml"])
@pytest.mark.parametrize("rosters", [False, True], ids=["no_rosters", "rosters"])
@pytest.mark.parametrize("fixture", FIXTURES, ids=lambda p: p.stem)
def test_fixture_matches_cwbox(fixture: Path, rosters: bool, xml: bool) -> None:
    data = fixture.read_bytes()
    support = synthetic_rosters(data) if rosters else None
    run = run_tool("cwbox", fixture, ["-X"] if xml else [], support)
    assert run is not None
    assert run[0] == 0
    expected, out = run[1], port_output(data, support, xml)
    if xml:
        # the C reads uninitialised memory for the ``pb`` attribute (see ``cwboxxml``)
        expected, out = PB.sub(b"", expected), PB.sub(b"", out)
    assert expected == out


def test_damaged_files_match_cwbox(tmp_path: Path) -> None:
    exe = build_sanitised("cwbox", tmp_path, ("cwboxxml", "cwboxsml", "xmlwrite"))
    if exe is None:
        pytest.skip("needs gcc and the Chadwick sources (CHADWICK_SRC)")
    rng = random.Random(9)
    checked = 0
    for fixture in FIXTURES:
        for i in range(25):
            data = bytes(damage(rng, bytearray(fixture.read_bytes())))
            path = tmp_path / f"{fixture.stem}_{i}.evt"
            path.write_bytes(data)
            for xml in (False, True):
                expected = run_clean(exe, path, ["-X"] if xml else [])
                if expected is None:
                    continue  # Chadwick exits, crashes or has undefined behaviour here
                try:
                    out = port_output(data, use_xml=xml)
                except (ValueError, IndexError):
                    continue  # the port raises where Chadwick would misbehave silently
                assert expected == out, (path.name, xml)
                checked += 1
    assert checked > 30
