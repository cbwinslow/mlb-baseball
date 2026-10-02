"""Port of Chadwick's ``cwgame`` (``src/cwtools/cwgame.c``), the game descriptor generator.

Chadwick is Copyright (c) 2002-2023 Dr T L Turocy and the Chadwick Baseball
Bureau, licensed GPL-2.0-or-later; this module is a derivative of it and keeps
that notice. One function per ``cwgame`` field, each returning the text the C
``sprintf`` writes; ``FIELDS`` and ``EXT_FIELDS`` are the C ``field_data`` and
``ext_field_data`` tables (function, header, description) in the same order. The
C declares the tabulated team totals with macros (``DECLARE_TABULATED_*_FUNC``);
the port builds the same functions with the factories below. ``ascii`` is the C
global of the same name: true for the comma-delimited quoted format (``-a``, the
default), false for the fixed-width Fortran format (``-ft``).

A C ``NULL`` string printed through ``%s`` is "(null)" (glibc). Where the C
dereferences ``NULL``, reads an uninitialised variable (a short date, an
unparsable start time) or indexes an array out of range, this port raises
``ValueError``. Deviation: the C builds each line in a 4096-byte buffer; the port
has no line limit. Entries of ``FIELDS`` that are ``None`` (lineup and finishing
pitcher fields, 46-83) are written by ``game_line`` itself, as in the C.
"""

from collections.abc import Callable, Collection, Iterator
from typing import TypeVar

from retrosheetpy.cw.box import (
    BoxPitcher,
    BoxPlayer,
    Boxscore,
    box_create,
    get_starter,
    get_starting_pitcher,
)
from retrosheetpy.cw.file import cw_atoi, scan_int
from retrosheetpy.cw.game import Game
from retrosheetpy.cw.gameiter import GameIter
from retrosheetpy.cw.roster import League, Roster
from retrosheetpy.cw.tools import iterate_games

Field = Callable[[bool, GameIter, Boxscore, Roster | None, Roster | None], str]

_T = TypeVar("_T")


def _deref(value: _T | None) -> _T:
    if value is None:
        raise ValueError("NULL dereference in Chadwick")
    return value


def _s(value: str | None) -> str:
    return "(null)" if value is None else value


def _cdiv(a: int, b: int) -> int:
    """C integer division (truncates toward zero)"""
    q = abs(a) // abs(b)
    return q if (a >= 0) == (b >= 0) else -q


def _cmod(a: int, b: int) -> int:
    return a - b * _cdiv(a, b)


def _info(gi: GameIter, key: str) -> str | None:
    return gi.game.info_lookup(key)


def _integer_or_null(value: int) -> str:
    """``cwgame_print_integer_or_null``: a negative number is a null, shown as nothing"""
    return str(value) if value >= 0 else ""


def _quoted_or_padded(a: bool, text: str, width: int) -> str:
    """``(ascii) ? "\\"%s\\"" : "%-<width>s"``"""
    return f'"{text}"' if a else f"{text:<{width}}"


def _info_text(key: str, width: int) -> Field:
    """``(tmp = cw_game_info_lookup(game, key)) ? tmp : ""`` through the quoted/padded format"""

    def f(a: bool, gi: GameIter, box: Boxscore, v: Roster | None, h: Roster | None) -> str:
        return _quoted_or_padded(a, _info(gi, key) or "", width)

    return f


def _int_field(a: bool, value: int, width: int) -> str:
    """``(ascii) ? "%d" : "%<width>d"``"""
    return str(value) if a else f"{value:{width}d}"


def _game_find_name(game: Game, player_id: str | None) -> str | None:
    """``cwgame_game_find_name``: a player's name from an appearance record"""
    for app in game.starters:
        if app.player_id == _deref(player_id):
            return app.name
    for event in game.events:
        for app in event.subs:
            if app.player_id == _deref(player_id):
                return app.name
    return None


def _find_player_name(
    game: Game, player_id: str, visitors: Roster | None, home: Roster | None
) -> str:
    """``cwgame_find_player_name``"""
    bio = visitors.player_find(player_id) if visitors is not None else None
    if bio is None and home is not None:
        bio = home.player_find(player_id)
    if bio is not None:
        return f'"{bio.first_name} {bio.last_name}"'
    return f'"{_s(_game_find_name(game, player_id))}"'


def _day_of_week_index(month: int, day: int, year: int) -> int:
    """``get_day_of_week`` (Tomohiko Sakamoto); 0 is Sunday"""
    t = [0, 3, 2, 5, 0, 3, 5, 1, 4, 6, 2, 4]
    if not 1 <= month <= 12:
        raise ValueError(f"month {month} out of range (undefined behaviour in C)")
    year -= month < 3
    total = year + _cdiv(year, 4) - _cdiv(year, 100) + _cdiv(year, 400) + t[month - 1] + day
    return _cmod(total, 7)


