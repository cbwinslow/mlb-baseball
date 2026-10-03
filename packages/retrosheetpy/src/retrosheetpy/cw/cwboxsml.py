"""Port of Chadwick's SportsML boxscore output (``src/cwtools/cwboxsml.c``, ``cwbox -S``).

Chadwick is Copyright (c) 2002-2023 Dr T L Turocy and the Chadwick Baseball
Bureau, licensed GPL-2.0-or-later; this module is a derivative of it and keeps
that notice. One function per ``cwbox_*`` function of the C file, writing through the
``xmlwrite`` port exactly as the C does.

A C ``NULL`` string printed through ``%s`` is "(null)" (glibc). Where the C dereferences
``NULL``, reads an uninitialised variable, reads past the end of a string (a short date, a
malformed extended pitch record) or ``exit``s (a play that does not parse), this port raises
``ValueError``.

Deviations:

1. ``cwbox_action_baseball_play`` passes ``state->runners[1]`` and ``[2]`` (whole structs, not
   their ``runner`` member) to a ``%s`` conversion, which is undefined behaviour (the real
   ``cwbox -S`` segfaults on it); the port writes the runner's player id, as
   ``runners[3].runner`` does.
2. When a play's pitch string is shorter than the previous event's, the C skips that many
   characters from the start of the string, past its terminating NUL, and reads whatever memory
   follows (undefined behaviour); the port reads no pitches for that play, which is what a NUL
   right after the string gives.
3. The ``date-time`` attribute of ``sports-metadata`` is the current local time, as in the C.
"""

import time
from typing import TypeVar

from retrosheetpy.cw.box import (
    BoxPitcher,
    BoxPlayer,
    Boxscore,
    find_pitcher,
    get_starter,
    get_starting_pitcher,
)
from retrosheetpy.cw.file import cw_atoi, scan_int
from retrosheetpy.cw.game import Appearance, Game
from retrosheetpy.cw.gameiter import GameIter
from retrosheetpy.cw.parse import (
    Ev,
    is_batter,
    outs_on_play,
    rbi_on_play,
    runs_on_play,
)
from retrosheetpy.cw.roster import Roster
from retrosheetpy.cw.xmlwrite import (
    XMLDoc,
    XMLNode,
    xml_document_cleanup,
    xml_node_attribute,
    xml_node_attribute_fmt,
    xml_node_attribute_int,
    xml_node_attribute_posint,
    xml_node_cdata,
    xml_node_open,
)


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


def _date(game: Game) -> str:
    """The ``date`` info record; the C indexes it up to ``date[9]`` unchecked"""
    date = _deref(_info(game, "date"))
    if len(date) < 10:
        raise ValueError(f"date {date!r} is shorter than the C reads (undefined behaviour)")
    return date


def _season(game: Game) -> str:
    """``strncpy(season, date, 4); season[4] = '\\0'``"""
    return _deref(_info(game, "date"))[:4]


def _htbf(game: Game) -> bool:
    htbf = _info(game, "htbf")
    return htbf is not None and htbf == "true"


def _pitches_flag(game: Game) -> bool:
    pitches = _info(game, "pitches")
    return pitches is not None and pitches == "pitches"


def _decision(game: Game, key: str, player_id: str) -> bool:
    value = _info(game, key)
    return value is not None and player_id == value


def player_metadata(
    parent: XMLNode, player: BoxPlayer, slot: int, seq: int, roster: Roster | None
) -> None:
    """``cwbox_player_metadata``: a ``<player-metadata>`` element"""
    node = xml_node_open(parent, "player-metadata")
    if player.positions[0] == 10:
        xml_node_attribute(node, "position-event", "dh")
    elif player.positions[0] == 11 or player.ph_inn > 0:
        xml_node_attribute(node, "position-event", "ph")
    elif player.positions[0] == 12 or player.pr_inn > 0:
        xml_node_attribute(node, "position-event", "pr")
    else:
        xml_node_attribute_int(node, "position-event", player.positions[0])
    xml_node_attribute(node, "player-key", player.player_id)
    xml_node_attribute(node, "status", "starter" if seq == 1 else "bench")
    xml_node_attribute_int(node, "lineup-slot", slot)
    xml_node_attribute_int(node, "lineup-slot-sequence", seq)

    if roster is not None:
        bio = roster.player_find(player.player_id)
        if bio is not None:
            name_node = xml_node_open(node, "name")
            xml_node_attribute(name_node, "first", bio.first_name)
            xml_node_attribute(name_node, "last", bio.last_name)


def player_stats_offensive(parent: XMLNode, player: BoxPlayer) -> None:
    """``cwbox_player_stats_offensive``: a ``<stats-baseball-offensive>`` element"""
    node = xml_node_open(parent, "stats-baseball-offensive")
    b = player.batting
    for attr, value in (
        ("plate-appearances", b.pa),
        ("at-bats", b.ab),
        ("runs-scored", b.r),
        ("hits", b.h),
        ("total-bases", b.h + b.b2 + 2 * b.b3 + 3 * b.hr),
        ("hits-extra-base", b.b2 + b.b3 + b.hr),
        ("singles", b.h - b.b2 - b.b3 - b.hr),
        ("doubles", b.b2),
        ("triples", b.b3),
        ("home-runs", b.hr),
        ("grand-slams", b.hrslam),
        ("rbi", b.bi),
        ("bases-on-balls", b.bb),
        ("bases-on-balls-intentional", b.ibb),
        ("strikeouts", b.so),
        ("grounded-into-double-play", b.gdp),
        ("hit-by-pitch", b.hp),
        ("sac-bunts", b.sh),
        ("sac-flies", b.sf),
        ("stolen-bases", b.sb),
        ("stolen-bases-caught", b.cs),
        ("reached-base-defensive-interference", b.xi),
        ("left-in-scoring-position", b.lisp),
        ("moved-up", b.movedup),
    ):
        xml_node_attribute_posint(node, attr, value)


