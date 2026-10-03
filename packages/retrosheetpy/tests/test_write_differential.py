"""The port's writers and edit functions against Chadwick's own.

``tests/reference/write_dump.c`` is compiled against the real Chadwick sources: it reads a file,
applies a script of edits (``cw_game_info_set``, ``cw_game_replace_player``,
``cw_scorebook_insert_game``, ``cw_roster_player_insert`` ...) and writes it back with
``cw_game_write``, ``cw_scorebook_write``, ``cw_roster_write`` or ``cw_league_write``.
``reference/write_dump.py`` does the same with the port. The bytes written must be identical.
"""

import random
import subprocess
from pathlib import Path

import pytest
from retrosheetpy.cw.game import read_games
from test_reader_differential import (
    FIXTURES,
    HERE,
    ROSTERS,
    SRC,
    damage,
    event_sample,
    pytestmark,  # noqa: F401  (skip without gcc / Chadwick sources)
)

from write_dump import MODES, parse_script  # isort: skip


@pytest.fixture(scope="module")
def harness(tmp_path_factory):
    out = tmp_path_factory.mktemp("wharness") / "write_dump"
    cmd = ["gcc", "-O1", "-w", "-I", str(SRC / "cwlib"), "-I", str(SRC)]
    cmd += [
        str(HERE / "reference" / "write_dump.c"),
        *map(str, sorted((SRC / "cwlib").glob("*.c"))),
    ]
    subprocess.run([*cmd, "-o", str(out)], check=True)
    return out


def c_write(harness: Path, data: bytes, tmp: Path, mode: str, script: str = "") -> bytes | None:
    (tmp / "f.dat").write_bytes(data)
    (tmp / "s.txt").write_bytes(script.encode("latin-1"))
    run = subprocess.run(
        [str(harness), str(tmp / "f.dat"), mode, str(tmp / "s.txt")], capture_output=True
    )
    return run.stdout if run.returncode == 0 else None


def port_write(data: bytes, mode: str, script: str = "") -> bytes | None:
    try:
        return MODES[mode](data, parse_script(script)).encode("latin-1")
    except ValueError:  # where the C crashes
        return None


def check(harness, tmp, data, mode, script=""):
    expected = c_write(harness, data, tmp, mode, script)
    if expected is None:
        return False
    assert port_write(data, mode, script) == expected, (data, script)
    return True


@pytest.mark.parametrize("path", sorted(FIXTURES.glob("*.evt")), ids=lambda p: p.stem)
@pytest.mark.parametrize("mode", ["game", "book"])
def test_fixture_written_equals_chadwick(harness, tmp_path, path, mode):
    assert check(harness, tmp_path, path.read_bytes(), mode)


WORDS = [
    "", "a", "x,y", 'q"r', "wp", "lp", "save", "date", "number", "inputter", "scorer", "umphome",
         "ump1b", "er", "ABC01", "zzz01", "1", "2", "2007/04/05", "0", "k",
]  # fmt: skip


def random_script(rnd: random.Random, ids: list[str]) -> str:
    def w() -> str:
        return rnd.choice([*WORDS, *ids]) if ids else rnd.choice(WORDS)

    lines = []
    for _ in range(rnd.randint(1, 14)):
        op = rnd.choice(
            ["version", "info_append", "info_set", "info_set", "starter", "event", "sub", "data",
             "stat", "evdata", "line", "set_er", "set_er", "comment", "evcomment", "replace",
             "replace", "truncate", "badj", "padj", "ladj", "radj"]
        )  # fmt: skip
        n = {"version": 1, "info_append": 2, "info_set": 2, "starter": 5, "event": 6, "sub": 5,
             "set_er": 2, "comment": 1, "evcomment": 1, "replace": 2, "truncate": 1, "badj": 1,
             "padj": 2, "ladj": 2, "radj": 2}.get(op, rnd.randint(1, 5))  # fmt: skip
        nums = {"starter": (2, 3, 4), "event": (0, 1), "sub": (2, 3, 4), "set_er": (1,),
                "truncate": (0,), "ladj": (0, 1), "radj": (1,)}.get(op, ())  # fmt: skip
        fields = [str(rnd.randint(0, 12)) if i in nums else w() for i in range(n)]
        if op in ("badj", "padj"):
            fields[0] = rnd.choice("LRB? ")
        lines.append("\t".join([op, *fields]))
    return "\n".join(lines) + "\n"


