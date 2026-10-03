"""Port of Chadwick's ``cwdaily`` (``src/cwtools/cwdaily.c``), the player game-by-game generator.

Chadwick is Copyright (c) 2002-2023 Dr T L Turocy and the Chadwick Baseball
Bureau, licensed GPL-2.0-or-later; this module is a derivative of it and keeps
that notice. One function per ``cwdaily`` field, in the same order, each returning
the text the C ``sprintf`` writes. The C declares each statistic with a macro
(``DECLARE_BATTING_CATEGORY`` and so on); the port builds the same functions with
the factories below. ``ascii`` is the C global of the same name: true for the
comma-delimited format (``-a``, the default), false for the fixed-width Fortran
format (``-ft``).

Deviations: the C reads ``date[0]``..``date[9]`` of the ``date`` info record without
checking its length (undefined behaviour on a short date) and builds each line in a
4096-byte buffer; the port raises ``ValueError`` on a missing or short date and has no
line limit.
"""

from collections.abc import Callable, Iterator

from retrosheetpy.cw.box import BoxPlayer, Boxscore, box_create, get_starter
from retrosheetpy.cw.file import cw_atoi
from retrosheetpy.cw.game import Game
from retrosheetpy.cw.gameiter import GameIter
from retrosheetpy.cw.roster import League
from retrosheetpy.cw.tools import iterate_games

Field = Callable[[bool, GameIter, Boxscore, int, int, int, BoxPlayer], str]


def _int_or_null(value: int) -> str:
    """``cwdaily_print_integer_or_null``: a negative number is a null, shown as nothing"""
    return str(value) if value >= 0 else ""


def _info(gi: GameIter, key: str) -> str:
    return gi.game.info_lookup(key) or ""


def _game_id(
    a: bool, gi: GameIter, box: Boxscore, team: int, slot: int, seq: int, p: BoxPlayer
) -> str:
    return f'"{gi.game.game_id}"' if a else f"{gi.game.game_id:<12}"


def _date(
    a: bool, gi: GameIter, box: Boxscore, team: int, slot: int, seq: int, p: BoxPlayer
) -> str:
    date = gi.game.info_lookup("date")
    if date is None or len(date) < 10:
        raise ValueError(f"game {gi.game.game_id} has no usable date (undefined in Chadwick)")
    text = date[0:4] + date[5:7] + date[8:10]
    return f'"{text}"' if a else text


def _number(
    a: bool, gi: GameIter, box: Boxscore, team: int, slot: int, seq: int, p: BoxPlayer
) -> str:
    tmp = gi.game.info_lookup("number")
    number = cw_atoi(tmp) if tmp is not None else 0
    return str(number) if a else f"{number:5d}"


def _app_date(
    a: bool, gi: GameIter, box: Boxscore, team: int, slot: int, seq: int, p: BoxPlayer
) -> str:
    # The appearance date differs from the game date for games suspended and then resumed
    return f'"{p.date}"'


def _team_name(a: bool, gi: GameIter, key: str) -> str:
    name = _info(gi, key)
    return f'"{name}"' if a else f"{name:<3}"


def _team_id(
    a: bool, gi: GameIter, box: Boxscore, team: int, slot: int, seq: int, p: BoxPlayer
) -> str:
    return _team_name(a, gi, "visteam" if team == 0 else "hometeam")


def _player_id(
    a: bool, gi: GameIter, box: Boxscore, team: int, slot: int, seq: int, p: BoxPlayer
) -> str:
    return f'"{p.player_id}"'


def _slot(
    a: bool, gi: GameIter, box: Boxscore, team: int, slot: int, seq: int, p: BoxPlayer
) -> str:
    return str(slot if slot < 10 else 0)


def _seq(a: bool, gi: GameIter, box: Boxscore, team: int, slot: int, seq: int, p: BoxPlayer) -> str:
    return str(seq)


def _home_fl(
    a: bool, gi: GameIter, box: Boxscore, team: int, slot: int, seq: int, p: BoxPlayer
) -> str:
    return str(int(team == 1))


def _opponent_id(
    a: bool, gi: GameIter, box: Boxscore, team: int, slot: int, seq: int, p: BoxPlayer
) -> str:
    return _team_name(a, gi, "visteam" if team == 1 else "hometeam")