def player_stats_defensive(parent: XMLNode, player: BoxPlayer) -> None:
    """``cwbox_player_stats_defensive``: a ``<stats-baseball-defensive>`` element"""
    node = xml_node_open(parent, "stats-baseball-defensive")
    outs = po = a = e = dp = tp = pb = xi = 0
    for pos in range(1, 10):
        f = player.fielding[pos]
        if f is None:
            continue
        outs += f.outs
        po += f.po
        a += f.a
        e += f.e
        dp += f.dp
        tp += f.tp
        if pos == 2:
            pb += f.pb
            xi += f.xi
    if outs > 0:
        xml_node_attribute_fmt(node, "innings-played", f"{_cdiv(outs, 3)}.{_cmod(outs, 3)}")
    xml_node_attribute_posint(node, "putouts", po)
    xml_node_attribute_posint(node, "assists", a)
    xml_node_attribute_posint(node, "errors", e)
    xml_node_attribute_posint(node, "double-plays", dp)
    xml_node_attribute_posint(node, "triple-plays", tp)
    xml_node_attribute_posint(node, "errors-passed-ball", pb)
    xml_node_attribute_posint(node, "errors-catchers-interference", xi)


def _innings_pitched(node: XMLNode, outs: int) -> None:
    if _cmod(outs, 3) == 0:
        xml_node_attribute_int(node, "innings-pitched", _cdiv(outs, 3))
    else:
        xml_node_attribute_fmt(node, "innings-pitched", f"{_cdiv(outs, 3)}.{_cmod(outs, 3)}")


def player_stats_pitching(parent: XMLNode, game: Game, pitcher: BoxPitcher) -> None:
    """``cwbox_player_stats_pitching``: a ``<stats-baseball-pitching>`` element"""
    node = xml_node_open(parent, "stats-baseball-pitching")
    p = pitcher.pitching
    _innings_pitched(node, p.outs)
    for attr, value in (
        ("batters-at-bats-against", p.ab),
        ("batters-total-against", p.bf),
        ("hits", p.h),
        ("runs-allowed", p.r),
        ("earned-runs", p.er),
        ("unearned-runs", p.r - p.er),
        ("home-runs-allowed", p.hr),
        ("singles-allowed", p.h - p.b2 - p.b3 - p.hr),
        ("doubles-allowed", p.b2),
        ("triples-allowed", p.b3),
        ("sacrifice-bunts-allowed", p.sh),
        ("sacrifice-flies-allowed", p.sf),
        ("bases-on-balls", p.bb),
        ("bases-on-balls-intentional", p.ibb),
        ("strikeouts", p.so),
        ("errors-hit-with-pitch", p.hb),
        ("errors-wild-pitch", p.wp),
        ("balks", p.bk),
        ("pick-offs", p.pk),
        ("inherited-runners-total", p.inr),
        ("inherited-runners-scored", p.inrs),
    ):
        xml_node_attribute_posint(node, attr, value)

    # FIXME in the C: a pitcher gets a shutout if he records all outs for a team, even if not
    # the starting pitcher
    first, last = pitcher.prev is None, pitcher.next is None
    xml_node_attribute_int(node, "shutouts", int(first and last and p.r == 0))
    xml_node_attribute_int(node, "games-complete", int(first and last))
    xml_node_attribute_int(node, "games-finished", int(not first and last))

    if _pitches_flag(game):
        xml_node_attribute_int(node, "number-of-pitches", p.pitches)
        xml_node_attribute_int(node, "number-of-strikes", p.strikes)

    if _decision(game, "wp", pitcher.player_id):
        xml_node_attribute(node, "event-credit", "win")
    elif _decision(game, "lp", pitcher.player_id):
        xml_node_attribute(node, "event-credit", "loss")
    elif _decision(game, "save", pitcher.player_id):
        xml_node_attribute(node, "event-credit", "save")
        xml_node_attribute(node, "save-credit", "save")


def player(
    parent: XMLNode,
    game: Game,
    p: BoxPlayer,
    pitching: BoxPitcher | None,
    slot: int,
    seq: int,
    roster: Roster | None,
) -> None:
    """``cwbox_player``: a ``<player>`` element"""
    node = xml_node_open(parent, "player")
    xml_node_attribute_fmt(node, "id", f"p.{p.player_id}")
    player_metadata(node, p, slot, seq, roster)
    stats_node = xml_node_open(node, "player-stats")
    stats_baseball = xml_node_open(stats_node, "player-stats-baseball")
    player_stats_offensive(stats_baseball, p)
    player_stats_defensive(stats_baseball, p)
    if pitching is not None:
        player_stats_pitching(stats_baseball, game, pitching)


