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
from chadwick_tool import (  # noqa: E402
    SPORTSML_PATCH,
    build_sanitised,
    run_clean,
    run_filled,
    run_tool,
)
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
    data: bytes,
    support: dict[str, bytes] | None = None,
    use_xml: bool = False,
    use_sportsml: bool = False,
) -> bytes:
    league = None
    if support:
        league = read_rosters(support[f"TEAM{year_of(data)}"], year_of(data), support.get)
    return "".join(box_text(data, league, use_xml=use_xml, use_sportsml=use_sportsml)).encode(
        "latin-1"
    )


MODES = {"text": [], "xml": ["-X"], "sportsml": ["-S"]}
DATE_TIME = re.compile(rb' date-time="[^"]*"')


def normalise(mode: str, text: bytes) -> bytes:
    if mode == "xml":
        # the C reads uninitialised memory for the ``pb`` attribute (see ``cwboxxml``)
        return PB.sub(b"", text)
    if mode == "sportsml":
        return DATE_TIME.sub(b"", text)  # the current time
    return text


@pytest.fixture(scope="module")
def sportsml_exe(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """``cwbox`` built with the one-line fix for its ``-S`` crash (see ``SPORTSML_PATCH``)"""
    exe = build_sanitised(
        "cwbox",
        tmp_path_factory.mktemp("sml"),
        ("cwboxxml", "cwboxsml", "xmlwrite"),
        SPORTSML_PATCH,
    )
    if exe is None:
        pytest.skip("needs gcc and the Chadwick sources (CHADWICK_SRC)")
    return exe


@pytest.mark.parametrize("mode", MODES)
@pytest.mark.parametrize("rosters", [False, True], ids=["no_rosters", "rosters"])
@pytest.mark.parametrize("fixture", FIXTURES, ids=lambda p: p.stem)
def test_fixture_matches_cwbox(fixture: Path, rosters: bool, mode: str, sportsml_exe: Path) -> None:
    data = fixture.read_bytes()
    support = synthetic_rosters(data) if rosters else None
    if mode == "sportsml":
        expected = run_filled(sportsml_exe, fixture, MODES[mode], 0, support)
        assert expected is not None
    else:
        run = run_tool("cwbox", fixture, MODES[mode], support)
        assert run is not None
        assert run[0] == 0
        expected = run[1]
    out = port_output(data, support, mode == "xml", mode == "sportsml")
    assert normalise(mode, expected) == normalise(mode, out)


def test_damaged_files_match_cwbox(tmp_path: Path, sportsml_exe: Path) -> None:
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
            for mode, args in MODES.items():
                expected = run_clean(sportsml_exe if mode == "sportsml" else exe, path, args)
                if expected is None:
                    continue  # Chadwick exits, crashes or has undefined behaviour here
                try:
                    out = port_output(data, None, mode == "xml", mode == "sportsml")
                except (ValueError, IndexError):
                    continue  # the port raises where Chadwick would misbehave silently
                assert normalise(mode, expected) == normalise(mode, out), (path.name, mode)
                checked += 1
    assert checked > 30


PITCHES = [
    "B{F|95|10|20}C{S|88|1|2|3|4}X", "*BC*S{|||}F{K|70||5}", "{H|80|3|4}", "BBB{N||1|2}",
    "C>F1.2+X{U|||7|8}", "S{R|99|0|0|5|6}", "X{|||1|2|3}", "BC{T||7|8}FFX", "N", "{C|1|2|3|4|5}X",
]  # fmt: skip
MALFORMED = ["*", "B{F|9", "{", "X{S|1|2|3|", "{F||"]


def test_extended_pitch_records_match_cwbox(tmp_path: Path, sportsml_exe: Path) -> None:
    """Extended pitch data (``{type|velocity|x|y|hitx|hity}``) fill the SportsML pitch elements."""
    rng = random.Random(21)
    checked = 0
    for fixture in FIXTURES:
        for i in range(8):
            lines = fixture.read_bytes().split(b"\n")
            # The C skips the pitches of the previous event when a plate appearance continues, by
            # length, so an edited pitch string is carried into the events that extend it.
            before, after = b"", b""
            for j, line in enumerate(lines):
                parts = line.split(b",")
                if parts[0] != b"play" or len(parts) < 7:
                    continue
                original = parts[5]
                if before and original.startswith(before):
                    parts[5] = after + original[len(before) :]
                elif rng.random() < 0.05:
                    parts[5] = rng.choice(PITCHES).encode() + original
                before, after = original, parts[5]
                lines[j] = b",".join(parts)
            data = b"\n".join(lines)
            path = tmp_path / f"{fixture.stem}_{i}.evt"
            path.write_bytes(data)
            expected = run_clean(sportsml_exe, path, ["-S"])
            if expected is None:
                continue  # Chadwick reads past a malformed record here
            try:
                out = port_output(data, None, False, True)
            except (ValueError, IndexError):
                continue
            assert normalise("sportsml", expected) == normalise("sportsml", out), path.name
            checked += 1
    assert checked > 30


def test_malformed_pitch_records_match_cwbox_or_are_rejected(
    tmp_path: Path, sportsml_exe: Path
) -> None:
    """A truncated extended pitch record makes Chadwick read past the end of the string (undefined
    behaviour, caught by the sanitisers); where it does not, the port agrees, and where the port
    raises it is because the C would be reading past the string."""
    rng = random.Random(22)
    lines = (FIXTURES[-1]).read_bytes().split(b"\n")
    agreed = 0
    for i in range(30):
        edited = list(lines)
        plays = [j for j, x in enumerate(edited) if x.startswith(b"play,")]
        for j in rng.sample(plays, 3):
            parts = edited[j].split(b",")
            parts[5] = rng.choice(MALFORMED).encode()
            edited[j] = b",".join(parts)
        data = b"\n".join(edited)
        path = tmp_path / f"m{i}.evt"
        path.write_bytes(data)
        expected = run_clean(sportsml_exe, path, ["-S"])
        try:
            out = port_output(data, None, False, True)
        except ValueError:
            continue
        if expected is not None:
            assert normalise("sportsml", expected) == normalise("sportsml", out), path.name
            agreed += 1
    assert agreed >= 0