def _lookup(text: str | None, table: tuple[tuple[int, str], ...]) -> int:
    """``cwgame_lookup``"""
    if text is None:
        return 0
    for code, name in table:
        if name == text:
            return code
    return 0


def _lookup_field(key: str, table: tuple[tuple[int, str], ...]) -> Field:
    def f(a: bool, gi: GameIter, box: Boxscore, v: Roster | None, h: Roster | None) -> str:
        return str(_lookup(_info(gi, key), table))

    return f


# Fields 0-45, 84 --------------------------------------------------------------------------


def _game_id(a: bool, gi: GameIter, box: Boxscore, v: Roster | None, h: Roster | None) -> str:
    return _quoted_or_padded(a, gi.game.game_id, 12)


def _date(a: bool, gi: GameIter, box: Boxscore, v: Roster | None, h: Roster | None) -> str:
    date = _deref(_info(gi, "date"))
    if len(date) < 10:
        raise ValueError(f"date {date!r} is shorter than the C reads (undefined behaviour)")
    text = date[0:4] + date[5:7] + date[8:10]
    return f'"{text}"' if a else text


def _number(a: bool, gi: GameIter, box: Boxscore, v: Roster | None, h: Roster | None) -> str:
    tmp = _info(gi, "number")
    return _int_field(a, cw_atoi(tmp) if tmp is not None else 0, 5)


DAY_NAMES = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]


def _day_of_week(a: bool, gi: GameIter, box: Boxscore, v: Roster | None, h: Roster | None) -> str:
    date = _info(gi, "date")
    if date is None:
        return ""
    year = scan_int(date, 0)
    month = day = None
    if year is not None and date[year[1] : year[1] + 1] == "/":
        month = scan_int(date, year[1] + 1)
        if month is not None and date[month[1] : month[1] + 1] == "/":
            day = scan_int(date, month[1] + 1)
    if year is None or month is None or day is None:
        raise ValueError(f"unparsable date {date!r} (uninitialised values in Chadwick)")
    y = year[0]
    if 0 < y <= 99:
        y += 1900  # assume that two-digit years are in the 20th century
    name = DAY_NAMES[_day_of_week_index(month[0], day[0], y)]
    return f'"{name}"' if a else name


def _start_time(a: bool, gi: GameIter, box: Boxscore, v: Roster | None, h: Roster | None) -> str:
    text = _info(gi, "starttime")
    if text is None:
        return "0" if a else "   0"
    hour = scan_int(text, 0)
    minute = None
    if hour is not None and text[hour[1] : hour[1] + 1] == ":":
        minute = scan_int(text, hour[1] + 1)
    if hour is None or minute is None:
        raise ValueError(f"unparsable start time {text!r} (uninitialised values in Chadwick)")
    return _int_field(a, hour[0] * 100 + minute[0], 4)


def _use_dh(a: bool, gi: GameIter, box: Boxscore, v: Roster | None, h: Roster | None) -> str:
    tmp = _info(gi, "usedh")
    c = "T" if tmp is not None and tmp == "true" else "F"
    return f'"{c}"' if a else c


def _day_night(a: bool, gi: GameIter, box: Boxscore, v: Roster | None, h: Roster | None) -> str:
    tmp = _info(gi, "daynight")
    c = "N" if tmp is not None and tmp == "night" else "D"
    return f'"{c}"' if a else c


def _starter_pitcher(team: int) -> Field:
    def f(a: bool, gi: GameIter, box: Boxscore, v: Roster | None, h: Roster | None) -> str:
        app = gi.game.starter_by_position(team, 1)
        return _quoted_or_padded(a, app.player_id if app is not None else "", 8)

    return f


def _attendance(a: bool, gi: GameIter, box: Boxscore, v: Roster | None, h: Roster | None) -> str:
    tmp = _info(gi, "attendance")
    value = (
        cw_atoi(tmp, "Warning: invalid value '%s' for info,attendance\n")
        if tmp is not None and tmp != ""
        else 0
    )
    return _int_field(a, value, 5)


def _temperature(a: bool, gi: GameIter, box: Boxscore, v: Roster | None, h: Roster | None) -> str:
    value = _info(gi, "temp")
    if value is None or value == "" or value == "unknown":
        return _int_field(a, 0, 3)
    return _int_field(a, cw_atoi(value, "Warning: invalid value '%s' for info,temp\n"), 3)


def _wind_speed(a: bool, gi: GameIter, box: Boxscore, v: Roster | None, h: Roster | None) -> str:
    value = _info(gi, "windspeed")
    if value is None or value == "" or value == "unknown":
        return "0"
    return str(cw_atoi(value, "Warning: invalid value '%s' for info,windspeed\n"))