def team_stats_baseball(parent: XMLNode, game: Game, box: Boxscore, t: int) -> None:
    """``cwbox_team_stats_baseball``: totals for a team, built from the player entries"""
    pa = ab = r = h = b2 = b3 = hr = hrslam = bi = 0
    bb = ibb = so = gdp = hp = sh = sf = 0
    sb = cs = xi = lisp = movedup = 0
    po = a = e = pb = dxi = 0
    outs = ha = ra = er = hra = bba = ibba = soa = 0
    sha = sfa = hb = wp = bk = pk = inr = inrs = 0
    pitches = strikes = 0

    for slot in range(1, 10):
        p = get_starter(box, t, slot)
        while p is not None:
            b = p.batting
            pa += b.pa
            ab += b.ab
            r += b.r
            h += b.h
            b2 += b.b2
            b3 += b.b3
            hr += b.hr
            hrslam += b.hrslam
            bi += b.bi
            bb += b.bb
            ibb += b.ibb
            so += b.so
            gdp += b.gdp
            hp += b.hp
            sh += b.sh
            sf += b.sf
            sb += b.sb
            xi += b.xi
            cs += b.cs
            lisp += b.lisp
            movedup += b.movedup
            for pos in range(1, 10):
                f = p.fielding[pos]
                if f is not None:
                    po += f.po
                    a += f.a
                    e += f.e
            catcher = p.fielding[2]
            if catcher is not None:
                pb += catcher.pb
                dxi += catcher.xi
            p = p.next

    stats = xml_node_open(parent, "team-stats-baseball")

    node = xml_node_open(stats, "stats-baseball-offensive")
    for attr, value in (
        ("plate-appearances", pa),
        ("at-bats", ab),
        ("runs-scored", r),
        ("hits", h),
        ("total-bases", h + b2 + 2 * b3 + 3 * hr),
        ("hits-extra-base", b2 + b3 + hr),
        ("singles", h - b2 - b3 - hr),
        ("doubles", b2),
        ("triples", b3),
        ("home-runs", hr),
        ("grand-slams", hrslam),
        ("rbi", bi),
        ("bases-on-balls", bb),
        ("bases-on-balls-intentional", ibb),
        ("strikeouts", so),
        ("grounded-into-double-play", gdp),
        ("hit-by-pitch", hp),
        ("sac-bunts", sh),
        ("sac-flies", sf),
        ("stolen-bases", sb),
        ("stolen-bases-caught", cs),
        ("reached-base-defensive-interference", xi),
        ("left-on-base", box.lob[t]),
        ("left-in-scoring-position", lisp),
        ("moved-up", movedup),
    ):
        xml_node_attribute_posint(node, attr, value)

    node = xml_node_open(stats, "stats-baseball-defensive")
    for attr, value in (
        ("putouts", po),
        ("assists", a),
        ("errors", e),
        ("double-plays", box.dp[t]),
        ("triple-plays", box.tp[t]),
        ("errors-passed-ball", pb),
        ("errors-defensive-interference", dxi),
    ):
        xml_node_attribute_posint(node, attr, value)

    pitcher = get_starting_pitcher(box, t)
    while pitcher is not None:
        pp = pitcher.pitching
        outs += pp.outs
        ha += pp.h
        ra += pp.r
        er += pp.er
        hra += pp.hr
        sha += pp.sh
        sfa += pp.sf
        bba += pp.bb
        ibba += pp.ibb
        soa += pp.so
        hb += pp.hb
        wp += pp.wp
        bk += pp.bk
        pk += pp.pk
        inr += pp.inr
        inrs += pp.inrs
        pitches += pp.pitches
        strikes += pp.strikes
        pitcher = pitcher.next

    node = xml_node_open(stats, "stats-baseball-pitching")
    _innings_pitched(node, outs)
    for attr, value in (
        ("runs-allowed", ra),
        ("earned-runs", er),
        ("hits", ha),
        ("home-runs-allowed", hra),
        ("bases-on-balls", bba),
        ("bases-on-balls-intentional", ibba),
        ("strikeouts", soa),
        ("sacrifice-bunts-allowed", sha),
        ("sacrifice-flies-allowed", sfa),
        ("errors-hit-with-pitch", hb),
        ("errors-wild-pitch", wp),
        ("balks", bk),
        ("pick-offs", pk),
        ("inherited-runners-total", inr),
        ("inherited-runners-scored", inrs),
    ):
        xml_node_attribute_posint(node, attr, value)
    if _pitches_flag(game):
        xml_node_attribute_int(node, "number-of-pitches", pitches)
        xml_node_attribute_int(node, "number-of-strikes", strikes)

    if _deref(get_starting_pitcher(box, t)).next is None:
        xml_node_attribute_int(node, "games-complete", 1)
        xml_node_attribute_int(node, "games-finished", 0)
    else:
        xml_node_attribute_int(node, "games-complete", 0)
        xml_node_attribute_int(node, "games-finished", 1)
    xml_node_attribute_int(node, "shutouts", 1 if ra == 0 else 0)


def team_stats(parent: XMLNode, game: Game, box: Boxscore, t: int) -> None:
    """``cwbox_team_stats``: a ``<team-stats>`` node"""
    node = xml_node_open(parent, "team-stats")
    xml_node_attribute_int(node, "score", box.score[t])
    if box.score[t] > box.score[1 - t]:
        xml_node_attribute(node, "event-outcome", "win")
    elif box.score[t] < box.score[1 - t]:
        xml_node_attribute(node, "event-outcome", "loss")
    else:
        xml_node_attribute(node, "event-outcome", "tie")

    i = 1
    while i < 50:
        if box.linescore[i][0] < 0 and box.linescore[i][1] < 0:
            break
        subnode = xml_node_open(node, "sub-score")
        xml_node_attribute_int(subnode, "period-value", i)
        if box.linescore[i][t] >= 0:
            xml_node_attribute_int(subnode, "score", box.linescore[i][t])
        i += 1

    team_stats_baseball(node, game, box, t)


