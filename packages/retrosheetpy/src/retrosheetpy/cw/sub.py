"""Port of Chadwick's ``cwsub`` (``src/cwtools/cwsub.c``), the substitution descriptor.

Chadwick is Copyright (c) 2002-2023 Dr T L Turocy and the Chadwick Baseball
Bureau, licensed GPL-2.0-or-later; this module is a derivative of it and keeps
that notice. One function per ``cwsub`` field, in the same order, each returning
the text the C ``sprintf`` writes. ``ascii`` is the C global of the same name:
true for the comma-delimited quoted format (``-a``, the default), false for the
fixed-width Fortran format (``-ft``).

A C ``NULL`` string printed through ``%s`` is "(null)" (glibc); ``None`` renders
that way here so a lineup slot with no player matches.
"""

from collections.abc import Callable, Iterator

from retrosheetpy.cw import game as cwgame
from retrosheetpy.cw.game import Appearance, Game
from retrosheetpy.cw.gameiter import GameIter
from retrosheetpy.cw.roster import League
from retrosheetpy.cw.tools import iterate_games

Field = Callable[[bool, GameIter, Appearance], str]


def _s(value: str | None) -> str:
    return "(null)" if value is None else value


def _str(ascii_: bool, value: str | None, width: int) -> str:
    """``(ascii) ? "\\"%s\\"" : "%-<width>s"``"""
    return f'"{_s(value)}"' if ascii_ else f"{_s(value):<{width}}"


def _int(ascii_: bool, value: int, width: int, zero: bool = False) -> str:
    """``(ascii) ? "%d" : "%<width>d"`` (or ``%0<width>d``)"""
    if ascii_:
        return str(value)
    return f"{value:0{width}d}" if zero else f"{value:{width}d}"


def _event(gi: GameIter) -> cwgame.Event:
    assert gi.event is not None
    return gi.event


def _game_id(a: bool, gi: GameIter, sub: Appearance) -> str:
    return _str(a, gi.game.game_id, 12)


def _inning(a: bool, gi: GameIter, sub: Appearance) -> str:
    return _int(a, _event(gi).inning, 2)


def _batting_team(a: bool, gi: GameIter, sub: Appearance) -> str:
    return str(_event(gi).batting_team)


def _player(a: bool, gi: GameIter, sub: Appearance) -> str:
    return _str(a, sub.player_id, 8)


def _team(a: bool, gi: GameIter, sub: Appearance) -> str:
    return str(sub.team)


def _slot(a: bool, gi: GameIter, sub: Appearance) -> str:
    return str(sub.slot)


def _position(a: bool, gi: GameIter, sub: Appearance) -> str:
    return _int(a, sub.pos, 2)


def _removed_player(a: bool, gi: GameIter, sub: Appearance) -> str:
    return _str(a, gi.state.lineups[sub.slot][sub.team].player_id, 8)


def _removed_position(a: bool, gi: GameIter, sub: Appearance) -> str:
    return _int(a, gi.state.lineups[sub.slot][sub.team].position, 2)


def _event_number(a: bool, gi: GameIter, sub: Appearance) -> str:
    count = gi.state.event_count
    return _int(a, count if _event(gi).event_text == "NP" else count + 1, 3)


def _count_digit(index: int) -> Field:
    def f(a: bool, gi: GameIter, sub: Appearance) -> str:
        count = _event(gi).count
        if len(count) >= 2 and count[0] != "?" and count[1] != "?":
            return count[index]
        return "0"

    return f


def _pitches(a: bool, gi: GameIter, sub: Appearance) -> str:
    # C: ``while (foo && isspace(*foo)) foo++`` -- bevent leaves leading whitespace out
    return _str(a, _event(gi).pitches.lstrip(" \t\n\v\f\r"), 20)


def _pitch_count(criterion: frozenset[str]) -> Field:
    def f(a: bool, gi: GameIter, sub: Appearance) -> str:
        return _int(a, cwgame.count_pitches(_event(gi).pitches, criterion), 2, zero=True)

    return f