def _time_of_game(a: bool, gi: GameIter, box: Boxscore, v: Roster | None, h: Roster | None) -> str:
    tmp = _info(gi, "timeofgame")
    value = (
        cw_atoi(tmp, "Warning: invalid value '%s' for info,timeofgame\n")
        if tmp is not None and tmp != ""
        else 0
    )
    return _int_field(a, value, 5)


def _innings(a: bool, gi: GameIter, box: Boxscore, v: Roster | None, h: Roster | None) -> str:
    if gi.game.events:
        return _int_field(a, gi.state.inning, 2)
    i = 1
    while i < 50:
        if box.linescore[i][0] < 0 and box.linescore[i][1] < 0:
            break
        i += 1
    return _int_field(a, i - 1, 2)


def _box_pair(attr: str, team: int) -> Field:
    """``box->score[t]``, ``box->hits[t]``, ``box->errors[t]``"""

    def f(a: bool, gi: GameIter, box: Boxscore, v: Roster | None, h: Roster | None) -> str:
        return _int_field(a, getattr(box, attr)[team], 2)

    return f


def _lob(team: int) -> Field:
    def f(a: bool, gi: GameIter, box: Boxscore, v: Roster | None, h: Roster | None) -> str:
        if gi.game.events:
            return _int_field(a, gi.state.left_on_base(team), 2)
        return _int_field(a, box.lob[team], 2)

    return f


def _game_type(a: bool, gi: GameIter, box: Boxscore, v: Roster | None, h: Roster | None) -> str:
    tmp = _info(gi, "gametype")
    return _quoted_or_padded(a, tmp if tmp is not None and tmp != "" else "regular", 12)


def starting_player(a: bool, game: Game, team: int, slot: int) -> str:
    """``cwgame_starting_player``"""
    starter = game.starter_find(team, slot)
    if starter is not None:
        return _quoted_or_padded(a, starter.player_id, 8)
    return "(null)"


def starting_position(game: Game, team: int, slot: int) -> str:
    """``cwgame_starting_position``"""
    starter = game.starter_find(team, slot)
    return str(starter.pos) if starter is not None else "0"


def final_pitcher(a: bool, box: Boxscore, team: int) -> str:
    """``cwgame_final_pitcher``"""
    pitcher = box.pitchers[team]
    player_id = pitcher.prev.player_id if pitcher is not None and pitcher.prev is not None else ""
    return _quoted_or_padded(a, player_id, 8)


# Extended fields ----------------------------------------------------------------------------


def _league(team: int) -> Field:
    def f(a: bool, gi: GameIter, box: Boxscore, v: Roster | None, h: Roster | None) -> str:
        roster = v if team == 0 else h
        return f'"{roster.league if roster is not None else ""}"'

    return f


def _empty(a: bool, gi: GameIter, box: Boxscore, v: Roster | None, h: Roster | None) -> str:
    return ""


def _length_outs(a: bool, gi: GameIter, box: Boxscore, v: Roster | None, h: Roster | None) -> str:
    outs = 0
    for t in range(2):
        pitcher = get_starting_pitcher(box, t)
        while pitcher is not None:
            outs += pitcher.pitching.outs
            pitcher = pitcher.next
    return str(outs)


def _line(team: int) -> Field:
    """``cwgame_visitors_line`` and ``cwgame_home_line``"""

    def f(a: bool, gi: GameIter, box: Boxscore, v: Roster | None, h: Roster | None) -> str:
        out = ""
        i = 1
        while i < 50:
            if box.linescore[i][0] < 0 and box.linescore[i][1] < 0:
                break
            score = box.linescore[i][team]
            if score >= 10:
                out += f"({score})"
            elif score >= 0:
                out += str(score)
            else:
                out += "x"
            i += 1
        return out

    return f


def _tabulated_batter(team: int, attr: str) -> Field:
    """``DECLARE_TABULATED_BATTER_FUNC``: a negative (null) stat stops that slot's walk and sets
    the total to -1, but the next slot goes on adding to it"""

    def f(a: bool, gi: GameIter, box: Boxscore, v: Roster | None, h: Roster | None) -> str:
        tot = 0
        for slot in range(1, 10):
            player: BoxPlayer | None = get_starter(box, team, slot)
            while player is not None:
                value = getattr(player.batting, attr)
                if value < 0:
                    tot = -1
                    break
                tot += value
                player = player.next
        return _integer_or_null(tot)

    return f


def _tabulated_pitcher(team: int, attr: str) -> Field:
    """``DECLARE_TABULATED_PITCHER_FUNC``"""

    def f(a: bool, gi: GameIter, box: Boxscore, v: Roster | None, h: Roster | None) -> str:
        tot = 0
        pitcher: BoxPitcher | None = get_starting_pitcher(box, team)
        while pitcher is not None:
            tot += getattr(pitcher.pitching, attr)
            pitcher = pitcher.next
        return _integer_or_null(tot)

    return f