def team_metadata(parent: XMLNode, t: int, roster: Roster | None) -> None:
    """``cwbox_team_metadata``: a ``<team-metadata>`` node"""
    node = xml_node_open(parent, "team-metadata")
    xml_node_attribute(node, "alignment", "away" if t == 0 else "home")
    if roster is not None:
        xml_node_attribute(node, "team-key", roster.team_id)
        name_node = xml_node_open(node, "name")
        xml_node_attribute(name_node, "first", roster.city)
        xml_node_attribute(name_node, "last", roster.nickname)


def team(parent: XMLNode, game: Game, box: Boxscore, t: int, roster: Roster | None) -> None:
    """``cwbox_team``: a ``<team>`` node with the data for team ``t``"""
    node = xml_node_open(parent, "team")
    team_metadata(node, t, roster)
    team_stats(node, game, box, t)
    for slot in range(1, 11):
        # This loop puts the zero slot for non-batting pitchers last
        p = get_starter(box, t, slot % 10)
        seq = 1
        while p is not None:
            player(node, game, p, find_pitcher(box, p.player_id), slot % 10, seq, roster)
            seq += 1
            p = p.next


def official(parent: XMLNode, game: Game, info_label: str, meta_label: str) -> None:
    """``cwbox_official``: the official at Retrosheet umpire position ``info_label``; nothing if
    that position is empty"""
    ump_id = _info(game, info_label)
    if ump_id is not None:
        ump_node = xml_node_open(parent, "official")
        data_node = xml_node_open(ump_node, "official-metadata")
        xml_node_attribute(data_node, "position", meta_label)
        xml_node_attribute_fmt(data_node, "official-key", f"p.{ump_id}")


def officials(parent: XMLNode, game: Game) -> None:
    """``cwbox_officials``"""
    node = xml_node_open(parent, "officials")
    official(node, game, "umphome", "Home Plate Umpire")
    official(node, game, "ump1b", "First Base Umpire")
    official(node, game, "ump2b", "Second Base Umpire")
    official(node, game, "ump3b", "Third Base Umpire")
    official(node, game, "umplf", "Left Field Umpire")
    official(node, game, "umprf", "Right Field Umpire")


def sml_get_play_type(gi: GameIter) -> str:  # noqa: C901, PLR0911, PLR0912
    """``cwbox_sml_get_play_type``

    NOTE in the C: this is not yet part of the formal SportsML standard. For now, these imitate
    MLBAM codes, except using SportsML-style dashes in between words, instead of MLBAM's
    underscores.
    """
    d = gi.data
    t = d.event_type
    if t == Ev.GENERICOUT:
        if d.sh_flag:
            return "sac-bunt-double-play" if d.dp_flag else "sac-bunt"
        if d.sf_flag:
            return "sac-fly-double-play" if d.dp_flag else "sac-fly"
        if d.gdp_flag:
            return "grounded-into-double-play"
        if d.dp_flag:
            return "double-play"
        if d.tp_flag:
            return "triple-play"
        if d.fc_flag[1] or d.fc_flag[2] or d.fc_flag[3]:
            return "force-out"
        return "field-out"
    if t == Ev.STRIKEOUT:
        if d.dp_flag:
            return "strikeout-double-play"
        if d.tp_flag:
            return "strikeout-triple-play"
        return "strikeout"
    if t == Ev.STOLENBASE:
        # MLBAM does not have any code for double-steal.  For now, emit the lead base stolen for
        # the event type.
        if d.sb_flag[3]:
            return "stolen-base-home"
        if d.sb_flag[2]:
            return "stolen-base-3b"
        return "stolen-base-2b"
    if t == Ev.INDIFFERENCE:
        return "defensive-indiff"
    if t == Ev.CAUGHTSTEALING:
        if d.dp_flag:
            return "cs-double-play"
        if d.cs_flag[1]:
            return "pickoff-caught-stealing-2b" if d.po_flag[1] else "caught-stealing-2b"
        if d.cs_flag[2]:
            return "pickoff-caught-stealing-3b" if d.po_flag[2] else "caught-stealing-3b"
        return "pickoff-caught-stealing-home" if d.po_flag[3] else "caught-stealing-home"
    # Note in the C: CW_EVENT_PICKOFFERROR is no longer used by Retrosheet
    if t == Ev.PICKOFF:
        if d.po_flag[1]:
            return "pickoff-caught-stealing-2b" if d.cs_flag[1] else "pickoff-1b"
        if d.po_flag[2]:
            return "pickoff-caught-stealing-3b" if d.cs_flag[2] else "pickoff-2b"
        return "pickoff-caught-stealing-home" if d.cs_flag[3] else "pickoff-3b"
    simple = {
        Ev.WILDPITCH: "wild-pitch",
        Ev.PASSEDBALL: "passed-ball",
        Ev.BALK: "balk",
        Ev.OTHERADVANCE: "other-advance",
        # does not appear in the MLBAM codes, but does appear in DiamondWare
        Ev.FOULERROR: "foul-error",
        Ev.WALK: "walk",
        Ev.INTENTIONALWALK: "intent-walk",
        Ev.HITBYPITCH: "hit-by-pitch",
        Ev.ERROR: "field-error",
        Ev.SINGLE: "single",
        Ev.DOUBLE: "double",
        Ev.TRIPLE: "triple",
        Ev.HOMERUN: "home-run",
    }
    if t in simple:
        return simple[Ev(t)]
    if t == Ev.INTERFERENCE:
        # Retrosheet uses the C notation for all interferences on which the batter is awarded
        # first base.  Most are catcher's interference C/E2, but some may be on other fielders.
        # Note the inconsistency in MLBAM's naming scheme here.
        return "catcher-interf" if d.errors[0] == 2 else "fielder-interference"
    if t == Ev.FIELDERSCHOICE:
        return "fielders-choice-out" if outs_on_play(d) > 0 else "fielders-choice"
    return "unknown-play"