def _site(
    a: bool, gi: GameIter, box: Boxscore, team: int, slot: int, seq: int, p: BoxPlayer
) -> str:
    site = _info(gi, "site")
    return f'"{site}"' if a else f"{site:<5}"


def _batting(cat: str) -> Field:
    """``DECLARE_BATTING_CATEGORY``"""

    def f(
        a: bool, gi: GameIter, box: Boxscore, team: int, slot: int, seq: int, p: BoxPlayer
    ) -> str:
        return _int_or_null(getattr(p.batting, cat))

    return f


def _batting_tb(
    a: bool, gi: GameIter, box: Boxscore, team: int, slot: int, seq: int, p: BoxPlayer
) -> str:
    b = p.batting
    return _int_or_null(b.h + b.b2 + 2 * b.b3 + 3 * b.hr)


def _b_g_dh(
    a: bool, gi: GameIter, box: Boxscore, team: int, slot: int, seq: int, p: BoxPlayer
) -> str:
    return "1" if 10 in p.positions[: p.num_positions] else "0"


def _b_g_ph(
    a: bool, gi: GameIter, box: Boxscore, team: int, slot: int, seq: int, p: BoxPlayer
) -> str:
    return "1" if p.ph_inn > 0 else "0"


def _b_g_pr(
    a: bool, gi: GameIter, box: Boxscore, team: int, slot: int, seq: int, p: BoxPlayer
) -> str:
    return "1" if p.pr_inn > 0 else "0"


def _pitched(
    a: bool, gi: GameIter, box: Boxscore, team: int, slot: int, seq: int, p: BoxPlayer
) -> str:
    return "1" if p.fielding[1] is not None else "0"


def _pitching(cat: str) -> Field:
    """``DECLARE_PITCHING_CATEGORY``: the player's pitching entries summed, null if any is null"""

    def f(
        a: bool, gi: GameIter, box: Boxscore, team: int, slot: int, seq: int, p: BoxPlayer
    ) -> str:
        stat = 0
        pitcher = box.pitchers[team]
        if p.fielding[1] is not None:
            while pitcher is not None:
                if pitcher.player_id == p.player_id:
                    value = getattr(pitcher.pitching, cat)
                    if value < 0:
                        stat = -1
                        break
                    stat += value
                pitcher = pitcher.prev
        return _int_or_null(stat)

    return f


def _pitching_tb(
    a: bool, gi: GameIter, box: Boxscore, team: int, slot: int, seq: int, p: BoxPlayer
) -> str:
    stat = 0
    pitcher = box.pitchers[team]
    if p.fielding[1] is not None:
        while pitcher is not None:
            if pitcher.player_id == p.player_id:
                g = pitcher.pitching
                if g.h < 0 or g.b2 < 0 or g.b3 < 0 or g.hr < 0:
                    stat = -1
                    break
                stat += g.h + g.b2 + 2 * g.b3 + 3 * g.hr
            pitcher = pitcher.prev
    return _int_or_null(stat)


def _pitching_pitches(cat: str) -> Field:
    """``cwdaily_P_PITCH`` and ``cwdaily_P_STRIKE``: only if the game records pitches"""

    def f(
        a: bool, gi: GameIter, box: Boxscore, team: int, slot: int, seq: int, p: BoxPlayer
    ) -> str:
        stat = 0
        if gi.game.info_lookup("pitches") == "pitches":
            pitcher = box.pitchers[team]
            if p.fielding[1] is not None:
                while pitcher is not None:
                    if pitcher.player_id == p.player_id:
                        value = getattr(pitcher.pitching, cat)
                        if value < 0:
                            stat = -1
                            break
                        stat += value
                    pitcher = pitcher.prev
        else:
            stat = -1
        return _int_or_null(stat)

    return f


def _fielding(pos: int, cat: str) -> Field:
    """``DECLARE_FIELDING_CATEGORY``"""

    def f(
        a: bool, gi: GameIter, box: Boxscore, team: int, slot: int, seq: int, p: BoxPlayer
    ) -> str:
        fielding = p.fielding[pos]
        return "0" if fielding is None else _int_or_null(getattr(fielding, cat))

    return f