def _tabulated_fielder(team: int, attr: str, frompos: int, topos: int) -> Field:
    """``DECLARE_TABULATED_FIELDER_FUNC``"""

    def f(a: bool, gi: GameIter, box: Boxscore, v: Roster | None, h: Roster | None) -> str:
        tot = 0
        for slot in range(10):
            player = get_starter(box, team, slot)
            while player is not None:
                for pos in range(frompos, topos + 1):
                    fielding = player.fielding[pos]
                    if fielding is not None:
                        value = getattr(fielding, attr)
                        if value < 0:
                            return "-1"
                        tot += value
                player = player.next
        return _integer_or_null(tot)

    return f


def _pitcher_count(team: int) -> Field:
    def f(a: bool, gi: GameIter, box: Boxscore, v: Roster | None, h: Roster | None) -> str:
        pitcher = get_starting_pitcher(box, team)
        i = 0
        while pitcher is not None:
            pitcher = pitcher.next
            i += 1
        return str(i)

    return f


def _box_count(attr: str, team: int) -> Field:
    """``box->er[t]``, ``box->dp[t]``, ``box->tp[t]``"""

    def f(a: bool, gi: GameIter, box: Boxscore, v: Roster | None, h: Roster | None) -> str:
        return str(getattr(box, attr)[team])

    return f


def _named(key: str) -> Field:
    """``cwgame_winning_pitcher_name`` and its losing/save twins"""

    def f(a: bool, gi: GameIter, box: Boxscore, v: Roster | None, h: Roster | None) -> str:
        tmp = _info(gi, key)
        if tmp is not None and tmp != "":
            return _find_player_name(gi.game, tmp, v, h)
        return '"(none)"'

    return f


def _goahead_rbi_id(
    a: bool, gi: GameIter, box: Boxscore, v: Roster | None, h: Roster | None
) -> str:
    return _quoted_or_padded(a, gi.state.go_ahead_rbi or "", 8)


def _goahead_rbi_name(
    a: bool, gi: GameIter, box: Boxscore, v: Roster | None, h: Roster | None
) -> str:
    tmp = gi.state.go_ahead_rbi
    if tmp is not None and tmp != "":
        return _find_player_name(gi.game, tmp, v, h)
    return '"(none)"'


def _lineup_name(team: int, slot: int) -> Field:
    """``cwgame_find_lineup_name``"""

    def f(a: bool, gi: GameIter, box: Boxscore, v: Roster | None, h: Roster | None) -> str:
        starter = gi.game.starter_find(team, slot)
        if starter is not None:
            return _find_player_name(gi.game, starter.player_id, v, h)
        return "(null)"

    return f


def _additional_info(
    a: bool, gi: GameIter, box: Boxscore, v: Roster | None, h: Roster | None
) -> str:
    htbf = _info(gi, "htbf")
    return "HTBF" if htbf is not None and htbf == "true" else ""


def _scheduled_innings(
    a: bool, gi: GameIter, box: Boxscore, v: Roster | None, h: Roster | None
) -> str:
    tmp = _info(gi, "innings")
    return tmp if tmp is not None else "9"


def _tiebreaker(a: bool, gi: GameIter, box: Boxscore, v: Roster | None, h: Roster | None) -> str:
    return f'"{_info(gi, "tiebreaker") or ""}"'


_HOWSCORED = ((0, "unknown"), (1, "park"), (2, "tv"), (3, "radio"))
_PITCHES = ((0, "unknown"), (1, "pitches"), (2, "count"), (0, "none"))
_WINDDIR = (
    (0, "unknown"), (1, "tolf"), (2, "tocf"), (3, "torf"), (4, "ltor"),
    (5, "fromlf"), (6, "fromcf"), (7, "fromrf"), (8, "rtol"),
)  # fmt: skip
_FIELDCOND = ((0, "unknown"), (1, "soaked"), (2, "wet"), (3, "damp"), (4, "dry"))
_PRECIP = ((0, "unknown"), (1, "none"), (2, "drizzle"), (3, "showers"), (4, "rain"), (5, "snow"))
_SKY = ((0, "unknown"), (1, "sunny"), (2, "cloudy"), (3, "overcast"), (4, "night"), (5, "dome"))