def sml_get_hit_type(gi: GameIter) -> str:
    """``cwbox_sml_get_hit_type``"""
    d = gi.data
    kind = d.batted_ball_type
    if kind == "F":
        return "fly-ball"
    if kind == "G":
        return "bunt-grounder" if d.bunt_flag else "ground-ball"
    if kind == "L":
        return "bunt-line-drive" if d.bunt_flag else "line-drive"
    if kind == "P":
        return "bunt-popup" if d.bunt_flag else "popup"
    return ""


PITCH_TYPES = {
    "F": "fastball",
    "N": "sinker",
    "C": "curve",
    "R": "splitter",
    "S": "slider",
    "K": "knuckleball",
    "H": "changeup",
    "U": "unknown",
    "T": "cutter",
}


class _Cursor:
    """A ``char *`` into a C string: reading the terminating NUL gives ``"\\0"``, reading
    beyond it is undefined behaviour in C and raises ``ValueError`` here"""

    def __init__(self, text: str, pos: int) -> None:
        self.text = text
        self.pos = pos

    def ch(self) -> str:
        if self.pos < len(self.text):
            return self.text[self.pos]
        if self.pos == len(self.text):
            return "\0"
        raise ValueError("read past the end of a pitch record (undefined behaviour in C)")

    def until(self, *stops: str) -> str:
        """The ``while (*c != ...) buffer[i++] = *c++`` loop: the text up to a stop character"""
        start = self.pos
        while self.ch() not in stops:
            if self.ch() == "\0":
                raise ValueError("unterminated pitch record (undefined behaviour in C)")
            self.pos += 1
        return self.text[start : self.pos]


def print_sml_pitch(node: XMLNode, pitch: _Cursor) -> int:
    """``cwbox_print_sml_pitch``: the extended datum after a pitch character, if any. ``pitch`` is
    at the pitch character; returns the position the C returns, which the caller steps from."""
    c = _Cursor(pitch.text, pitch.pos + 1)
    if c.ch() != "{":
        return pitch.pos
    # This is an extended pitch datum
    c.pos += 1

    # First entry: pitch type, one character
    kind = c.ch()
    if kind in PITCH_TYPES:
        xml_node_attribute(node, "pitch-type", PITCH_TYPES[kind])
        c.pos += 1
    elif kind != "|":
        c.pos += 1

    # At this point, 'c' should be pointing at a '|'
    c.pos += 1

    # Next, pitch velocity
    if c.ch() != "|":
        xml_node_attribute(node, "pitch-velocity", c.until("|"))
    c.pos += 1

    # Next, pitch coordinate X
    if c.ch() != "|":
        xml_node_attribute(node, "pitch-coordinate-x", c.until("|"))
    c.pos += 1

    # Next, pitch coordinate Y
    if c.ch() != "|" and c.ch() != "}":
        xml_node_attribute(node, "pitch-coordinate-y", c.until("|", "}"))

    # At this point, 'c' should be pointing at a '|' or a '}'
    if c.ch() == "}":
        return c.pos

    # Start action-baseball-contact, which is a child of action-baseball-pitch
    contact = xml_node_open(node, "action-baseball-contact")

    # Hit coordinates X and Y follow
    c.pos += 1
    if c.ch() != "|":
        xml_node_attribute(contact, "hit-location-x", c.until("|"))
    c.pos += 1
    if c.ch() != "}":
        xml_node_attribute(contact, "hit-location-y", c.until("}"))
    return c.pos


def _advance(node: XMLNode, gi: GameIter, base: int, attr: str) -> None:
    """The ``advance[base]`` ladder of ``cwbox_action_baseball_play``"""
    d = gi.data
    if 1 <= d.advance[base] <= 3:
        xml_node_attribute_int(node, attr, d.advance[base])
    elif d.advance[base] >= 4:
        xml_node_attribute(node, attr, "home")
    elif d.play[base] != "" and "E" not in d.play[base]:
        xml_node_attribute(node, attr, "out")


PITCH_SKIPPED = ".>123+"

PITCH_CALLS = {
    "B": (("umpire-call", "ball"), ("ball-type", "called")),
    "C": (("umpire-call", "strike"), ("strike-type", "called")),
    "F": (("umpire-call", "strike"), ("strike-type", "foul")),
    "H": (("umpire-call", "ball"), ("ball-type", "hit-by-pitch")),
    "I": (("umpire-call", "ball"), ("ball-type", "intentional")),
    "K": (("umpire-call", "strike"), ("strike-type", "unknown")),
    "L": (("umpire-call", "strike"), ("strike-type", "foul-bunt")),
    "M": (("umpire-call", "strike"), ("strike-type", "missed-bunt")),
    "N": (("umpire-call", "no-pitch"),),
    "O": (("umpire-call", "strike"), ("strike-type", "foul-tip-on-bunt")),
    "P": (("umpire-call", "ball"), ("ball-type", "pitchout")),
    "Q": (("umpire-call", "strike"), ("strike-type", "swinging-on-pitchout")),
    "R": (("umpire-call", "strike"), ("strike-type", "foul-on-pitchout")),
    "S": (("umpire-call", "strike"), ("strike-type", "swinging")),
    "T": (("umpire-call", "strike"), ("strike-type", "foul-tip")),
    "U": (),
    "V": (("umpire-call", "ball"), ("ball-type", "automatic")),
    "X": (("umpire-call", "in-play"),),
    "Y": (("umpire-call", "in-play"),),
}


