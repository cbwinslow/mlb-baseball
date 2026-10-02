"""Port of Chadwick's ``cwbox`` plain-text mode (``src/cwtools/cwbox.c``), the boxscore generator.

Chadwick is Copyright (c) 2002-2023 Dr T L Turocy and the Chadwick Baseball
Bureau, licensed GPL-2.0-or-later; this module is a derivative of it and keeps
that notice. One function per ``cwbox_print_*`` function, each returning the text
the C ``printf`` calls write. The XML output (``-X``) is in ``cwboxxml``, SportsML (``-S``) in
``cwboxsml``.

A C ``NULL`` string printed through ``%s`` is "(null)" (glibc). Where the C
dereferences ``NULL`` or reads an uninitialised variable, this port raises
``ValueError``. Messages Chadwick prints to stderr go to ``logging``.
Like the C (``cwbox_print_header``), a day game is never marked ``(D)``: the C compares
the ``daynight`` field with the literal ``"g_day"`` (the same typo is kept).
"""

import logging
from collections.abc import Iterator
from typing import TypeVar

from retrosheetpy.cw.box import (
    BoxEvent,
    BoxPitcher,
    BoxPlayer,
    Boxscore,
    box_create,
    get_starter,
    get_starting_pitcher,
)
from retrosheetpy.cw.cwboxsml import print_sportsml
from retrosheetpy.cw.cwboxxml import print_xml
from retrosheetpy.cw.file import scan_int
from retrosheetpy.cw.game import Game
from retrosheetpy.cw.lint import game_lint
from retrosheetpy.cw.roster import League, Player, Roster
from retrosheetpy.cw.tools import iterate_games
from retrosheetpy.cw.xmlwrite import XMLDoc, xml_document_cleanup

log = logging.getLogger("retrosheetpy.cw")

POSITIONS = ["", "p", "c", "1b", "2b", "3b", "ss", "lf", "cf", "rf", "dh", "ph", "pr"]
MARKERS = ["*", "+", "#"]


def _s(value: str | None) -> str:
    return "(null)" if value is None else value


_T = TypeVar("_T")


def _deref(value: _T | None) -> _T:
    if value is None:
        raise ValueError("NULL dereference in Chadwick")
    return value


def _cdiv(a: int, b: int) -> int:
    """C integer division (truncates toward zero)"""
    q = abs(a) // abs(b)
    return q if (a >= 0) == (b >= 0) else -q


def _cmod(a: int, b: int) -> int:
    return a - b * _cdiv(a, b)


def _info(game: Game, key: str) -> str | None:
    return game.info_lookup(key)


def _team(game: Game, roster: Roster | None, key: str) -> str:
    """``(roster) ? roster->city : cw_game_info_lookup(game, key)``"""
    return roster.city if roster is not None else _s(_info(game, key))


def _first(player: Player) -> str:
    """``first_name[0]``: the terminating NUL when the first name is empty"""
    return player.first_name[:1] or "\0"


def _buffer_name(player: Player) -> str:
    """``sprintf(name, "%s %c", last_name, first_name[0])``: the C string ends at the NUL that
    ``%c`` writes for an empty first name"""
    return f"{player.last_name} {player.first_name[:1]}"


def _print_header(game: Game, visitors: Roster | None, home: Roster | None) -> str:
    """``cwbox_print_header``"""
    date = _deref(_info(game, "date"))
    year = scan_int(date, 0)
    month = day = None
    if year is not None and date[year[1] : year[1] + 1] == "/":
        month = scan_int(date, year[1] + 1)
        if month is not None and date[month[1] : month[1] + 1] == "/":
            day = scan_int(date, month[1] + 1)
    if year is None or month is None or day is None:
        raise ValueError(f"unparsable date {date!r} (uninitialised values in Chadwick)")
    g_year, g_month, g_day = year[0], month[0], day[0]
    number = _deref(_info(game, "number"))
    away, host = _team(game, visitors, "visteam"), _team(game, home, "hometeam")
    if number == "0":
        out = f"     Game of {g_month}/{g_day}/{g_year} -- {away} at {host}"
    else:
        out = f"     Game of {g_month}/{g_day}/{g_year}, game {number} -- {away} at {host}"
    daynight = _info(game, "daynight")
    if daynight is not None and daynight == "g_day":
        out += " (D)\n"
    elif daynight is not None and daynight == "night":
        out += " (N)\n"
    else:
        out += "\n"
    return out + "\n"


