"""Port of Chadwick's XML boxscore output (``src/cwtools/cwboxxml.c``, ``cwbox -X``).

Chadwick is Copyright (c) 2002-2023 Dr T L Turocy and the Chadwick Baseball
Bureau, licensed GPL-2.0-or-later; this module is a derivative of it and keeps
that notice. One function per ``cwbox_xml_*`` function, each returning the text
the C ``printf`` calls write. As in the C, attribute values are written as they
are, with no XML escaping.

A C ``NULL`` string printed through ``%s`` is "(null)" (glibc). Where the C reads
past the 20 players of a notable event, this port raises ``ValueError``.

Deviation: ``cwbox_xml_player`` tests ``player->positions[pos] == 2`` with ``pos`` the
*fielding* position being printed, so it reads entries of ``positions`` beyond the
``num_positions`` the player filled. ``cw_box_player_create`` never initialises that array
(``malloc``), so in the C the ``pb`` attribute of a ``<fielding>`` element depends on whatever
the allocator hands back. The port defines those entries as 0 (what a zero-filled allocator
gives); with the real binary the output differs from the port only in such ``pb`` attributes.
"""

from retrosheetpy.cw.box import (
    BoxEvent,
    BoxPlayer,
    Boxscore,
    get_starter,
    get_starting_pitcher,
)
from retrosheetpy.cw.game import Game
from retrosheetpy.cw.roster import Roster


def _s(value: str | None) -> str:
    return "(null)" if value is None else value


def _info(game: Game, key: str) -> str | None:
    return game.info_lookup(key)


def linescore(box: Boxscore) -> str:
    """``cwbox_xml_linescore``"""
    out = (
        f'  <linescore away_runs="{box.score[0]}" away_hits="{box.hits[0]}" '
        f'away_errors="{box.errors[0]}" home_runs="{box.score[1]}" '
        f'home_hits="{box.hits[1]}" home_errors="{box.errors[1]}">\n'
    )
    i = 1
    while i < 50:
        if box.linescore[i][0] < 0 and box.linescore[i][1] < 0:
            break
        if box.linescore[i][1] >= 0:
            out += (
                f'    <inning_line_score away="{box.linescore[i][0]}" '
                f'home="{box.linescore[i][1]}" inning="{i}"/>\n'
            )
        else:
            out += f'    <inning_line_score away="{box.linescore[i][0]}" home="x" inning="{i}"/>\n'
        i += 1
    return out + "  </linescore>\n"


def player(game: Game, p: BoxPlayer, slot: int, seq: int, roster: Roster | None) -> str:
    """``cwbox_xml_player``: one player's boxscore entry"""
    bio = roster.player_find(p.player_id) if roster is not None else None
    out = (
        f'    <player id="{p.player_id}" lname="{bio.last_name if bio else ""}" '
        f'fname="{bio.first_name if bio else ""}" slot="{slot}" seq="{seq}" '
    )
    out += 'pos="'
    if p.ph_inn > 0 and p.positions[0] != 11:
        out += "h"
    elif p.pr_inn > 0 and p.positions[0] != 12:
        out += "r"
    for pos in range(p.num_positions):
        code = p.positions[pos]
        if code == 10:
            out += "d"
        elif code == 11:
            out += "h"
        elif code == 12:
            out += "r"
        else:
            out += str(code)
    out += '" '

    if p.ph_inn > 0:
        out += f'ph_inning="{p.ph_inn}" '
    elif p.pr_inn > 0:
        out += f'pr_inning="{p.pr_inn}" '
    out += ">\n"

    if slot > 0:
        b = p.batting
        out += (
            f'      <batting ab="{b.ab}" r="{b.r}" h="{b.h}" d="{b.b2}" t="{b.b3}" '
            f'hr="{b.hr}" bi="{b.bi}" bi2out="{b.bi2out}" '
        )
        out += (
            f'bb="{b.bb}" ibb="{b.ibb}" so="{b.so}" gdp="{b.gdp}" '
            f'hp="{b.hp}" sh="{b.sh}" sf="{b.sf}" '
        )
        out += f'sb="{b.sb}" cs="{b.cs}" '
        gwrbi = _info(game, "gwrbi")
        if gwrbi is not None and p.player_id == gwrbi:
            out += 'gwrbi="1" '
        out += "/>\n"

    for pos in range(1, 10):
        f = p.fielding[pos]
        if f is None:
            continue
        out += f'      <fielding pos="{pos}" '
        out += f'outs="{f.outs}" po="{f.po}" a="{f.a}" e="{f.e}" dp="{f.dp}" tp="{f.tp}" '
        if p.positions[pos] == 2:
            out += f'pb="{f.pb}" '
        out += f'bip="{f.bip}" bf="{f.bf}" '
        out += "/>\n"
    return out + "    </player>\n"