def action_baseball_play(
    parent: XMLNode,
    gi: GameIter,
    visitors: Roster | None,
    home: Roster | None,
    seq: int,
    new_pa: bool,
) -> None:
    """``cwbox_action_baseball_play``"""
    d = gi.data
    state = gi.state
    ev = _deref(gi.event)
    node = xml_node_open(
        parent, "action-baseball-score" if runs_on_play(d) > 0 else "action-baseball-play"
    )

    xml_node_attribute_int(node, "sequence-number", seq)
    xml_node_attribute_int(node, "inning-value", state.inning)
    top, bottom = ("bottom", "top") if _htbf(gi.game) else ("top", "bottom")
    xml_node_attribute(node, "inning-half", top if state.batting_team == 0 else bottom)
    xml_node_attribute_int(node, "outs", state.outs)

    _advance(node, gi, 0, "batter-advance")
    for base, name in ((1, "first"), (2, "second"), (3, "third")):
        if state.base_occupied(base):
            xml_node_attribute_fmt(
                node, f"runner-on-{name}-idref", f"p.{_s(state.runners[base].runner)}"
            )
            _advance(node, gi, base, f"runner-on-{name}-advance")

    # ASSUMPTION in the C: batter-idref and pitcher-idref refer to the charged batter and
    # pitcher, which might not be the ones who took the final action!
    xml_node_attribute_fmt(node, "pitcher-idref", f"p.{_s(state.charged_pitcher(d))}")
    xml_node_attribute_fmt(node, "batter-idref", f"p.{state.charged_batter(ev.batter, d)}")

    bat_hand = state.charged_batter_hand(
        ev.batter,
        d,
        visitors if state.batting_team == 0 else home,
        home if state.batting_team == 0 else visitors,
    )
    # Note that bat_hand might be '?', unknown
    if bat_hand == "R":
        xml_node_attribute(node, "batter-side", "right")
    elif bat_hand == "L":
        xml_node_attribute(node, "batter-side", "left")

    xml_node_attribute(node, "play-type", sml_get_play_type(gi))
    hit_type = sml_get_hit_type(gi)
    if hit_type != "":
        xml_node_attribute(node, "hit-type", hit_type)

    xml_node_attribute(node, "play-scorekeepers-notation", ev.event_text)
    xml_node_attribute_int(node, "outs-recorded", outs_on_play(d))

    if runs_on_play(d) > 0:
        xml_node_attribute_int(node, "rbi", rbi_on_play(d))
        xml_node_attribute_int(node, "runs-scored", runs_on_play(d))
        # FIXME in the C: Is earned-runs-scored team or individually earned?
        earned = sum(d.advance[b] == 4 for b in range(4))
        xml_node_attribute_int(node, "earned-runs-scored", earned)
        xml_node_attribute_int(
            node, "score-team", state.score[state.batting_team] + runs_on_play(d)
        )
        xml_node_attribute_int(node, "score-team-opposing", state.score[1 - state.batting_team])

    # Pitches here. Earlier versions of the C checked for whether the "info,pitches" field read
    # "pitches." However, some files aren't marked as having pitches, but do have pitches for
    # some plate appearances; and, some are marked as having pitches, but clearly only have
    # incomplete pitch data. So, the C ignores the info,pitches field, and simply reports what
    # the event file has.
    pitches = ev.pitches
    start = 0
    if not new_pa:
        # Skip pitches in previous event
        if gi.index == 0:
            raise ValueError("no previous event (NULL dereference in Chadwick)")
        # the C skips past the end when the previous string is longer; the port stops there
        start = min(len(gi.game.events[gi.index - 1].pitches), len(pitches))
    c = start
    while c < len(pitches):
        ch = pitches[c]
        if ch in PITCH_SKIPPED:
            c += 1
            continue
        pitch = xml_node_open(node, "action-baseball-pitch")
        if ch in PITCH_CALLS:
            for attr, value in PITCH_CALLS[ch]:
                xml_node_attribute(pitch, attr, value)
        elif ch == "*":
            c += 1
            after = pitches[c] if c < len(pitches) else "\0"
            if after == "B":
                xml_node_attribute(pitch, "umpire-call", "ball")
                xml_node_attribute(pitch, "ball-type", "blocked")
            elif after == "S":
                xml_node_attribute(pitch, "umpire-call", "strike")
                xml_node_attribute(pitch, "strike-type", "swinging-blocked")
        c = print_sml_pitch(pitch, _Cursor(pitches, c))
        c += 1


def _position_name(node: XMLNode, attr: str, position: int) -> None:
    if position == 10:
        xml_node_attribute(node, attr, "dh")
    elif position == 11:
        xml_node_attribute(node, attr, "ph")
    elif position == 12:
        xml_node_attribute(node, attr, "pr")
    else:
        xml_node_attribute_int(node, attr, position)