def _fielding_starter(pos: int) -> Field:
    """``DECLARE_FIELDING_STARTER``"""

    def f(
        a: bool, gi: GameIter, box: Boxscore, team: int, slot: int, seq: int, p: BoxPlayer
    ) -> str:
        return "1" if p.start_position == pos else "0"

    return f


def _fielding_tc(pos: int) -> Field:
    """``DECLARE_FIELDING_TC``: putouts + assists + errors, null if any is null"""

    def f(
        a: bool, gi: GameIter, box: Boxscore, team: int, slot: int, seq: int, p: BoxPlayer
    ) -> str:
        fielding = p.fielding[pos]
        if fielding is None:
            return "0"
        if fielding.po < 0 or fielding.a < 0 or fielding.e < 0:
            return _int_or_null(-1)
        return _int_or_null(fielding.po + fielding.a + fielding.e)

    return f


# (function, header, description) for fields 0-153
FIELDS: tuple[tuple[Field, str, str], ...] = (
    (_game_id, "GAME_ID", "game id"),
    (_date, "GAME_DT", "date"),
    (_number, "GAME_CT", "game number (0 = no double header)"),
    (_app_date, "APPEAR_DT", "apperance date"),
    (_team_id, "TEAM_ID", "team id"),
    (_player_id, "PLAYER_ID", "player id"),
    (_slot, "SLOT_CT", "player slot in batting order"),
    (_seq, "SEQ_CT", "sequence in batting order slot"),
    (_home_fl, "HOME_FL", "home flag"),
    (_opponent_id, "OPPONENT_ID", "opponent id"),
    (_site, "PARK_ID", "park id"),
    (_batting("g"), "B_G", "B_G:   games played"),
    (_batting("pa"), "B_PA", "B_PA:  plate appearances"),
    (_batting("ab"), "B_AB", "B_AB:  at bats"),
    (_batting("r"), "B_R", "B_R:   runs"),
    (_batting("h"), "B_H", "B_H:   hits"),
    (_batting_tb, "B_TB", "B_TB:  total bases"),
    (_batting("b2"), "B_2B", "B_2B:  doubles"),
    (_batting("b3"), "B_3B", "B_3B:  triples"),
    (_batting("hr"), "B_HR", "B_HR:  home runs"),
    (_batting("hrslam"), "B_HR4", "B_HR4: grand slams"),
    (_batting("bi"), "B_RBI", "B_RBI: runs batted in"),
    (_batting("gw"), "B_GW", "B_GW:  game winning RBI"),
    (_batting("bb"), "B_BB", "B_BB:  walks"),
    (_batting("ibb"), "B_IBB", "B_IBB: intentional walks"),
    (_batting("so"), "B_SO", "B_SO:  strikeouts"),
    (_batting("gdp"), "B_GDP", "B_GDP: grounded into DP"),
    (_batting("hp"), "B_HP", "B_HP:  hit by pitch"),
    (_batting("sh"), "B_SH", "B_SH:  sacrifice hits"),
    (_batting("sf"), "B_SF", "B_SF:  sacrifice flies"),
    (_batting("sb"), "B_SB", "B_SB:  stolen bases"),
    (_batting("cs"), "B_CS", "B_CS:  caught stealing"),
    (_batting("xi"), "B_XI", "B_XI:  reached on interference"),
    (_b_g_dh, "B_G_DH", "B_G_DH: games as DH"),
    (_b_g_ph, "B_G_PH", "B_G_PH: games as PH"),
    (_b_g_pr, "B_G_PR", "B_G_PR: games as PR"),
    (_pitched, "P_G", "P_G:   games pitched"),
    (_pitching("gs"), "P_GS", "P_GS:  games started"),
    (_pitching("cg"), "P_CG", "P_CG:  complete games"),
    (_pitching("sho"), "P_SHO", "P_SHO: shutouts"),
    (_pitching("gf"), "P_GF", "P_GF:  games finished"),
    (_pitching("w"), "P_W", "P_W:  wins"),
    (_pitching("l"), "P_L", "P_L:  losses"),
    (_pitching("sv"), "P_SV", "P_SV:  saves"),
    (_pitching("outs"), "P_OUT", "P_OUT: outs recorded (innings pitched times 3)"),
    (_pitching("bf"), "P_TBF", "P_TBF: batters faced"),
    (_pitching("ab"), "P_AB", "P_AB:  at bats"),
    (_pitching("r"), "P_R", "P_R:   runs allowed"),
    (_pitching("er"), "P_ER", "P_ER:  earned runs allowed"),
    (_pitching("h"), "P_H", "P_H:   hits allowed"),
    (_pitching_tb, "P_TB", "P_TB:  total bases allowed"),
    (_pitching("b2"), "P_2B", "P_2B:  doubles allowed"),
    (_pitching("b3"), "P_3B", "P_3B:  triples allowed"),
    (_pitching("hr"), "P_HR", "P_HR:  home runs allowed"),
    (_pitching("hrslam"), "P_HR4", "P_HR4:  grand slams allowed"),
    (_pitching("bb"), "P_BB", "P_BB:  walks allowed"),
    (_pitching("ibb"), "P_IBB", "P_IBB: intentional walks allowed"),
    (_pitching("so"), "P_SO", "P_SO:  strikeouts"),
    (_pitching("gdp"), "P_GDP", "P_GDP: grounded into double play"),
    (_pitching("hb"), "P_HP", "P_HP:  hit batsmen"),
    (_pitching("sh"), "P_SH", "P_SH:  sacrifice hits against"),
    (_pitching("sf"), "P_SF", "P_SF:  sacrifice flies against"),
    (_pitching("xi"), "P_XI", "P_XI:  reached on interference"),
    (_pitching("wp"), "P_WP", "P_WP:  wild pitches"),
    (_pitching("bk"), "P_BK", "P_BK:  balks"),
    (_pitching("inr"), "P_IR", "P_IR:  inherited runners"),
    (_pitching("inrs"), "P_IRS", "P_IRS: inherited runners scored"),
    (_pitching("gb"), "P_GO", "P_GO:  ground outs"),
    (_pitching("fb"), "P_AO", "P_AO:  air outs"),
    (_pitching_pitches("pitches"), "P_PITCH", "P_PITCH:  pitches"),
    (_pitching_pitches("strikes"), "P_STRIKE", "P_STRIKE: strikes"),
    (_pitched, "F_P_G", "F_P_G:    games at P"),
    (_pitching("gs"), "F_P_GS", "F_P_GS:   games started at P"),
    (_fielding(1, "outs"), "F_P_OUT", "F_P_OUT:  outs recorded at P (innings fielded times 3)"),
    (_fielding_tc(1), "F_P_TC", "F_P_TC:   total chances at P"),
    (_fielding(1, "po"), "F_P_PO", "F_P_PO:   putouts at P"),
    (_fielding(1, "a"), "F_P_A", "F_P_A:    assists at P"),
    (_fielding(1, "e"), "F_P_E", "F_P_E:    errors at P"),
    (_fielding(1, "dp"), "F_P_DP", "F_P_DP:   double plays at P"),
    (_fielding(1, "tp"), "F_P_TP", "F_P_TP:   triple plays at P"),
    (_fielding(2, "g"), "F_C_G", "F_C_G:    games at C"),
    (_fielding_starter(2), "F_C_GS", "F_C_GS:   games started at C"),
    (_fielding(2, "outs"), "F_C_OUT", "F_C_OUT:  outs recorded at C (innings fielded times 3)"),
    (_fielding_tc(2), "F_C_TC", "F_C_TC:   total chances at C"),
    (_fielding(2, "po"), "F_C_PO", "F_C_PO:   putouts at C"),
    (_fielding(2, "a"), "F_C_A", "F_C_A:    assists at C"),
    (_fielding(2, "e"), "F_C_E", "F_C_E:    errors at C"),
    (_fielding(2, "dp"), "F_C_DP", "F_C_DP:   double plays at C"),
    (_fielding(2, "tp"), "F_C_TP", "F_C_TP:   triple plays at C"),
    (_fielding(2, "pb"), "F_C_PB", "F_C_PB:   passed balls at C"),
    (_fielding(2, "xi"), "F_C_XI", "F_C_IX:   catcher's interference at C"),
    (_fielding(3, "g"), "F_1B_G", "F_1B_G:   games at 1B"),
    (_fielding_starter(3), "F_1B_GS", "F_1B_GS:  games started at 1B"),
    (_fielding(3, "outs"), "F_1B_OUT", "F_1B_OUT: outs recorded at 1B (innings fielded times 3)"),
    (_fielding_tc(3), "F_1B_TC", "F_1B_TC:  total chances at 1B"),
    (_fielding(3, "po"), "F_1B_PO", "F_1B_PO:  putouts at 1B"),
    (_fielding(3, "a"), "F_1B_A", "F_1B_A:   assists at 1B"),
    (_fielding(3, "e"), "F_1B_E", "F_1B_E:   errors at 1B"),
    (_fielding(3, "dp"), "F_1B_DP", "F_1B_DP:  double plays at 1B"),
    (_fielding(3, "tp"), "F_1B_TP", "F_1B_TP:  triple plays at 1B"),
    (_fielding(4, "g"), "F_2B_G", "F_2B_G:   games at 2B"),
    (_fielding_starter(4), "F_2B_GS", "F_2B_GS:  games started at 2B"),
    (_fielding(4, "outs"), "F_2B_OUT", "F_2B_OUT: outs recorded at 2B (innings fielded times 3)"),
    (_fielding_tc(4), "F_2B_TC", "F_2B_TC:  total chances at 2B"),
    (_fielding(4, "po"), "F_2B_PO", "F_2B_PO:  putouts at 2B"),
    (_fielding(4, "a"), "F_2B_A", "F_2B_A:   assists at 2B"),
    (_fielding(4, "e"), "F_2B_E", "F_2B_E:   errors at 2B"),
    (_fielding(4, "dp"), "F_2B_DP", "F_2B_DP:  double plays at 2B"),
    (_fielding(4, "tp"), "F_2B_TP", "F_2B_TP:  triple plays at 2B"),
    (_fielding(5, "g"), "F_3B_G", "F_3B_G:   games at 3B"),
    (_fielding_starter(5), "F_3B_GS", "F_3B_GS:  games started at 3B"),
    (_fielding(5, "outs"), "F_3B_OUT", "F_3B_OUT: outs recorded at 3B (innings fielded times 3)"),
    (_fielding_tc(5), "F_3B_TC", "F_3B_TC:  total chances at 3B"),
    (_fielding(5, "po"), "F_3B_PO", "F_3B_PO:  putouts at 3B"),
    (_fielding(5, "a"), "F_3B_A", "F_3B_A:   assists at 3B"),
    (_fielding(5, "e"), "F_3B_E", "F_3B_E:   errors at 3B"),
    (_fielding(5, "dp"), "F_3B_DP", "F_3B_DP:  double plays at 3B"),
    (_fielding(5, "tp"), "F_3B_TP", "F_3B_TP:  triple plays at 3B"),
    (_fielding(6, "g"), "F_SS_G", "F_SS_G:    games at SS"),
    (_fielding_starter(6), "F_SS_GS", "F_SS_GS:  games started at SS"),
    (_fielding(6, "outs"), "F_SS_OUT", "F_SS_OUT: outs recorded at SS (innings fielded times 3)"),
    (_fielding_tc(6), "F_SS_TC", "F_SS_TC:  total chances at SS"),
    (_fielding(6, "po"), "F_SS_PO", "F_SS_PO:  putouts at SS"),
    (_fielding(6, "a"), "F_SS_A", "F_SS_A:   assists at SS"),
    (_fielding(6, "e"), "F_SS_E", "F_SS_E:   errors at SS"),
    (_fielding(6, "dp"), "F_SS_DP", "F_SS_DP:  double plays at SS"),
    (_fielding(6, "tp"), "F_SS_TP", "F_SS_TP:  triple plays at SS"),
    (_fielding(7, "g"), "F_LF_G", "F_LF_G:   games at LF"),
    (_fielding_starter(7), "F_LF_GS", "F_LF_GS:  games started at LF"),
    (_fielding(7, "outs"), "F_LF_OUT", "F_LF_OUT: outs recorded at LF (innings fielded times 3)"),
    (_fielding_tc(7), "F_LF_TC", "F_LF_TC:  total chances at LF"),
    (_fielding(7, "po"), "F_LF_PO", "F_LF_PO:  putouts at LF"),
    (_fielding(7, "a"), "F_LF_A", "F_LF_A:   assists at LF"),
    (_fielding(7, "e"), "F_LF_E", "F_LF_E:   errors at LF"),
    (_fielding(7, "dp"), "F_LF_DP", "F_LF_DP:  double plays at LF"),
    (_fielding(7, "tp"), "F_LF_TP", "F_LF_TP:  triple plays at LF"),
    (_fielding(8, "g"), "F_CF_G", "F_CF_G:   games at CF"),
    (_fielding_starter(8), "F_CF_GS", "F_CF_GS:  games started at CF"),
    (_fielding(8, "outs"), "F_CF_OUT", "F_CF_OUT: outs recorded at CF (innings fielded times 3)"),
    (_fielding_tc(8), "F_CF_TC", "F_CF_TC:  total chances at CF"),
    (_fielding(8, "po"), "F_CF_PO", "F_CF_PO:  putouts at CF"),
    (_fielding(8, "a"), "F_CF_A", "F_CF_A:   assists at CF"),
    (_fielding(8, "e"), "F_CF_E", "F_CF_E:   errors at CF"),
    (_fielding(8, "dp"), "F_CF_DP", "F_CF_DP:  double plays at CF"),
    (_fielding(8, "tp"), "F_CF_TP", "F_CF_TP:  triple plays at CF"),
    (_fielding(9, "g"), "F_RF_G", "F_RF_G:   games at RF"),
    (_fielding_starter(9), "F_RF_GS", "F_RF_GS:  games started at RF"),
    (_fielding(9, "outs"), "F_RF_OUT", "F_RF_OUT: outs recorded at RF (innings fielded times 3)"),
    (_fielding_tc(9), "F_RF_TC", "F_RF_TC:  total chances at RF"),
    (_fielding(9, "po"), "F_RF_PO", "F_RF_PO:  putouts at RF"),
    (_fielding(9, "a"), "F_RF_A", "F_RF_A:   assists at RF"),
    (_fielding(9, "e"), "F_RF_E", "F_RF_E:   errors at RF"),
    (_fielding(9, "dp"), "F_RF_DP", "F_RF_DP:  double plays at RF"),
    (_fielding(9, "tp"), "F_RF_TP", "F_RF_TP:  triple plays at RF"),
)

