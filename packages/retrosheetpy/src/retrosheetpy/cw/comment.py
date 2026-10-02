"""Port of Chadwick's ``cwcomment`` (``src/cwtools/cwcomment.c``), the comment extractor.

Chadwick is Copyright (c) 2002-2023 Dr T L Turocy and the Chadwick Baseball
Bureau, licensed GPL-2.0-or-later; this module is a derivative of it and keeps
that notice. One function per ``cwcomment`` field, in the same order, each
returning the text the C ``sprintf`` writes. ``ascii`` is the C global of the
same name: true for the comma-delimited format (``-a``, the default), false for
the fixed-width Fortran format (``-ft``).

The C walks a linked list of comments (``comment->next``); the port walks the list
of comments of the same game or event by index, which visits the same comments.
Deviation: the C builds each line in a 4096-byte buffer and overruns it on a longer
line (undefined behaviour); the port has no limit.
"""

from collections.abc import Callable, Iterator

from retrosheetpy.cw.game import Comment, Game
from retrosheetpy.cw.gameiter import GameIter
from retrosheetpy.cw.roster import League
from retrosheetpy.cw.tools import iterate_games

Field = Callable[[bool, GameIter, bool, list[Comment], int], str]


def _special(comment: Comment) -> bool:
    """``comment->ejection.person_id || comment->umpchange.person_id``"""
    return (comment.ejection is not None and comment.ejection[0] is not None) or (
        comment.umpchange is not None and comment.umpchange[2] is not None
    )


def _ej(comment: Comment, index: int) -> str:
    """``(x) ? x : ""`` for one of the ejection fields"""
    if comment.ejection is None:
        return ""
    value = comment.ejection[index]
    return "" if value is None else value


def _ump(comment: Comment, index: int) -> str:
    if comment.umpchange is None:
        return ""
    value = comment.umpchange[index]
    return "" if value is None else value


def _game_id(a: bool, gi: GameIter, beginning: bool, coms: list[Comment], at: int) -> str:
    return f'"{gi.game.game_id}"' if a else f"{gi.game.game_id:<12}"


def _event_number(a: bool, gi: GameIter, beginning: bool, coms: list[Comment], at: int) -> str:
    if beginning:
        number = 0
    else:
        assert gi.event is not None
        count = gi.state.event_count
        number = count if gi.event.event_text == "NP" else count + 1
    return str(number) if a else f"{number:3d}"


def _comment(a: bool, gi: GameIter, beginning: bool, coms: list[Comment], at: int) -> str:
    out = '"' if a else ""
    for k in range(at, len(coms)):
        if k != at:
            out += " "
        out += coms[k].text
        if _special(coms[k]):
            break
    return out + ('"' if a else "")


def _quoted(getter: Callable[[Comment], str]) -> Field:
    def f(a: bool, gi: GameIter, beginning: bool, coms: list[Comment], at: int) -> str:
        return f'"{getter(coms[at])}"'

    return f


def _umpchange_inning(a: bool, gi: GameIter, beginning: bool, coms: list[Comment], at: int) -> str:
    return _ump(coms[at], 0)


# (function, header, description) for fields 0-9
FIELDS: tuple[tuple[Field, str, str], ...] = (
    (_game_id, "GAME_ID", "game id"),
    (_event_number, "EVENT_ID", "event num"),
    (_comment, "COMMENT_TX", "comment text"),
    (_quoted(lambda c: _ej(c, 0)), "EJECT_PERSON_ID", "ID of person ejected"),
    (_quoted(lambda c: _ej(c, 1)), "EJECT_PERSON_ROLE_CD", "role of person ejected"),
    (_quoted(lambda c: _ej(c, 2)), "EJECT_UMPIRE_ID", "ID of ejecting umpire"),
    (_quoted(lambda c: _ej(c, 3)), "EJECT_REASON_TX", "reason for ejection"),
    (_umpchange_inning, "UMPCHANGE_INN_CT", "inning of umpire change"),
    (_quoted(lambda c: _ump(c, 1)), "UMPCHANGE_POS_CD", "position umpire assumed"),
    (_quoted(lambda c: _ump(c, 2)), "UMPCHANGE_PERSON_ID", "ID of umpire assuming position"),
)

COLUMNS = tuple(header for _, header, _ in FIELDS)
MAX_FIELD = len(FIELDS) - 1


def header_line(fields: tuple[int, ...] = tuple(range(MAX_FIELD + 1))) -> str:
    """``cwcomment_initialize`` with ``-n``: the quoted column names (ascii format only)."""
    return ",".join(f'"{FIELDS[i][1]}"' for i in fields)


def _lines(
    gi: GameIter,
    comments: list[Comment],
    beginning: bool,
    ascii_: bool,
    fields: tuple[int, ...],
) -> Iterator[str]:
    """The ``while (comment)`` loop of ``cwcomment_process_game`` over one comment list.

    After printing a comment the C moves to the next one when this one is an ejection or an
    umpire change, and otherwise skips ahead to the next ejection or umpire change (the plain
    comments that follow were printed as part of this line's text).
    """
    at = 0
    while at < len(comments):
        sep = "," if ascii_ else ""
        yield sep.join(FIELDS[i][0](ascii_, gi, beginning, comments, at) for i in fields)
        if _special(comments[at]):
            at += 1
        else:
            at += 1
            while at < len(comments) and not _special(comments[at]):
                at += 1


def game_lines(
    game: Game,
    ascii_: bool = True,
    fields: tuple[int, ...] = tuple(range(MAX_FIELD + 1)),
) -> Iterator[str]:
    """``cwcomment_process_game``: the game's comments before the first play, then each play's."""
    gi = GameIter(game)
    yield from _lines(gi, game.comments, True, ascii_, fields)
    while gi.event is not None:
        yield from _lines(gi, gi.event.comments, False, ascii_, fields)
        gi.next()


def comment_lines(
    data: bytes,
    league: League | None = None,
    game_id: str = "",
    first_date: str = "0101",
    last_date: str = "1231",
    ascii_: bool = True,
    fields: tuple[int, ...] = tuple(range(MAX_FIELD + 1)),
) -> Iterator[str]:
    """Lines for the selected games of an event file, as ``cwcomment`` prints them."""
    for game, _visitors, _home in iterate_games(data, league, game_id, first_date, last_date):
        yield from game_lines(game, ascii_, fields)