def action_baseball_substitution(parent: XMLNode, gi: GameIter, sub: Appearance, seq: int) -> None:
    """``cwbox_action_baseball_substitution``

    Semantic note in the C: Retrosheet files do not contain an additional substitution for a
    player who PH or PRs for a DH to indicate that they automatically become the DH.
    """
    state = gi.state
    node = xml_node_open(parent, "action-baseball-substitution")
    xml_node_attribute_int(node, "sequence-number", seq)
    xml_node_attribute_int(node, "inning-value", state.inning)
    top, bottom = ("bottom", "top") if _htbf(gi.game) else ("top", "bottom")
    xml_node_attribute(node, "inning-half", top if state.batting_team == 0 else bottom)
    xml_node_attribute_int(node, "outs", state.outs)
    xml_node_attribute(node, "person-type", "player")

    original = state.lineups[sub.slot][sub.team]
    xml_node_attribute_fmt(node, "person-original-idref", f"p.{_s(original.player_id)}")
    _position_name(node, "person-original-position", original.position)

    pitcher_slot = state.lineups[0][sub.team].player_id
    if sub.slot > 0 and pitcher_slot is not None and pitcher_slot == sub.player_id:
        # This is a case of the pitcher assuming a lineup slot
        xml_node_attribute(node, "person-original-lineup-slot", "0")
    else:
        xml_node_attribute_int(node, "person-original-lineup-slot", sub.slot)
    xml_node_attribute_fmt(node, "person-replacing-idref", f"p.{sub.player_id}")

    if original.position == 10 and state.batting_team == sub.team:
        # Convention in the C: when pinch-hitting or pinch-running for the DH, report new
        # position as DH
        xml_node_attribute(node, "person-replacing-position", "dh")
    else:
        _position_name(node, "person-replacing-position", sub.pos)
    xml_node_attribute_int(node, "person-replacing-lineup-slot", sub.slot)


def actions(parent: XMLNode, game: Game, visitors: Roster | None, home: Roster | None) -> None:
    """``cwbox_actions``: ``<event-actions>``, with all play-by-play actions"""
    gi = GameIter(game)
    seq = 1
    new_pa = True  # true if the current event starts a new PA

    action_node = xml_node_open(parent, "event-actions")
    node = xml_node_open(action_node, "event-actions-baseball")

    while gi.event is not None:
        ev = gi.event
        if not gi.parse_ok:
            raise ValueError(
                f"Parse error in game {game.game_id} at event {gi.state.event_count + 1}: "
                f'invalid play string "{ev.event_text}" ({ev.batter} batting); Chadwick exits'
            )
        if ev.event_text != "NP":
            action_baseball_play(node, gi, visitors, home, seq, new_pa)
            seq += 1
            new_pa = is_batter(gi.data) or gi.state.outs + outs_on_play(gi.data) >= 3
        for sub in ev.subs:
            action_baseball_substitution(node, gi, sub, seq)
            seq += 1
        gi.next()


def site(parent: XMLNode, game: Game) -> None:
    """``cwbox_site``: a ``<site>`` element"""
    site_node = xml_node_open(parent, "site")
    metadata = xml_node_open(site_node, "site-metadata")
    site_key = _info(game, "site")
    if site_key is not None:
        # Retrosheet convention is that the 'site' entry is a code
        xml_node_attribute(metadata, "site-key", site_key)
    site_name = _info(game, "site-name")
    if site_name is not None:
        # Extension: use info,site-name to embed the site's name in files
        name_node = xml_node_open(metadata, "name")
        xml_node_attribute(name_node, "full", site_name)
    xml_node_open(metadata, "home-location")

    stats = xml_node_open(site_node, "site-stats")
    attendance = _info(game, "attendance")
    if attendance is not None:
        xml_node_attribute(stats, "attendance", attendance)


def event_metadata(parent: XMLNode, game: Game) -> None:
    """``cwbox_event_metadata``: an ``<event-metadata>`` element"""
    season = _season(game)
    node = xml_node_open(parent, "event-metadata")
    xml_node_attribute(node, "date-coverage-type", "event")
    xml_node_attribute_fmt(node, "event-key", f"l.mlb.com-{season}-e.{game.game_id}")
    # date-coverage-value is in fact same as event-key
    xml_node_attribute_fmt(node, "date-coverage-value", f"l.mlb.com-{season}-e.{game.game_id}")
    date = _date(game)
    xml_node_attribute_fmt(
        node,
        "start-date-time",
        f"{date[0:4]}{date[5:7]}{date[8:10]}T000000-0000",
    )
    xml_node_attribute(node, "event-status", "post-event")

    time_of_game = _info(game, "timeofgame")
    if time_of_game is not None:
        found = scan_int(time_of_game, 0)
        if found is None:
            if time_of_game == "":
                raise ValueError("empty timeofgame (uninitialised value in Chadwick)")
        elif found[0] > 0:
            minutes = found[0]
            xml_node_attribute_fmt(
                node, "duration", f"{_cdiv(minutes, 60)}:{_cmod(minutes, 60):02d}"
            )

    number = _deref(_info(game, "number"))
    xml_node_attribute_int(node, "game-of-day", 1 if cw_atoi(number) == 0 else cw_atoi(number))

    if _htbf(game):
        xml_node_attribute(node, "site-alignment", "away")

    # For the moment, <event-metadata-baseball> is empty, so the C just creates it here rather
    # than using a separate function.
    xml_node_open(node, "event-metadata-baseball")
    site(node, game)


def sports_event(
    parent: XMLNode, game: Game, box: Boxscore, visitors: Roster | None, home: Roster | None
) -> None:
    """``cwbox_sports_event``: a ``<sports-event>`` element"""
    node = xml_node_open(parent, "sports-event")
    event_metadata(node, game)
    team(node, game, box, 0, visitors)
    team(node, game, box, 1, home)
    officials(node, game)
    actions(node, game, visitors, home)


def sports_title(parent: XMLNode, game: Game, visitors: Roster | None, home: Roster | None) -> None:
    """``cwbox_sports_title``: a ``<sports-title>`` element"""
    node = xml_node_open(parent, "sports-title")
    season = _season(game)
    date = _date(game)
    text = (
        f"{visitors.city if visitors else ''} {visitors.nickname if visitors else ''} at "
        f"{home.city if home else ''} {home.nickname if home else ''}, "
        f"{date[5]}{date[6]}/{date[8]}{date[9]}/{season}"
    )
    xml_node_cdata(node, text)