FIELDS: tuple[tuple[Field | None, str, str], ...] = (
    (_game_id, "GAME_ID", "game id"),
    (_date, "GAME_DT", "date"),
    (_number, "GAME_CT", "game number (0 = no double header)"),
    (_day_of_week, "GAME_DY", "day of week"),
    (_start_time, "START_GAME_TM", "start time"),
    (_use_dh, "DH_FL", "DH used flag"),
    (_day_night, "DAYNIGHT_PARK_CD", "day/night flag"),
    (_info_text("visteam", 3), "AWAY_TEAM_ID", "visiting team"),
    (_info_text("hometeam", 3), "HOME_TEAM_ID", "home team"),
    (_info_text("site", 5), "PARK_ID", "game site"),
    (_starter_pitcher(0), "AWAY_START_PIT_ID", "vis. starting pitcher"),
    (_starter_pitcher(1), "HOME_START_PIT_ID", "home starting pitcher"),
    (_info_text("umphome", 30), "BASE4_UMP_ID", "home plate umpire"),
    (_info_text("ump1b", 30), "BASE1_UMP_ID", "first base umpire"),
    (_info_text("ump2b", 30), "BASE2_UMP_ID", "second base umpire"),
    (_info_text("ump3b", 30), "BASE3_UMP_ID", "third base umpire"),
    (_info_text("umplf", 30), "LF_UMP_ID", "left field umpire"),
    (_info_text("umprf", 30), "RF_UMP_ID", "right field umpire"),
    (_attendance, "ATTEND_PARK_CT", "attendance"),
    (_info_text("scorer", 30), "SCORER_RECORD_ID", "PS scorer"),
    (_info_text("translator", 30), "TRANSLATOR_RECORD_ID", "translator"),
    (_info_text("inputter", 30), "INPUTTER_RECORD_ID", "inputter"),
    (_info_text("inputtime", 30), "INPUT_RECORD_TS", "input time"),
    (_info_text("edittime", 30), "EDIT_RECORD_TS", "edit time"),
    (_lookup_field("howscored", _HOWSCORED), "METHOD_RECORD_CD", "how scored"),
    (_lookup_field("pitches", _PITCHES), "PITCHES_RECORD_CD", "pitches entered?"),
    (_temperature, "TEMP_PARK_CT", "temperature"),
    (_lookup_field("winddir", _WINDDIR), "WIND_DIRECTION_PARK_CD", "wind direction"),
    (_wind_speed, "WIND_SPEED_PARK_CT", "wind speed"),
    (_lookup_field("fieldcond", _FIELDCOND), "FIELD_PARK_CD", "field condition"),
    (_lookup_field("precip", _PRECIP), "PRECIP_PARK_CD", "precipitation"),
    (_lookup_field("sky", _SKY), "SKY_PARK_CD", "sky"),
    (_time_of_game, "MINUTES_GAME_CT", "time of game"),
    (_innings, "INN_CT", "number of innings"),
    (_box_pair("score", 0), "AWAY_SCORE_CT", "visitor final score"),
    (_box_pair("score", 1), "HOME_SCORE_CT", "home final score"),
    (_box_pair("hits", 0), "AWAY_HITS_CT", "visitor hits"),
    (_box_pair("hits", 1), "HOME_HITS_CT", "home hits"),
    (_box_pair("errors", 0), "AWAY_ERR_CT", "visitor errors"),
    (_box_pair("errors", 1), "HOME_ERR_CT", "home errors"),
    (_lob(0), "AWAY_LOB_CT", "visitor left on base"),
    (_lob(1), "HOME_LOB_CT", "home left on base"),
    (_info_text("wp", 8), "WIN_PIT_ID", "winning pitcher"),
    (_info_text("lp", 8), "LOSE_PIT_ID", "losing pitcher"),
    (_info_text("save", 12), "SAVE_PIT_ID", "save for"),
    (_info_text("gwrbi", 8), "GWRBI_BAT_ID", "GW RBI"),
    (None, "AWAY_LINEUP1_BAT_ID", "visitor batter 1"),
    (None, "AWAY_LINEUP1_FLD_CD", "visitor position 1"),
    (None, "AWAY_LINEUP2_BAT_ID", "visitor batter 2"),
    (None, "AWAY_LINEUP2_FLD_CD", "visitor position 2"),
    (None, "AWAY_LINEUP3_BAT_ID", "visitor batter 3"),
    (None, "AWAY_LINEUP3_FLD_CD", "visitor position 3"),
    (None, "AWAY_LINEUP4_BAT_ID", "visitor batter 4"),
    (None, "AWAY_LINEUP4_FLD_CD", "visitor position 4"),
    (None, "AWAY_LINEUP5_BAT_ID", "visitor batter 5"),
    (None, "AWAY_LINEUP5_FLD_CD", "visitor position 5"),
    (None, "AWAY_LINEUP6_BAT_ID", "visitor batter 6"),
    (None, "AWAY_LINEUP6_FLD_CD", "visitor position 6"),
    (None, "AWAY_LINEUP7_BAT_ID", "visitor batter 7"),
    (None, "AWAY_LINEUP7_FLD_CD", "visitor position 7"),
    (None, "AWAY_LINEUP8_BAT_ID", "visitor batter 8"),
    (None, "AWAY_LINEUP8_FLD_CD", "visitor position 8"),
    (None, "AWAY_LINEUP9_BAT_ID", "visitor batter 9"),
    (None, "AWAY_LINEUP9_FLD_CD", "visitor position 9"),
    (None, "HOME_LINEUP1_BAT_ID", "home batter 1"),
    (None, "HOME_LINEUP1_FLD_CD", "home position 1"),
    (None, "HOME_LINEUP2_BAT_ID", "home batter 2"),
    (None, "HOME_LINEUP2_FLD_CD", "home position 2"),
    (None, "HOME_LINEUP3_BAT_ID", "home batter 3"),
    (None, "HOME_LINEUP3_FLD_CD", "home position 3"),
    (None, "HOME_LINEUP4_BAT_ID", "home batter 4"),
    (None, "HOME_LINEUP4_FLD_CD", "home position 4"),
    (None, "HOME_LINEUP5_BAT_ID", "home batter 5"),
    (None, "HOME_LINEUP5_FLD_CD", "home position 5"),
    (None, "HOME_LINEUP6_BAT_ID", "home batter 6"),
    (None, "HOME_LINEUP6_FLD_CD", "home position 6"),
    (None, "HOME_LINEUP7_BAT_ID", "home batter 7"),
    (None, "HOME_LINEUP7_FLD_CD", "home position 7"),
    (None, "HOME_LINEUP8_BAT_ID", "home batter 8"),
    (None, "HOME_LINEUP8_FLD_CD", "home position 8"),
    (None, "HOME_LINEUP9_BAT_ID", "home batter 9"),
    (None, "HOME_LINEUP9_FLD_CD", "home position 9"),
    (None, "AWAY_FINISH_PIT_ID", "visiting finisher (NULL if complete game)"),
    (None, "HOME_FINISH_PIT_ID", "home finisher (NULL if complete game)"),
    (_game_type, "GAME_TYPE_TX", "game type"),
)

