"""Port side of the scripted edits and writers of ``write_dump.c`` (script format: see there)."""

from retrosheetpy.cw.book import Scorebook
from retrosheetpy.cw.game import Game, event_comment_append, read_games
from retrosheetpy.cw.roster import League, Player, Roster
from retrosheetpy.cw.write import game_write, league_write, roster_write, scorebook_write


def parse_script(text: str) -> list[list[str]]:
    return [line.split("\t") for line in text.split("\n") if line != ""]


def game_op(g: Game, f: list[str]) -> None:
    op = f[0]
    if op == "version":
        g.set_version(f[1])
    elif op == "info_append":
        g.info_append(f[1], f[2])
    elif op == "info_set":
        g.info_set(f[1], f[2])
    elif op == "starter":
        g.starter_append(f[1], f[2], int(f[3]), int(f[4]), int(f[5]))
    elif op == "event":
        g.event_append(int(f[1]), int(f[2]), f[3], f[4], f[5], f[6])
    elif op == "sub":
        g.substitute_append(f[1], f[2], int(f[3]), int(f[4]), int(f[5]))
    elif op in ("data", "stat", "evdata", "line"):
        getattr(g, op + "_append")(list(f[1:]))
    elif op == "set_er":
        g.data_set_er(f[1], int(f[2]))
    elif op == "comment":
        g.comment_append(f[1])
    elif op == "evcomment":
        if g.events:
            event_comment_append(g.events[-1], f[1])
    elif op == "replace":
        g.replace_player(f[1], f[2])
    elif op == "truncate":
        k = int(f[1])
        if k < len(g.events):
            g.truncate(g.events[k])
    elif op == "badj":
        if g.events:
            g.events[-1].batter_hand = f[1][0]
    elif op == "padj":
        if g.events:
            g.events[-1].pitcher_hand = f[1][0]
            g.events[-1].pitcher_hand_id = f[2]
    elif op == "ladj":
        if g.events:
            g.events[-1].ladj_align, g.events[-1].ladj_slot = int(f[1]), int(f[2])
    elif op == "radj":
        if g.events:
            g.events[-1].auto_runner_id, g.events[-1].auto_base = f[1], int(f[2])


def write_games(data: bytes, script: list[list[str]]) -> str:
    out = []
    for g in read_games(data):
        for f in script:
            game_op(g, f)
        out.append(game_write(g))
    return "".join(out)


def write_book(data: bytes, script: list[list[str]]) -> str:
    book = Scorebook()
    if book.read(data) < 0:
        return "read=-1\n"
    for f in script:
        if f[0] == "reshuffle":
            k, rev = int(f[1]), int(f[2])
            m = len(book.games)
            ids = [book.games[(j + k) % (m or 1)].game_id for j in range(m)]
            if rev:
                ids.reverse()
            removed = [book.remove_game(i) for i in ids]
            for game in removed:
                book.insert_game(game)
        elif f[0] == "remove":
            book.remove_game(f[1])
    return scorebook_write(book)


def write_roster(data: bytes, script: list[list[str]]) -> str:
    r = Roster("T", "L", "C", "N")
    r.read(data)
    for f in script:
        op = f[0]
        if op in ("insert", "append"):
            p = Player(f[1], f[2], f[3], f[4][:1] or "\0", f[5][:1] or "\0")
            (r.player_insert if op == "insert" else r.player_append)(p)
        elif op in ("first", "last"):
            p = r.player_find(f[1])
            if p:
                (p.set_first_name if op == "first" else p.set_last_name)(f[2])
        elif op == "city":
            r.set_city(f[1])
        elif op == "nick":
            r.set_nickname(f[1])
        elif op == "league":
            r.set_league(f[1])
    return (
        roster_write(r)
        + f"count={r.player_count()} city={r.city} nick={r.nickname} league={r.league}\n"
    )


def write_league(data: bytes, script: list[list[str]]) -> str:
    lg = League()
    lg.read(data)
    for f in script:
        if f[0] == "append":
            lg.roster_append(Roster(f[1], f[2], f[3], f[4]))
    return league_write(lg)


MODES = {"game": write_games, "book": write_book, "roster": write_roster, "league": write_league}