# (function, header, description) for fields 0-24
FIELDS: tuple[tuple[Field, str, str], ...] = (
    (_game_id, "GAME_ID", "game id"),
    (_inning, "INN_CT", "inning"),
    (_batting_team, "BAT_HOME_ID", "batting team"),
    (_player, "SUB_ID", "substitute"),
    (_team, "SUB_HOME_ID", "team"),
    (_slot, "SUB_LINEUP_ID", "lineup position"),
    (_position, "SUB_FLD_CD", "fielding position"),
    (_removed_player, "REMOVED_ID", "removed player"),
    (_removed_position, "REMOVED_FLD_CD", "position of removed player"),
    (_event_number, "EVENT_ID", "event number"),
    (_count_digit(0), "BALLS_CT", "balls"),
    (_count_digit(1), "STRIKES_CT", "strikes"),
    (_pitches, "PITCH_SEQ_TX", "pitch sequence"),
    (
        _pitch_count(cwgame.PITCH_BALL_THROWN),
        "PA_BALL_CT",
        "number of balls thrown in plate appearance",
    ),
    (
        _pitch_count(cwgame.PITCH_BALL_CALLED),
        "PA_CALLED_BALL_CT",
        "number of called balls in plate appearance",
    ),
    (
        _pitch_count(cwgame.PITCH_BALL_INTENTIONAL),
        "PA_INTENT_BALL_CT",
        "number of intentional balls in plate appearance",
    ),
    (
        _pitch_count(cwgame.PITCH_BALL_PITCHOUT),
        "PA_PITCHOUT_BALL_CT",
        "number of pitchouts in plate appearance",
    ),
    (
        _pitch_count(cwgame.PITCH_BALL_HIT_BATTER),
        "PA_HITBATTER_BALL_CT",
        "number of pitches hitting batter in plate appearance",
    ),
    (
        _pitch_count(cwgame.PITCH_BALL_OTHER),
        "PA_OTHER_BALL_CT",
        "number of other balls in plate appearance",
    ),
    (
        _pitch_count(cwgame.PITCH_STRIKE_THROWN),
        "PA_STRIKE_CT",
        "number of strikes thrown in plate appearance",
    ),
    (
        _pitch_count(cwgame.PITCH_STRIKE_CALLED),
        "PA_CALLED_STRIKE_CT",
        "number of called strikes in plate appearance",
    ),
    (
        _pitch_count(cwgame.PITCH_STRIKE_SWINGING),
        "PA_SWINGMISS_STRIKE_CT",
        "number of swinging strikes in plate appearance",
    ),
    (
        _pitch_count(cwgame.PITCH_STRIKE_FOUL),
        "PA_FOUL_STRIKE_CT",
        "number of foul balls in plate appearance",
    ),
    (
        _pitch_count(cwgame.PITCH_STRIKE_INPLAY),
        "PA_INPLAY_STRIKE_CT",
        "number of balls in play in plate appearance",
    ),
    (
        _pitch_count(cwgame.PITCH_STRIKE_OTHER),
        "PA_OTHER_STRIKE_CT",
        "number of other strikes in plate appearance",
    ),
)

COLUMNS = tuple(header for _, header, _ in FIELDS)
MAX_FIELD = len(FIELDS) - 1


def header_line(fields: tuple[int, ...] = tuple(range(MAX_FIELD + 1))) -> str:
    """``cwsub_initialize`` with ``-n``: the quoted column names (ascii format only)."""
    return ",".join(f'"{FIELDS[i][1]}"' for i in fields)


def game_lines(
    game: Game,
    ascii_: bool = True,
    fields: tuple[int, ...] = tuple(range(MAX_FIELD + 1)),
) -> Iterator[str]:
    """``cwsub_process_game``: one output line per substitution of the game."""
    gi = GameIter(game)
    while gi.event is not None:
        for sub in gi.event.subs:
            sep = "," if ascii_ else ""
            yield sep.join(FIELDS[i][0](ascii_, gi, sub) for i in fields)
        gi.next()


def sub_lines(
    data: bytes,
    league: League | None = None,
    game_id: str = "",
    first_date: str = "0101",
    last_date: str = "1231",
    ascii_: bool = True,
    fields: tuple[int, ...] = tuple(range(MAX_FIELD + 1)),
) -> Iterator[str]:
    """Lines for the selected games of an event file, as ``cwsub`` prints them."""
    for game, _visitors, _home in iterate_games(data, league, game_id, first_date, last_date):
        yield from game_lines(game, ascii_, fields)