def batting(game: Game, box: Boxscore, t: int, roster: Roster | None) -> str:
    """``cwbox_xml_batting``: the boxscore entries for players on team ``t``"""
    out = (
        f'  <players team="{roster.team_id if roster else ""}" lob="{box.lob[t]}" '
        f'dp="{box.dp[t]}" tp="{box.tp[t]}" risp_ab="{box.risp_ab[t]}" '
        f'risp_h="{box.risp_h[t]}">\n'
    )
    for slot in range(10):
        p = get_starter(box, t, slot)
        seq = 1
        while p is not None:
            out += player(game, p, slot, seq, roster)
            seq += 1
            p = p.next
    return out + "  </players>\n"


def pitching(game: Game, box: Boxscore, t: int, roster: Roster | None) -> str:
    """``cwbox_xml_pitching``: the pitching lines for team ``t``"""
    pitcher = get_starting_pitcher(box, t)
    out = f'  <pitching team="{roster.team_id if roster else ""}">\n'
    while pitcher is not None:
        bio = roster.player_find(pitcher.player_id) if roster is not None else None
        p = pitcher.pitching
        out += (
            f'    <pitcher id="{pitcher.player_id}" lname="{bio.last_name if bio else ""}" '
            f'fname="{bio.first_name if bio else ""}" '
        )
        # FIXME in the C: a pitcher gets a shutout if he records all outs for a team, even if
        # not the starting pitcher
        first, last = pitcher.prev is None, pitcher.next is None
        out += (
            f'gs="{int(first)}" cg="{int(first and last)}" '
            f'sho="{int(first and last and p.r == 0)}" gf="{int(not first and last)}" '
        )
        out += (
            f'outs="{p.outs}" ab="{p.ab}" bf="{p.bf}" h="{p.h}" r="{p.r}" er="{p.er}" hr="{p.hr}" '
        )
        out += f'bb="{p.bb}" ibb="{p.ibb}" so="{p.so}" wp="{p.wp}" bk="{p.bk}" hb="{p.hb}" '
        out += f'gb="{p.gb}" fb="{p.fb}" '
        if p.xbinn > 0:
            out += f'xb="{p.xb}" xbinn="{p.xbinn}" '
        pitches = _info(game, "pitches")
        if pitches is not None and pitches == "pitches":
            out += f'pitch="{p.pitches}" strike="{p.strikes}" '
        wp, lp, save = _info(game, "wp"), _info(game, "lp"), _info(game, "save")
        if wp is not None and pitcher.player_id == wp:
            out += 'dec="W" '
        elif lp is not None and pitcher.player_id == lp:
            out += 'dec="L" '
        elif save is not None and pitcher.player_id == save:
            out += 'dec="S" '
        out += "/>\n"
        pitcher = pitcher.next
    return out + "  </pitching>\n"


def _player(event: BoxEvent, index: int) -> str | None:
    if index >= len(event.players):
        raise ValueError("player index out of range (undefined behaviour in C)")
    return event.players[index]


def batting_events(events: list[BoxEvent], mainlabel: str, itemlabel: str) -> str:
    """``cwbox_xml_batting_events``: generic output for batting event entries"""
    if not events:
        return ""
    out = f"  <{mainlabel}>\n"
    for e in events:
        out += (
            f'    <{itemlabel} batter="{_s(_player(e, 0))}" pitcher="{_s(_player(e, 1))}" '
            f'inning="{e.inning}" half="{e.half_inning}"/>\n'
        )
    return out + f"  </{mainlabel}>\n"


def homeruns(events: list[BoxEvent]) -> str:
    """``cwbox_xml_homeruns``"""
    if not events:
        return ""
    out = "  <homeruns>\n"
    for e in events:
        out += (
            f'    <homerun batter="{_s(_player(e, 0))}" pitcher="{_s(_player(e, 1))}" '
            f'inning="{e.inning}" half="{e.half_inning}" runners="{e.runners}" '
            f'outs="{e.outs}" location="{_s(e.location)}"/>\n'
        )
    return out + "  </homeruns>\n"


def steal_events(events: list[BoxEvent], mainlabel: str, itemlabel: str) -> str:
    """``cwbox_xml_steal_events``: generic output for stolen base events"""
    if not events:
        return ""
    out = f"  <{mainlabel}>\n"
    for e in events:
        base = e.runners + 1 if e.runners >= 0 else -1
        out += (
            f'    <{itemlabel} runner="{_s(_player(e, 0))}" pitcher="{_s(_player(e, 1))}" '
            f'catcher="{_player(e, 2) or ""}" inning="{e.inning}" half="{e.half_inning}" '
            f'base="{base}" pickoff="{e.pickoff}"/>\n'
        )
    return out + f"  </{mainlabel}>\n"