def _position(code: int) -> str:
    if not 0 <= code < len(POSITIONS):
        raise ValueError(f"position {code} out of range (undefined behaviour in C)")
    return POSITIONS[code]


def _print_player(player: BoxPlayer, roster: Roster | None) -> str:
    """``cwbox_print_player``"""
    bio = roster.player_find(player.player_id) if roster is not None else None
    name = _buffer_name(bio) if bio is not None else player.name

    if player.ph_inn > 0 and player.positions[0] != 11:
        posstr = "ph"
    elif player.pr_inn > 0 and player.positions[0] != 12:
        posstr = "pr"
    else:
        posstr = ""
    for pos in range(player.num_positions):
        if len(posstr) > 0:
            posstr += "-"
        posstr += _position(player.positions[pos])

    if len(posstr) <= 10:
        if len(posstr) + len(name) > 18:
            outstr = name[: 18 - len(posstr)] + ", "
        else:
            outstr = name + ", "
        outstr += posstr
    else:
        outstr = name + ", " + _position(player.positions[0]) + ",..."

    b = player.batting
    if b.bi != -1:
        return f"{outstr:<20} {b.ab:2d} {b.r:2d} {b.h:2d} {b.bi:2d}"
    return f"{outstr:<20} {b.ab:2d} {b.r:2d} {b.h:2d}   "