COLUMNS = tuple(header for _, header, _ in FIELDS)
MAX_FIELD = len(FIELDS) - 1


def header_line(fields: tuple[int, ...] = tuple(range(MAX_FIELD + 1))) -> str:
    """``cwdaily_initialize`` with ``-n``: the quoted column names (ascii format only)."""
    return ",".join(f'"{FIELDS[i][1]}"' for i in fields)


def game_lines(
    game: Game,
    ascii_: bool = True,
    fields: tuple[int, ...] = tuple(range(MAX_FIELD + 1)),
) -> Iterator[str]:
    """``cwdaily_process_game``: one line per player appearance, team by team, in batting order.

    "We list non-batting pitchers last, but they are coded as slot 0".
    """
    gi = GameIter(game)
    box = box_create(game)
    while gi.event is not None:
        gi.next()

    for team in (0, 1):
        for j in range(1, 11):
            player = get_starter(box, team, j % 10)
            seq = 1
            while player is not None:
                sep = "," if ascii_ else ""
                yield sep.join(FIELDS[i][0](ascii_, gi, box, team, j, seq, player) for i in fields)
                player = player.next
                seq += 1


def daily_lines(
    data: bytes,
    league: League | None = None,
    game_id: str = "",
    first_date: str = "0101",
    last_date: str = "1231",
    ascii_: bool = True,
    fields: tuple[int, ...] = tuple(range(MAX_FIELD + 1)),
) -> Iterator[str]:
    """Lines for the selected games of an event file, as ``cwdaily`` prints them."""
    for game, _visitors, _home in iterate_games(data, league, game_id, first_date, last_date):
        yield from game_lines(game, ascii_, fields)