EXT_FIELDS: tuple[tuple[Field | None, str, str], ...] = (
    (_league(0), "AWAY_TEAM_LEAGUE_ID", "visiting team league"),
    (_league(1), "HOME_TEAM_LEAGUE_ID", "home team league"),
    (_empty, "AWAY_TEAM_GAME_CT", "visiting team game number"),
    (_empty, "HOME_TEAM_GAME_CT", "home team game number"),
    (_length_outs, "OUTS_CT", "length of game in outs"),
    (_empty, "COMPLETION_TX", "information on completion of game"),
    (_empty, "FORFEIT_TX", "information on forfeit of game"),
    (_empty, "PROTEST_TX", "information on protest of game"),
    (_line(0), "AWAY_LINE_TX", "visiting team linescore"),
    (_line(1), "HOME_LINE_TX", "home team linescore"),
    (_tabulated_batter(0, "ab"), "AWAY_AB_CT", "visiting team AB"),
    (_tabulated_batter(0, "b2"), "AWAY_2B_CT", "visiting team 2B"),
    (_tabulated_batter(0, "b3"), "AWAY_3B_CT", "visiting team 3B"),
    (_tabulated_batter(0, "hr"), "AWAY_HR_CT", "visiting team HR"),
    (_tabulated_batter(0, "bi"), "AWAY_BI_CT", "visiting team RBI"),
    (_tabulated_batter(0, "sh"), "AWAY_SH_CT", "visiting team SH"),
    (_tabulated_batter(0, "sf"), "AWAY_SF_CT", "visiting team SF"),
    (_tabulated_batter(0, "hp"), "AWAY_HP_CT", "visiting team HP"),
    (_tabulated_batter(0, "bb"), "AWAY_BB_CT", "visiting team BB"),
    (_tabulated_batter(0, "ibb"), "AWAY_IBB_CT", "visiting team IBB"),
    (_tabulated_batter(0, "so"), "AWAY_SO_CT", "visiting team SO"),
    (_tabulated_batter(0, "sb"), "AWAY_SB_CT", "visiting team SB"),
    (_tabulated_batter(0, "cs"), "AWAY_CS_CT", "visiting team CS"),
    (_tabulated_batter(0, "gdp"), "AWAY_GDP_CT", "visiting team GDP"),
    (_tabulated_batter(0, "xi"), "AWAY_XI_CT", "visiting team reach on interference"),
    (_pitcher_count(0), "AWAY_PITCHER_CT", "number of pitchers used by visiting team"),
    (_tabulated_pitcher(0, "er"), "AWAY_ER_CT", "visiting team individual ER allowed"),
    (_box_count("er", 0), "AWAY_TER_CT", "visiting team team ER allowed"),
    (_tabulated_pitcher(0, "wp"), "AWAY_WP_CT", "visiting team WP"),
    (_tabulated_pitcher(0, "bk"), "AWAY_BK_CT", "visiting team BK"),
    (_tabulated_fielder(0, "po", 1, 9), "AWAY_PO_CT", "visiting team PO"),
    (_tabulated_fielder(0, "a", 1, 9), "AWAY_A_CT", "visiting team A"),
    (_tabulated_fielder(0, "pb", 2, 2), "AWAY_PB_CT", "visiting team PB"),
    (_box_count("dp", 0), "AWAY_DP_CT", "visiting team DP"),
    (_box_count("tp", 0), "AWAY_TP_CT", "visiting team TP"),
    (_tabulated_batter(1, "ab"), "HOME_AB_CT", "home team AB"),
    (_tabulated_batter(1, "b2"), "HOME_2B_CT", "home team 2B"),
    (_tabulated_batter(1, "b3"), "HOME_3B_CT", "home team 3B"),
    (_tabulated_batter(1, "hr"), "HOME_HR_CT", "home team HR"),
    (_tabulated_batter(1, "bi"), "HOME_BI_CT", "home team RBI"),
    (_tabulated_batter(1, "sh"), "HOME_SH_CT", "home team SH"),
    (_tabulated_batter(1, "sf"), "HOME_SF_CT", "home team SF"),
    (_tabulated_batter(1, "hp"), "HOME_HP_CT", "home team HP"),
    (_tabulated_batter(1, "bb"), "HOME_BB_CT", "home team BB"),
    (_tabulated_batter(1, "ibb"), "HOME_IBB_CT", "home team IBB"),
    (_tabulated_batter(1, "so"), "HOME_SO_CT", "home team SO"),
    (_tabulated_batter(1, "sb"), "HOME_SB_CT", "home team SB"),
    (_tabulated_batter(1, "cs"), "HOME_CS_CT", "home team CS"),
    (_tabulated_batter(1, "gdp"), "HOME_GDP_CT", "home team GDP"),
    (_tabulated_batter(1, "xi"), "HOME_XI_CT", "home team reach on interference"),
    (_pitcher_count(1), "HOME_PITCHER_CT", "number of pitchers used by home team"),
    (_tabulated_pitcher(1, "er"), "HOME_ER_CT", "home team individual ER allowed"),
    (_box_count("er", 1), "HOME_TER_CT", "home team team ER allowed"),
    (_tabulated_pitcher(1, "wp"), "HOME_WP_CT", "home team WP"),
    (_tabulated_pitcher(1, "bk"), "HOME_BK_CT", "home team BK"),
    (_tabulated_fielder(1, "po", 1, 9), "HOME_PO_CT", "home team PO"),
    (_tabulated_fielder(1, "a", 1, 9), "HOME_A_CT", "home team A"),
    (_tabulated_fielder(1, "pb", 2, 2), "HOME_PB_CT", "home team PB"),
    (_box_count("dp", 1), "HOME_DP_CT", "home team DP"),
    (_box_count("tp", 1), "HOME_TP_CT", "home team TP"),
    (_empty, "UMP_HOME_NAME_TX", "home plate umpire name"),
    (_empty, "UMP_1B_NAME_TX", "first base umpire name"),
    (_empty, "UMP_2B_NAME_TX", "second base umpire name"),
    (_empty, "UMP_3B_NAME_TX", "third base umpire name"),
    (_empty, "UMP_LF_NAME_TX", "left field umpire name"),
    (_empty, "UMP_RF_NAME_TX", "right field umpire name"),
    (_empty, "AWAY_MANAGER_ID", "visitors manager ID"),
    (_empty, "AWAY_MANAGER_NAME_TX", "visitors manager name"),
    (_empty, "HOME_MANAGER_ID", "home manager ID"),
    (_empty, "HOME_MANAGER_NAME_TX", "home manager name"),
    (_named("wp"), "WIN_PIT_NAME_TX", "winning pitcher name"),
    (_named("lp"), "LOSE_PIT_NAME_TX", "losing pitcher name"),
    (_named("save"), "SAVE_PIT_NAME_TX", "save pitcher name"),
    (_goahead_rbi_id, "GOAHEAD_RBI_ID", "batter with goahead RBI ID"),
    (_goahead_rbi_name, "GOAHEAD_RBI_NAME_TX", "batter with goahead RBI"),
    (_lineup_name(0, 1), "AWAY_LINEUP1_BAT_NAME_TX", "visitor batter 1 name"),
    (_lineup_name(0, 2), "AWAY_LINEUP2_BAT_NAME_TX", "visitor batter 2 name"),
    (_lineup_name(0, 3), "AWAY_LINEUP3_BAT_NAME_TX", "visitor batter 3 name"),
    (_lineup_name(0, 4), "AWAY_LINEUP4_BAT_NAME_TX", "visitor batter 4 name"),
    (_lineup_name(0, 5), "AWAY_LINEUP5_BAT_NAME_TX", "visitor batter 5 name"),
    (_lineup_name(0, 6), "AWAY_LINEUP6_BAT_NAME_TX", "visitor batter 6 name"),
    (_lineup_name(0, 7), "AWAY_LINEUP7_BAT_NAME_TX", "visitor batter 7 name"),
    (_lineup_name(0, 8), "AWAY_LINEUP8_BAT_NAME_TX", "visitor batter 8 name"),
    (_lineup_name(0, 9), "AWAY_LINEUP9_BAT_NAME_TX", "visitor batter 9 name"),
    (_lineup_name(1, 1), "HOME_LINEUP1_BAT_NAME_TX", "home batter 1 name"),
    (_lineup_name(1, 2), "HOME_LINEUP2_BAT_NAME_TX", "home batter 2 name"),
    (_lineup_name(1, 3), "HOME_LINEUP3_BAT_NAME_TX", "home batter 3 name"),
    (_lineup_name(1, 4), "HOME_LINEUP4_BAT_NAME_TX", "home batter 4 name"),
    (_lineup_name(1, 5), "HOME_LINEUP5_BAT_NAME_TX", "home batter 5 name"),
    (_lineup_name(1, 6), "HOME_LINEUP6_BAT_NAME_TX", "home batter 6 name"),
    (_lineup_name(1, 7), "HOME_LINEUP7_BAT_NAME_TX", "home batter 7 name"),
    (_lineup_name(1, 8), "HOME_LINEUP8_BAT_NAME_TX", "home batter 8 name"),
    (_lineup_name(1, 9), "HOME_LINEUP9_BAT_NAME_TX", "home batter 9 name"),
    (_additional_info, "ADD_INFO_TX", "additional information"),
    (_empty, "ACQ_INFO_TX", "acquisition information"),
    (_scheduled_innings, "SCHED_INN_CT", "scheduled length of game in innings "),
    (_tiebreaker, "TIEBREAK_CD", "tiebreaker rule type in use"),
)