def _print_pitcher(
    game: Game, pitcher: BoxPitcher, roster: Roster | None, note_count: list[int]
) -> str:
    """``cwbox_print_pitcher``; ``note_count`` is the C ``int *``, a one-item list"""
    bio = roster.player_find(pitcher.player_id) if roster is not None else None
    name = _buffer_name(bio) if bio is not None else pitcher.name

    if _info(game, "wp") is not None and _info(game, "wp") == pitcher.player_id:
        name += " (W)"
    elif _info(game, "lp") is not None and _info(game, "lp") == pitcher.player_id:
        name += " (L)"
    elif _info(game, "save") is not None and _info(game, "save") == pitcher.player_id:
        name += " (S)"

    p = pitcher.pitching
    if p.xbinn > 0 and p.xb > 0:
        for _ in range(note_count[0] // 3 + 1):
            name += MARKERS[note_count[0] % 3]
        note_count[0] += 1

    out = f"{name:<20} {_cdiv(p.outs, 3):2d}.{_cmod(p.outs, 3):1d} {p.h:2d} {p.r:2d}"
    out += f" {p.er:2d}" if p.er != -1 else "   "
    out += f" {p.bb:2d}" if p.bb != -1 else "   "
    out += f" {p.so:2d}\n" if p.so != -1 else "   \n"
    return out


def _game_find_name(game: Game, player_id: str | None) -> str | None:
    """``cwbox_game_find_name``: a player's name from an appearance record, used when no
    roster file is available"""
    for app in game.starters:
        if app.player_id == _deref(player_id):
            return app.name
    for event in game.events:
        for app in event.subs:
            if app.player_id == _deref(player_id):
                return app.name
    return None


def _ordinal_suffix(n: int) -> str:
    if _cmod(n, 10) == 1 and n != 11:
        return "st"
    if _cmod(n, 10) == 2 and n != 12:
        return "nd"
    if _cmod(n, 10) == 3 and n != 13:
        return "rd"
    return "th"


def _print_pitcher_apparatus(box: Boxscore) -> str:
    """``cwbox_print_pitcher_apparatus``"""
    out = ""
    count = 0
    for t in range(2):
        pitcher = get_starting_pitcher(box, t)
        while pitcher is not None:
            p = pitcher.pitching
            if p.xbinn > 0 and p.xb > 0:
                out += "  " + MARKERS[count % 3] * (count // 3 + 1)
                out += f" Pitched to {p.xb} batter{'' if p.xb == 1 else 's'} in {p.xbinn}"
                out += _ordinal_suffix(p.xbinn) + "\n"
                count += 1
            pitcher = pitcher.next
    return out


def _print_linescore(
    game: Game, box: Boxscore, visitors: Roster | None, home: Roster | None
) -> str:
    """``cwbox_print_linescore``"""
    out = ""
    for t in range(2):
        runs = 0
        out += (
            f"{_team(game, visitors if t == 0 else home, 'visteam' if t == 0 else 'hometeam'):<17}"
        )
        i = 1
        while i < 50:
            if box.linescore[i][0] < 0 and box.linescore[i][1] < 0:
                break
            score = box.linescore[i][t]
            if score >= 10:
                out += f"({score})"
                runs += score
            elif score >= 0:
                out += str(score)
                runs += score
            else:
                out += "x"
            if i % 3 == 0:
                out += " "
            i += 1
        if (i - 1) % 3 != 0:
            out += " "
        out += f"-- {runs:2d}\n"

    if box.outs_at_end != 3:
        plural = "" if box.outs_at_end == 1 else "s"
        if not box.walk_off:
            out += f"  {box.outs_at_end} out{plural} when game ended.\n"
        else:
            out += f"  {box.outs_at_end} out{plural} when winning run was scored.\n"
    return out


def _print_play(
    label: str,
    counts: list[int],
    game: Game,
    visitors: Roster | None,
    home: Roster | None,
) -> str:
    """``cwbox_print_double_play`` and ``cwbox_print_triple_play``"""
    if counts[0] == 0 and counts[1] == 0:
        return ""
    away, host = _team(game, visitors, "visteam"), _team(game, home, "hometeam")
    out = f"{label} -- "
    if counts[0] > 0 and counts[1] == 0:
        out += f"{away} {counts[0]}\n"
    elif counts[0] == 0 and counts[1] > 0:
        out += f"{host} {counts[1]}\n"
    else:
        out += f"{away} {counts[0]}, {host} {counts[1]}\n"
    return out


def _print_lob(game: Game, box: Boxscore, visitors: Roster | None, home: Roster | None) -> str:
    """``cwbox_print_lob``"""
    if box.lob[0] == 0 and box.lob[1] == 0:
        return ""
    away, host = _team(game, visitors, "visteam"), _team(game, home, "hometeam")
    return f"LOB -- {away} {box.lob[0]}, {host} {box.lob[1]}\n"


def _event_player(event: BoxEvent, index: int) -> str:
    """``event->players[index]`` handed to ``strcmp``/``%s`` (``NULL`` crashes ``strcmp``)"""
    if index >= len(event.players):
        raise ValueError("player index out of range (undefined behaviour in C)")
    return _deref(event.players[index])


def _find_player(
    visitors: Roster | None, home: Roster | None, player_id: str | None
) -> Player | None:
    """``if (visitors) bio = find(visitors, ...); if (!bio && home) bio = find(home, ...)``"""
    bio = visitors.player_find(player_id) if visitors is not None else None
    if bio is None and home is not None:
        bio = home.player_find(player_id)
    return bio


def _print_player_apparatus(
    game: Game,
    events: list[BoxEvent],
    index: int,
    label: str,
    visitors: Roster | None,
    home: Roster | None,
) -> str:
    """``cwbox_print_player_apparatus``: generic output for a list of events (2B, 3B, WP, ...)"""
    if not events:
        return ""
    out = f"{label} -- "
    comma = False
    for at, event in enumerate(events):
        if event.mark > 0:
            continue
        count = 0
        for search in events[at:]:
            if _event_player(event, index) == _event_player(search, index):
                count += 1
                search.mark = 1
        player_id = _event_player(event, index)
        bio = _find_player(visitors, home, player_id)
        name = _game_find_name(game, player_id) if bio is None else None
        if comma:
            out += ", "
        suffix = "" if count == 1 else f" {count}"
        if bio is not None:
            out += f"{bio.last_name} {_first(bio)}{suffix}"
        elif name is not None:
            out += f"{name}{suffix}"
        else:
            out += f"{player_id}{suffix}"
        comma = True
    out += "\n"
    for event in events:
        event.mark = 0
    return out


def _print_hbp_apparatus(
    game: Game, events: list[BoxEvent], visitors: Roster | None, home: Roster | None
) -> str:
    """``cwbox_print_hbp_apparatus``"""
    if not events:
        return ""
    out = "HBP -- "
    comma = False
    for at, event in enumerate(events):
        if event.mark > 0:
            continue
        count = 0
        for search in events[at:]:
            if _event_player(event, 0) == _event_player(search, 0) and _event_player(
                event, 1
            ) == _event_player(search, 1):
                count += 1
                search.mark = 1
        batter_id, pitcher_id = _event_player(event, 0), _event_player(event, 1)
        batter = _find_player(visitors, home, batter_id)
        batter_name = _game_find_name(game, batter_id) if batter is None else None
        pitcher = _find_player(visitors, home, pitcher_id)
        pitcher_name = _game_find_name(game, pitcher_id) if pitcher is None else None
        if comma:
            out += ", "
        if pitcher is not None:
            out += f"by {pitcher.last_name} {_first(pitcher)} "
        elif pitcher_name is not None:
            out += f"by {pitcher_name} "
        else:
            out += f"by {pitcher_id} "
        if batter is not None:
            out += f"({batter.last_name} {_first(batter)})"
        elif batter_name is not None:
            out += f"({batter_name})"
        else:
            out += f"({batter_id})"
        if count != 1:
            out += f" {count}"
        comma = True
    out += "\n"
    for event in events:
        event.mark = 0
    return out


def _print_timeofgame(game: Game) -> str:
    """``cwbox_print_timeofgame``"""
    text = _info(game, "timeofgame")
    if text is None:
        return ""
    found = scan_int(text, 0)
    if found is None:
        if text == "":
            raise ValueError("empty timeofgame (uninitialised value in Chadwick)")
        return ""
    if found[0] > 0:
        return f"T -- {_cdiv(found[0], 60)}:{_cmod(found[0], 60):02d}\n"
    return ""


def _print_attendance(game: Game) -> str:
    """``cwbox_print_attendance``"""
    return f"A -- {_s(_info(game, 'attendance'))}\n"


def _print_apparatus(
    game: Game, box: Boxscore, visitors: Roster | None, home: Roster | None
) -> str:
    """``cwbox_print_apparatus``"""
    out = _print_player_apparatus(game, box.err_list, 0, "E", visitors, home)
    out += _print_play("DP", box.dp, game, visitors, home)
    out += _print_play("TP", box.tp, game, visitors, home)
    out += _print_lob(game, box, visitors, home)
    for events, index, label in (
        (box.b2_list, 0, "2B"),
        (box.b3_list, 0, "3B"),
        (box.hr_list, 0, "HR"),
        (box.sb_list, 0, "SB"),
        (box.cs_list, 0, "CS"),
        (box.sh_list, 0, "SH"),
        (box.sf_list, 0, "SF"),
    ):
        out += _print_player_apparatus(game, events, index, label, visitors, home)
    out += _print_hbp_apparatus(game, box.hp_list, visitors, home)
    for events, index, label in (
        (box.wp_list, 0, "WP"),
        (box.bk_list, 0, "Balk"),
        (box.pb_list, 1, "PB"),
    ):
        out += _print_player_apparatus(game, events, index, label, visitors, home)
    out += _print_timeofgame(game)
    out += _print_attendance(game)
    return out


def print_text(game: Game, box: Boxscore, visitors: Roster | None, home: Roster | None) -> str:
    """``cwbox_print_text``: the boxscore in plain text"""
    note_count = [0]
    slots = [1, 1]
    players: list[BoxPlayer | None] = [get_starter(box, 0, 1), get_starter(box, 1, 1)]
    ab, r, h, bi = [0, 0], [0, 0], [0, 0], [0, 0]
    away, host = _team(game, visitors, "visteam"), _team(game, home, "hometeam")

    out = _print_header(game, visitors, home)
    out += f"  {away:<18} AB  R  H RBI    {host:<18} AB  R  H RBI\n"

    while slots[0] <= 9 or slots[1] <= 9:
        for t in range(2):
            if slots[t] <= 9:
                player = _deref(players[t])
                out += _print_player(player, visitors if t == 0 else home)
                ab[t] += player.batting.ab
                r[t] += player.batting.r
                h[t] += player.batting.h
                if player.batting.bi != -1:
                    bi[t] += player.batting.bi
                else:
                    bi[t] = -1
                players[t] = player.next
                if players[t] is None:
                    # In some National Association games, teams played with 8 players.  This
                    # generalization allows for printing boxscores with empty batting slots.
                    while slots[t] <= 9 and players[t] is None:
                        slots[t] += 1
                        if slots[t] <= 9:
                            players[t] = get_starter(box, t, slots[t])
            else:
                out += f"{'':<32}"
            out += "   "
        out += "\n"

    out += f"{'':<20} -- -- -- -- {'':<22} -- -- -- --\n"
    if bi[0] == -1 or bi[1] == -1:
        out += (
            f"{'':<20} {ab[0]:2d} {r[0]:2d} {h[0]:2d}    {'':<22} "
            f"{ab[1]:2d} {r[1]:2d} {h[1]:2d}   \n"
        )
    else:
        out += (
            f"{'':<20} {ab[0]:2d} {r[0]:2d} {h[0]:2d} {bi[0]:2d} {'':<22} "
            f"{ab[1]:2d} {r[1]:2d} {h[1]:2d} {bi[1]:2d}\n"
        )
    out += "\n"
    out += _print_linescore(game, box, visitors, home)
    out += "\n"

    for t in range(2):
        pitcher = get_starting_pitcher(box, t)
        out += f"  {away if t == 0 else host:<18}   IP  H  R ER BB SO\n"
        while pitcher is not None:
            out += _print_pitcher(game, pitcher, visitors if t == 0 else home, note_count)
            pitcher = pitcher.next
        if t == 0:
            out += "\n"
    out += _print_pitcher_apparatus(box)
    out += "\n"
    out += _print_apparatus(game, box, visitors, home)
    return out + "\f"


def process_game(
    game: Game,
    visitors: Roster | None,
    home: Roster | None,
    use_xml: bool = False,
    doc: XMLDoc | None = None,
    use_sportsml: bool = False,
) -> str | None:
    """``cwbox_process_game`` (text mode; XML with ``use_xml`` as ``-X``; SportsML with
    ``use_sportsml`` as ``-S``, written into ``doc``): the boxscore, or ``None`` when the game
    fails the sanity check (``cw_game_lint``) and is skipped"""
    if not game_lint(game):
        log.warning("WARNING: Sanity check fails for game %s, skipping...", game.game_id)
        return None
    box = box_create(game)
    if visitors is None:
        log.warning("WARNING: In game %s, could not find roster for visiting team.", game.game_id)
    if home is None:
        log.warning("WARNING: In game %s, could not find roster for home team.", game.game_id)
    if use_xml:
        return print_xml(game, box, visitors, home)
    if use_sportsml:
        return print_sportsml(doc, game, box, visitors, home)
    return print_text(game, box, visitors, home)


def box_text(
    data: bytes,
    league: League | None = None,
    game_id: str = "",
    first_date: str = "0101",
    last_date: str = "1231",
    use_xml: bool = False,
    use_sportsml: bool = False,
) -> Iterator[str]:
    """The boxscores of the selected games of an event file, as ``cwbox`` (``cwbox -X`` with
    ``use_xml``, ``cwbox -S`` with ``use_sportsml``) prints them. With ``use_sportsml`` the
    output is one ``sports-content-set`` document for this file (``cwbox_initialize`` and
    ``cwbox_cleanup`` around the games)."""
    doc = XMLDoc("sports-content-set") if use_sportsml else None
    if doc is not None:
        yield doc.take()
    for game, visitors, home in iterate_games(data, league, game_id, first_date, last_date):
        text = process_game(game, visitors, home, use_xml, doc, use_sportsml)
        if text is not None:
            yield text
    if doc is not None:
        xml_document_cleanup(doc)
        yield doc.take()