def pickoff_events(events: list[BoxEvent]) -> str:
    """``cwbox_xml_pickoff_events``"""
    if not events:
        return ""
    out = "  <pickoffs>\n"
    for e in events:
        out += (
            f'    <pickoff runner="{_s(_player(e, 0))}" fielder="{_s(_player(e, 1))}" '
            f'inning="{e.inning}" half="{e.half_inning}" base="{e.runners}" '
            f'pickoff="{e.pickoff}"/>\n'
        )
    return out + "  </pickoffs>\n"


def wildpitch_events(events: list[BoxEvent]) -> str:
    """``cwbox_xml_wildpitch_events``"""
    if not events:
        return ""
    out = "  <wildpitches>\n"
    for e in events:
        out += (
            f'    <wildpitch pitcher="{_s(_player(e, 0))}" catcher="{_s(_player(e, 1))}" '
            f'inning="{e.inning}" half="{e.half_inning}"/>\n'
        )
    return out + "  </wildpitches>\n"


def passedball_events(events: list[BoxEvent]) -> str:
    """``cwbox_xml_passedball_events``"""
    if not events:
        return ""
    out = "  <passedballs>\n"
    for e in events:
        out += (
            f'    <passedball pitcher="{_s(_player(e, 0))}" catcher="{_s(_player(e, 1))}" '
            f'inning="{e.inning}" half="{e.half_inning}"/>\n'
        )
    return out + "  </passedballs>\n"


def multiplay_events(events: list[BoxEvent], mainlabel: str, itemlabel: str) -> str:
    """``cwbox_xml_multiplay_events``: double plays and triple plays"""
    if not events:
        return ""
    out = f"  <{mainlabel}>\n"
    for e in events:
        out += f'    <{itemlabel} inning="{e.inning}" half="{e.half_inning}" '
        i = 0
        while _player(e, i) is not None:
            out += f'player{i + 1}="{e.players[i]}" '
            i += 1
        out += "/>\n"
    return out + f"  </{mainlabel}>\n"


def print_xml(game: Game, box: Boxscore, visitors: Roster | None, home: Roster | None) -> str:
    """``cwbox_print_xml``: the boxscore in XML format"""
    out = (
        f'<boxscore game_id="{game.game_id}" date="{_s(_info(game, "date"))}" '
        f'site="{_s(_info(game, "site"))}" '
        f'visitor="{visitors.team_id if visitors else ""}" '
        f'visitor_city="{visitors.city if visitors else ""}" '
        f'visitor_name="{visitors.nickname if visitors else ""}" '
        f'home="{home.team_id if home else ""}" home_city="{home.city if home else ""}" '
        f'home_name="{home.nickname if home else ""}" '
    )
    out += (
        f'start_time="{_s(_info(game, "starttime"))}" day_night="{_s(_info(game, "daynight"))}" '
        f'temperature="{_s(_info(game, "temp"))}" wind_direction="{_s(_info(game, "winddir"))}" '
        f'wind_speed="{_s(_info(game, "windspeed"))}" '
        f'field_condition="{_s(_info(game, "fieldcond"))}" precip="{_s(_info(game, "precip"))}" '
        f'sky="{_s(_info(game, "sky"))}" time_of_game="{_s(_info(game, "timeofgame"))}" '
        f'attendance="{_s(_info(game, "attendance"))}" '
    )
    for key, attr in (
        ("umphome", "umpire_hp"),
        ("ump1b", "umpire_1b"),
        ("ump2b", "umpire_2b"),
        ("ump3b", "umpire_3b"),
        ("umplf", "umpire_lf"),
        ("umprf", "umpire_rf"),
    ):
        value = _info(game, key)
        if value is not None:
            out += f'{attr}="{value}" '
    if box.outs_at_end != 3:
        out += f'walk_off="{box.walk_off}" outs_at_end="{box.outs_at_end}" '
    htbf = _info(game, "htbf")
    if htbf is not None and htbf == "true":
        out += 'htbf="1" '
    out += ">\n"

    out += linescore(box)
    out += batting(game, box, 0, visitors)
    out += batting(game, box, 1, home)
    out += pitching(game, box, 0, visitors)
    out += pitching(game, box, 1, home)

    out += batting_events(box.b2_list, "doubles", "double")
    out += batting_events(box.b3_list, "triples", "triple")
    out += homeruns(box.hr_list)
    out += batting_events(box.ibb_list, "intentionalwalks", "intentionalwalk")
    out += batting_events(box.hp_list, "hitbypitches", "hitbypitch")
    out += batting_events(box.sh_list, "sacbunts", "sacbunt")
    out += batting_events(box.sf_list, "sacflies", "sacfly")

    out += steal_events(box.sb_list, "stolenbases", "stolenbase")
    out += steal_events(box.cs_list, "caughtstealings", "caughtstealing")
    out += pickoff_events(box.po_list)

    out += wildpitch_events(box.wp_list)
    out += passedball_events(box.pb_list)
    out += multiplay_events(box.dp_list, "doubleplays", "doubleplay")
    out += multiplay_events(box.tp_list, "tripleplays", "tripleplay")
    return out + "</boxscore>\n\n"