def test_game_edits_equal_chadwick(harness, tmp_path):
    rnd = random.Random(5)
    files = [p.read_bytes() for p in sorted(FIXTURES.glob("*.evt"))]
    compared = 0
    for _ in range(400):
        d = bytes(event_sample(rnd, files))
        games = list(read_games(d))
        ids = sorted(
            {e.batter for g in games for e in g.events}
            | {x.player_id for g in games for x in g.starters}
        )
        compared += check(harness, tmp_path, d, "game", random_script(rnd, ids[:20]))
    assert compared > 300


def test_damaged_games_written_equal_chadwick(harness, tmp_path):
    rnd = random.Random(8)
    files = [p.read_bytes() for p in sorted(FIXTURES.glob("*.evt"))]
    compared = 0
    for _ in range(300):
        d = damage(rnd, event_sample(rnd, files))
        if not d.startswith(b"id,"):
            d[0:0] = b"id,X\n"
        compared += check(harness, tmp_path, bytes(d), "game")
    assert compared > 250


def test_scorebook_edits_equal_chadwick(harness, tmp_path):
    rnd = random.Random(13)
    files = [p.read_bytes() for p in sorted(FIXTURES.glob("*.evt"))]
    heads = [b"", b'com,"a note"\n', b'com,"x"\ncom,"y"\n']
    compared = 0
    for _ in range(200):
        d = rnd.choice(heads) + bytes(event_sample(rnd, files))
        script = "".join(
            f"reshuffle\t{rnd.randint(0, 9)}\t{rnd.randint(0, 1)}\n"
            if rnd.random() < 0.7
            else f"remove\t{rnd.choice(['X', 'NYA200704050', 'BOS200704050'])}\n"
            for _ in range(rnd.randint(1, 3))
        )
        compared += check(harness, tmp_path, d, "book", script)
    assert compared > 120


def roster_script(rnd: random.Random) -> str:
    lines = []
    for _ in range(rnd.randint(1, 10)):
        op = rnd.choice(["insert", "insert", "append", "first", "last", "city", "nick", "league"])
        pid = rnd.choice(["aaaa001", "zzzz001", "m", "abc01", "ABC01", "bbbb001", "1"])
        if op in ("insert", "append"):
            lines.append(f"{op}\t{pid}\tLast\tFirst\t{rnd.choice('LRB?')}\t{rnd.choice('LR?')}")
        elif op in ("first", "last"):
            lines.append(f"{op}\t{pid}\tNew{rnd.randint(0, 9)}")
        else:
            lines.append(f"{op}\tv{rnd.randint(0, 9)}")
    return "\n".join(lines) + "\n"


@pytest.mark.parametrize("path", ROSTERS, ids=lambda p: f"{p.parent.name}/{p.name}")
def test_roster_and_team_files_written_equal_chadwick(harness, tmp_path, path):
    mode = "league" if path.name.startswith("TEAM") else "roster"
    rnd = random.Random(path.name)
    script = roster_script(rnd) if mode == "roster" else "append\tNEW\tAL\tCity\tNick\n"
    data = path.read_bytes()
    assert check(harness, tmp_path, data, mode)
    assert check(harness, tmp_path, data, mode, script)


@pytest.mark.parametrize("mode", ["roster", "league"])
def test_damaged_roster_files_written_equal_chadwick(harness, tmp_path, mode):
    rnd = random.Random(4)
    files = [p.read_bytes() for p in ROSTERS if p.name.startswith("TEAM") == (mode == "league")]
    for _ in range(200):
        d = bytes(damage(rnd, bytearray(rnd.choice(files))))
        script = roster_script(rnd) if mode == "roster" else ""
        check(harness, tmp_path, d, mode, script)


def test_scorebook_insert_with_equal_date_and_number(harness, tmp_path):
    """Games sharing date and number keep the order the C ``strcmp < 0`` test gives them."""
    rnd = random.Random(17)
    compared = 0
    for path in sorted(FIXTURES.glob("*.evt")):
        body = path.read_bytes()
        start = body.index(b"id,")
        end = body.find(b"\nid,", start) + 1 or len(body)
        game = body[start:end]
        first_id = game.split(b"\n")[0][3:]
        copies = b"".join(game.replace(b"id," + first_id, b"id,COPY%d" % i, 1) for i in range(4))
        data = game + copies
        for _ in range(10):
            script = f"reshuffle\t{rnd.randint(0, 9)}\t{rnd.randint(0, 1)}\n"
            compared += check(harness, tmp_path, data, "book", script)
    assert compared > 60