MAX_FIELD = len(FIELDS) - 1
MAX_EXT_FIELD = len(EXT_FIELDS) - 1


def game_line(
    game: Game,
    visitors: Roster | None,
    home: Roster | None,
    ascii_: bool,
    fields: Collection[int],
    ext_fields: Collection[int],
) -> str:
    """``cwgame_process_game``: the line describing one game"""
    box = box_create(game)
    gi = GameIter(game)
    while gi.event is not None:
        gi.next()

    parts: list[str] = []
    for i in range(46):
        if i in fields:
            parts.append(_deref(FIELDS[i][0])(ascii_, gi, box, visitors, home))
    for t in range(2):
        for i in range(1, 10):
            for j in range(2):
                if 46 + t * 18 + 2 * (i - 1) + j in fields:
                    parts.append(
                        starting_player(ascii_, game, t, i)
                        if j == 0
                        else starting_position(game, t, i)
                    )
    for t, i in enumerate((82, 83)):
        if i in fields:
            parts.append(final_pitcher(ascii_, box, t))
    for i in range(84, MAX_FIELD + 1):
        if i in fields:
            parts.append(_deref(FIELDS[i][0])(ascii_, gi, box, visitors, home))
    for i in range(MAX_EXT_FIELD + 1):
        if i in ext_fields:
            parts.append(_deref(EXT_FIELDS[i][0])(ascii_, gi, box, visitors, home))
    return ("," if ascii_ else "").join(parts)


def header_line(fields: Collection[int], ext_fields: Collection[int]) -> str:
    """``cwgame_initialize`` with ``-n``: the field names, quoted and comma separated"""
    names = [f'"{FIELDS[i][1]}"' for i in range(MAX_FIELD + 1) if i in fields]
    names += [f'"{EXT_FIELDS[i][1]}"' for i in range(MAX_EXT_FIELD + 1) if i in ext_fields]
    return ",".join(names)


DEFAULT_FIELDS = tuple(range(84))


def game_lines(
    data: bytes,
    league: League | None = None,
    game_id: str = "",
    first_date: str = "0101",
    last_date: str = "1231",
    ascii_: bool = True,
    fields: Collection[int] = DEFAULT_FIELDS,
    ext_fields: Collection[int] = (),
) -> Iterator[str]:
    """Lines for the selected games of an event file, as ``cwgame`` prints them."""
    for game, visitors, home in iterate_games(data, league, game_id, first_date, last_date):
        yield game_line(game, visitors, home, ascii_, fields, ext_fields)