def sports_content_codes(
    parent: XMLNode, game: Game, visitors: Roster | None, home: Roster | None
) -> None:
    """``cwbox_sports_content_codes``: ``<sports-content-codes>`` and its children

    TODO in the C: more/all of these should be configurable in the data structure, like with
    "publisher".
    """
    _season(game)  # the C copies the season first, which crashes without a date
    codes = xml_node_open(parent, "sports-content-codes")

    node = xml_node_open(codes, "sports-content-code")
    publisher = _info(game, "publisher")
    if publisher is not None:
        xml_node_attribute(node, "code-name", publisher)
        xml_node_attribute(node, "code-key", _s(_info(game, "publisher-key")))
        xml_node_attribute(node, "code-type", "publisher")
    else:
        xml_node_attribute(node, "code-name", "Retrosheet")
        xml_node_attribute(node, "code-key", "retrosheet.org")
        xml_node_attribute(node, "code-type", "publisher")

    node = xml_node_open(codes, "sports-content-code")
    xml_node_attribute(node, "code-name", "XML Team Solutions, Inc.")
    xml_node_attribute(node, "code-key", "xmlteam.com")
    xml_node_attribute(node, "code-type", "distributor")

    node = xml_node_open(codes, "sports-content-code")
    xml_node_attribute(node, "code-type", "sport")
    xml_node_attribute(node, "code-key", "15007000")
    xml_node_attribute(node, "code-name", "Baseball")

    node = xml_node_open(codes, "sports-content-code")
    xml_node_attribute(node, "code-type", "league")
    league = _info(game, "league")
    xml_node_attribute(node, "code-name", league if league is not None else "Major League Baseball")
    league_key = _info(game, "league-key")
    xml_node_attribute(node, "code-key", league_key if league_key is not None else "l.mlb.com")

    level = _info(game, "level")
    if level is not None:
        node = xml_node_open(codes, "sports-content-code")
        xml_node_attribute(node, "code-type", "level")
        xml_node_attribute(node, "code-key", level)

    node = xml_node_open(codes, "sports-content-code")
    xml_node_attribute(node, "code-type", "season-type")
    season_type = _info(game, "season-type")
    xml_node_attribute(node, "code-key", season_type if season_type is not None else "regular")

    node = xml_node_open(codes, "sports-content-code")
    xml_node_attribute(node, "code-type", "season")
    season = _info(game, "season")
    xml_node_attribute(node, "code-key", season if season is not None else _season(game))

    node = xml_node_open(codes, "sports-content-code")
    xml_node_attribute(node, "code-type", "priority")
    xml_node_attribute(node, "code-key", "normal")

    if visitors is not None:
        node = xml_node_open(codes, "sports-content-code")
        xml_node_attribute(node, "code-type", "team")
        xml_node_attribute(node, "code-key", visitors.team_id)
        xml_node_attribute_fmt(node, "code-name", f"{visitors.city} {visitors.nickname}")

    if home is not None:
        node = xml_node_open(codes, "sports-content-code")
        xml_node_attribute(node, "code-type", "team")
        xml_node_attribute(node, "code-key", home.team_id)
        xml_node_attribute_fmt(node, "code-name", f"{home.city} {home.nickname}")

    node = xml_node_open(codes, "sports-content-code")
    xml_node_attribute(node, "code-type", "action-listing")
    xml_node_attribute(node, "code-key", "complete")


def _now_stamp() -> str:
    """``strftime(..., "%Y%m%dT%H%M%S", localtime(&t))`` followed by ``"%+03ld%02ld"`` of the
    GMT offset in hours and the remainder in seconds (sic), as the C writes it"""
    now = time.localtime()
    offset = now.tm_gmtoff or 0
    return (
        f"{time.strftime('%Y%m%dT%H%M%S', now)}{_cdiv(offset, 3600):+03d}{_cmod(offset, 3600):02d}"
    )


def sports_metadata(
    parent: XMLNode, game: Game, visitors: Roster | None, home: Roster | None
) -> None:
    """``cwbox_sports_metadata``: a ``<sports-metadata>`` element"""
    node = xml_node_open(parent, "sports-metadata")
    xml_node_attribute(node, "language", "en-US")
    xml_node_attribute(node, "date-time", _now_stamp())
    xml_node_attribute(node, "doc-id", f"Retrosheet.{game.game_id}.box")
    xml_node_attribute(
        node, "revision-id", f"l.mlb.com-{_season(game)}-e.{game.game_id}-event-stats"
    )
    xml_node_attribute(node, "fixture-key", "event-stats")
    xml_node_attribute(node, "document-class", "event-summary")
    xml_node_attribute(node, "fixture-name", "Box Score")
    sports_title(node, game, visitors, home)
    sports_content_codes(node, game, visitors, home)


def print_sportsml(
    doc: XMLDoc | None,
    game: Game,
    box: Boxscore,
    visitors: Roster | None,
    home: Roster | None,
) -> str:
    """``cwbox_print_sportsml``: one game as a ``<sports-content>`` element of ``doc`` (the
    ``sports-content-set`` of ``cwbox -S``); without a document, a complete document of its own.
    Returns the text written."""
    own = doc is None
    if doc is None:
        doc = XMLDoc("sports-content")
        node = doc.root
    else:
        node = xml_node_open(doc.root, "sports-content")
    xml_node_attribute(node, "xmlns:xts", "http://www.xmlteam.com")
    xml_node_attribute(node, "xts:systemid", "MLB_Boxscore_XML")

    sports_metadata(node, game, visitors, home)
    sports_event(node, game, box, visitors, home)

    if own:
        xml_document_cleanup(doc)
    return doc.take()
