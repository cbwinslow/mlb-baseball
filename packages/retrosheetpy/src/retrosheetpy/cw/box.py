"""Port of Chadwick's boxscore builder (``src/cwlib/box.c`` and ``box.h``).

Chadwick is Copyright (c) 2002-2023 Dr T L Turocy and the Chadwick Baseball
Bureau, licensed GPL-2.0-or-later; this module is a derivative of it and keeps
that notice. Names map onto the C functions (``cw_box_x`` -> ``x``) so the two
can be read side by side.

Data layout follows ``box.h``. Players and pitchers stay doubly linked
(``slots[slot][team]`` and ``pitchers[team]`` point at the *current* entry; walk
``prev`` for earlier ones), because Chadwick's tools walk them that way. The
notable-event lists (``b2_list`` ...) are plain Python lists in file order
instead of linked lists. Unset C pointers are ``None``.

Where the C ends the program (``exit(1)``) or dereferences ``NULL``, this port
raises ``ValueError``; messages Chadwick prints to stderr go to ``logging``.
"""

import logging
from dataclasses import dataclass, field
from typing import TypeVar

from retrosheetpy.cw.file import cw_atoi
from retrosheetpy.cw.game import Game, pitch_ball_thrown, pitch_strike_thrown
from retrosheetpy.cw.gameiter import GameIter
from retrosheetpy.cw.parse import (
    Ev,
    is_batter,
    is_official_ab,
    outs_on_play,
    rbi_on_play,
    runs_on_play,
)

log = logging.getLogger("retrosheetpy.cw")

_T = TypeVar("_T")

LINESCORE_INNINGS = 50
NUM_POSITIONS = 40
EVENT_PLAYERS = 20


def _deref(value: _T | None) -> _T:
    """A C ``NULL`` dereference: Chadwick would crash here."""
    if value is None:
        raise ValueError("Chadwick would dereference NULL here")
    return value


def _c0(text: str) -> int:
    """``text[0]`` as a C ``char`` (the terminating NUL of an empty string is 0)."""
    return ord(text[0]) if text else 0


@dataclass
class BoxBatting:
    """``CWBoxBatting``"""

    g: int = 0
    pa: int = 0
    ab: int = 0
    r: int = 0
    h: int = 0
    b2: int = 0
    b3: int = 0
    hr: int = 0
    hrslam: int = 0
    bi: int = 0
    bi2out: int = 0
    gw: int = -1  # GWRBI defaults to NULL instead of zero
    bb: int = 0
    ibb: int = 0
    so: int = 0
    gdp: int = 0
    hp: int = 0
    sh: int = 0
    sf: int = 0
    sb: int = 0
    cs: int = 0
    xi: int = 0
    lisp: int = 0
    movedup: int = 0
    pitches: int = 0
    strikes: int = 0


@dataclass
class BoxFielding:
    """``CWBoxFielding``"""

    g: int = 0
    outs: int = 0
    bip: int = 0
    bf: int = 0
    po: int = 0
    a: int = 0
    e: int = 0
    dp: int = 0
    tp: int = 0
    pb: int = 0
    xi: int = 0


@dataclass
class BoxPitching:
    """``CWBoxPitching``"""

    g: int = 0
    gs: int = 0
    cg: int = 0
    sho: int = 0
    gf: int = 0
    outs: int = 0
    ab: int = 0
    r: int = 0
    er: int = 0
    h: int = 0
    b2: int = 0
    b3: int = 0
    hr: int = 0
    hrslam: int = 0
    bb: int = 0
    ibb: int = 0
    so: int = 0
    bf: int = 0
    bk: int = 0
    wp: int = 0
    hb: int = 0
    gdp: int = 0
    sh: int = 0
    sf: int = 0
    xi: int = 0
    pk: int = 0
    w: int = 0
    l: int = 0  # noqa: E741  (C field name)
    sv: int = 0
    inr: int = 0  # inherited runners
    inrs: int = 0  # inherited runners scored, even if relieved before they scored
    xb: int = 0  # extra batters: batters faced in an inning without getting an out
    xbinn: int = 0
    gb: int = 0
    fb: int = 0
    pitches: int = 0
    strikes: int = 0


class BoxPlayer:
    """``CWBoxPlayer``: a player's entry in the boxscore."""

    def __init__(self, player_id: str, name: str) -> None:
        """``cw_box_player_create``"""
        self.player_id = player_id
        self.name = name
        self.date = ""  # the appearance date, taking resumed games into account
        self.batting = BoxBatting()
        self.ph_inn = self.pr_inn = self.num_positions = 0
        self.start_position = -1  # position in the starting lineup; -1 if not a starter
        self.positions = [0] * NUM_POSITIONS
        self.fielding: list[BoxFielding | None] = [None] * 10
        self.prev: BoxPlayer | None = None
        self.next: BoxPlayer | None = None

    def add_position(self, pos: int) -> None:
        """``positions[num_positions++] = pos`` (the C array has 40 entries and no check)"""
        if self.num_positions >= len(self.positions):
            self.positions.extend([0] * (self.num_positions + 1 - len(self.positions)))
        self.positions[self.num_positions] = pos
        self.num_positions += 1


class BoxPitcher:
    """``CWBoxPitcher``: a pitcher's entry in the boxscore."""

    def __init__(self, player_id: str, name: str) -> None:
        """``cw_box_pitcher_create``"""
        self.player_id = player_id
        self.name = name
        self.pitching = BoxPitching()
        self.prev: BoxPitcher | None = None
        self.next: BoxPitcher | None = None


@dataclass
class BoxEvent:
    """``CWBoxEvent``: a notable event (extra-base hit, wild pitch, ...)."""

    players: list[str | None] = field(default_factory=lambda: [None] * EVENT_PLAYERS)
    inning: int = 0
    half_inning: int = 0
    runners: int = -1
    pickoff: int = -1
    outs: int = -1
    mark: int = 0
    location: str = ""


def add_event(events: list[BoxEvent], inning: int, half: int, *players: str) -> BoxEvent:
    """``cw_box_add_event``: ``players`` are the ``count`` strings of its variable arguments."""
    event = BoxEvent(inning=inning, half_inning=half)
    for i, p in enumerate(players):
        event.players[i] = p
    events.append(event)
    return event


def _set_player(event: BoxEvent, i: int, player_id: str) -> None:
    """``event->players[i] = ...`` (a C array of 20 pointers, no bound check)"""
    if i >= len(event.players):
        event.players.extend([None] * (i + 1 - len(event.players)))
    event.players[i] = player_id


def _item_int(stat: tuple[str | None, ...], index: int) -> int:
    """``cw_data_get_item_int``"""
    if index >= len(stat):
        return -1
    text = stat[index]
    assert text is not None  # only the reader's sentinel can be None, and it never gets stored
    return cw_atoi(text)


def _slot_team(slot: int, team: int) -> None:
    """The C indexes ``slots[slot][team]`` unchecked; bad values are undefined behaviour."""
    if not 0 <= slot <= 9 or not 0 <= team <= 1:
        raise ValueError(f"slot {slot} / team {team} out of range (undefined behaviour in C)")


class Boxscore:
    """``CWBoxscore``"""

    def __init__(self) -> None:
        self.slots: list[list[BoxPlayer | None]] = [[None, None] for _ in range(10)]
        self.pitchers: list[BoxPitcher | None] = [None, None]
        self.linescore: list[list[int]] = [[-1, -1] for _ in range(LINESCORE_INNINGS)]
        self.score = [0, 0]
        self.hits = [0, 0]
        self.errors = [0, 0]
        self.dp = [0, 0]
        self.tp = [0, 0]
        self.lob = [0, 0]
        self.er = [0, 0]
        self.risp_ab = [0, 0]
        self.risp_h = [0, 0]
        # How many outs there were when the game ended; if not 3, the game was called in the
        # middle of an inning or ended on a walk-off event (``walk_off`` is 1 then).
        self.outs_at_end = 0
        self.walk_off = 0
        self.b2_list: list[BoxEvent] = []
        self.b3_list: list[BoxEvent] = []
        self.hr_list: list[BoxEvent] = []
        self.sb_list: list[BoxEvent] = []
        self.cs_list: list[BoxEvent] = []
        self.po_list: list[BoxEvent] = []
        self.sh_list: list[BoxEvent] = []
        self.sf_list: list[BoxEvent] = []
        self.hp_list: list[BoxEvent] = []
        self.ibb_list: list[BoxEvent] = []
        self.wp_list: list[BoxEvent] = []
        self.bk_list: list[BoxEvent] = []
        self.err_list: list[BoxEvent] = []
        self.pb_list: list[BoxEvent] = []
        self.dp_list: list[BoxEvent] = []
        self.tp_list: list[BoxEvent] = []

    def _inning_row(self, inning: int) -> list[int]:
        """``linescore[inning]`` (the C array has 50 rows and no bound check)"""
        if inning < 0:
            raise ValueError(f"inning {inning} out of range (undefined behaviour in C)")
        while inning >= len(self.linescore):
            self.linescore.append([-1, -1])
        return self.linescore[inning]


def _date8(date: str | None) -> str:
    """``date[0..3] date[5..6] date[8..9]`` of the ``date`` info record (``YYYY/MM/DD``)

    The C only reads ``date`` when it enters a player, so a missing record is fine until then.
    """
    date = _deref(date)
    return date[0:4] + date[5:7] + date[8:10]


def enter_starters(box: Boxscore, game: Game) -> None:
    """``cw_box_enter_starters``: initialize slots with starting players"""
    date = game.info_lookup("date")
    for t in (0, 1):
        for i in range(10):
            app = game.starter_find(t, i)
            if app is None:
                continue

            player = BoxPlayer(app.player_id, app.name)
            box.slots[i][t] = player
            player.date = _date8(date)
            player.batting.g = 1
            player.num_positions += 1
            player.positions[0] = app.pos
            player.start_position = app.pos
            if app.pos < 10:
                if app.pos < 0:
                    raise ValueError("negative starting position (undefined behaviour in C)")
                # Under modern rules, players only receive credit for a game in the field when
                # they appear there for at least one event, so fielding.g stays 0 here.
                player.fielding[app.pos] = BoxFielding()
            if app.pos == 1:
                pitcher = BoxPitcher(app.player_id, app.name)
                pitcher.pitching.g = 1
                pitcher.pitching.gs = 1
                box.pitchers[t] = pitcher


def add_substitute(box: Boxscore, gi: GameIter) -> None:
    """``cw_box_add_substitute``: add a substitute into a slot"""
    event = _deref(gi.event)
    state = gi.state
    for sub in event.subs:
        if sub.slot < 0 or sub.slot > 9:
            msg = (
                f"ERROR: In {gi.game.game_id}, invalid slot {sub.slot} "
                f"for player '{sub.player_id}'."
            )
            log.error(msg)
            raise ValueError(msg)
        if sub.team < 0 or sub.team > 1:
            msg = (
                f"ERROR: In {gi.game.game_id}, invalid team {sub.team} "
                f"for player '{sub.player_id}'."
            )
            log.error(msg)
            raise ValueError(msg)
        if sub.pos < 1 or sub.pos > 12:
            msg = (
                f"ERROR: In {gi.game.game_id}, invalid position {sub.pos} "
                f"for player '{sub.player_id}'."
            )
            log.error(msg)
            raise ValueError(msg)

        current = box.slots[sub.slot][sub.team]
        slot0 = box.slots[0][sub.team]
        if current is None:
            # This should never happen; however, there do exist Retrosheet files with bogus
            # substitution entries, including ones which sub players into the 0 slot even though
            # the DH is not in use. Try to do something reasonable here.
            player = BoxPlayer(sub.player_id, sub.name)
            player.date = state.date[:8]
            player.batting.g = 1
            box.slots[sub.slot][sub.team] = player
        elif sub.slot != 0 and slot0 is not None and slot0.player_id == sub.player_id:
            # With the DH in use, a pitcher assumes a field position (and therefore a batting
            # order slot)
            player = slot0

            # Remove player from special slot zero
            if player.prev is not None:
                box.slots[0][sub.team] = player.prev
                player.prev.next = None
                player.prev = None
            else:
                box.slots[0][sub.team] = None

            # Put player in his new slot
            current.next = player
            player.prev = current
            box.slots[sub.slot][sub.team] = player
        elif sub.player_id != current.player_id:
            player = BoxPlayer(sub.player_id, sub.name)
            player.date = state.date[:8]
            player.batting.g = 1
            current.next = player
            player.prev = current
            box.slots[sub.slot][sub.team] = player

            if sub.pos == 11:
                player.ph_inn = state.inning
            elif sub.pos == 12:
                player.pr_inn = state.inning

        entry = _deref(box.slots[sub.slot][sub.team])
        if sub.pos < 10 and entry.fielding[sub.pos] is None:
            # The mere announcement of a player at a position does not award him a game played
            # at the position (under modern rules); the game is set when processing fielding
            # credits for events.
            entry.fielding[sub.pos] = BoxFielding()

        entry.add_position(sub.pos)
        if sub.pos >= 11 and sub.slot == state.dh_slot[sub.team]:
            # Entering as a PH or PR for a DH automatically makes the player the DH.
            entry.add_position(10)

        # Guard against possibility of pitcher being subbed into batting order slot when a team
        # loses the DH -- don't want to create a pitcher record for this!
        if sub.pos == 1 and sub.player_id != _deref(box.pitchers[sub.team]).player_id:
            cur = _deref(box.pitchers[sub.team])
            cur_pitcher = cur.pitching
            if state.outs == 0 and state.inning_batters > 0:
                cur_pitcher.xb = min(cur_pitcher.bf, state.inning_batters)
                cur_pitcher.xbinn = state.inning
            elif cur_pitcher.outs == 0:
                cur_pitcher.xb = cur_pitcher.bf
                cur_pitcher.xbinn = state.inning

            pitcher = BoxPitcher(sub.player_id, sub.name)
            pitcher.pitching.g = 1
            cur.next = pitcher
            pitcher.prev = cur
            box.pitchers[sub.team] = pitcher

        if sub.pos == 1:
            pitching = _deref(box.pitchers[sub.team]).pitching
            for base in (1, 2, 3):
                if state.base_occupied(base):
                    pitching.inr += 1
                    if gi.runner_fate(base) >= 4:
                        pitching.inrs += 1


def find_player(box: Boxscore, player_id: str | None, batter: bool) -> BoxPlayer | None:
    """``cw_box_find_player``

    If ``batter``, search only batting entries; this implements the 'Ohtani rule' for DHes, in
    which a player who DHes for himself has two identities within the game, one in the batting
    order and one as the DHed-for pitcher.
    """
    if player_id is None:
        return None
    for t in (0, 1):
        for i in range(1 if batter else 0, 10):
            player = box.slots[i][t]
            while player is not None:
                if player.player_id == player_id:
                    return player
                player = player.prev
    return None


def find_current_player(
    box: Boxscore, player_id: str | None, batting_only: bool
) -> BoxPlayer | None:
    """``cw_box_find_current_player``

    Unlike ``find_player`` this only searches, and returns, entries from among players currently
    in the game. That matters when building the boxscore, in the case of an illegal (or
    sanctioned but unorthodox) re-entry of a player in a different lineup slot.
    """
    if player_id is None:
        return None
    for t in (0, 1):
        for i in range(1 if batting_only else 0, 10):
            player = box.slots[i][t]
            if player is not None and player.player_id == player_id:
                return player
    return None


def find_pitcher(box: Boxscore, player_id: str | None) -> BoxPitcher | None:
    """``cw_box_find_pitcher`` (``strcmp`` against ``NULL`` is undefined; it never matches here)"""
    for t in (0, 1):
        pitcher = box.pitchers[t]
        while pitcher is not None and pitcher.player_id != player_id:
            pitcher = pitcher.prev
        if pitcher is not None:
            return pitcher
    return None


def _log_play(gi: GameIter) -> None:
    ev = _deref(gi.event)
    log.error("      (Batter ID '%s', event text '%s')", ev.batter, ev.event_text)
    log.error("      Skipping statistics tabulation for this play.")


def pitch_stats(box: Boxscore, gi: GameIter) -> None:
    """``cw_box_pitch_stats``: update pitch stats with the current event

    Called even for NP events, as pitches may occur prior to a substitution. Only counts pitches
    following the last period in the pitch string.
    """
    ev = _deref(gi.event)
    state = gi.state
    if ev.pitches == "":
        return
    player = find_current_player(box, ev.batter, False)
    if player is None:
        log.error(
            "ERROR: In %s, no entry for batter at event %d.", gi.game.game_id, state.event_count
        )
        log.error("      (Batter ID '%s', event text '%s')", ev.batter, ev.event_text)
        log.error("      Skipping pitches tabulation for this play.")
        return
    pitcher = box.pitchers[1 - state.batting_team]
    if pitcher is None:
        side = "home" if state.batting_team == 0 else "visiting"
        log.error("ERROR: In %s, no pitcher in lineup for %s team.", gi.game.game_id, side)
        return

    # start from the first pitch after the last period
    for ch in ev.pitches[ev.pitches.rfind(".") + 1 :]:
        if pitch_ball_thrown(ch):
            player.batting.pitches += 1
            pitcher.pitching.pitches += 1
        elif pitch_strike_thrown(ch):
            player.batting.pitches += 1
            player.batting.strikes += 1
            pitcher.pitching.pitches += 1
            pitcher.pitching.strikes += 1


def batter_stats(box: Boxscore, gi: GameIter) -> None:  # noqa: C901, PLR0912, PLR0915
    """``cw_box_batter_stats``: update batter/pitcher stats with the current play"""
    d = gi.data
    ev = _deref(gi.event)
    state = gi.state
    bt = state.batting_team
    inning = state.inning
    charged_batter = state.charged_batter(ev.batter, d)

    player = find_player(box, charged_batter, True)
    if is_batter(d) and player is None:
        # If not a batter event, we will be tolerant if the player ID in the batter field is bogus.
        log.error(
            "ERROR: In %s, no entry for batter '%s' at event %d.",
            gi.game.game_id,
            charged_batter,
            state.event_count,
        )
        _log_play(gi)
        return

    pitcher = box.pitchers[1 - bt]
    if pitcher is None:
        side = "home" if bt == 0 else "visiting"
        msg = f"ERROR: In {gi.game.game_id}, no pitcher in lineup for {side} team."
        log.error(msg)
        raise ValueError(msg)

    charged_pitcher = state.charged_pitcher(d)
    res_pitcher: BoxPitcher | None = pitcher
    while res_pitcher is not None and res_pitcher.player_id != charged_pitcher:
        res_pitcher = res_pitcher.prev
    if res_pitcher is None:
        log.warning(
            "WARNING: In %s, no entry for charged pitcher '%s' at event %d.",
            gi.game.game_id,
            charged_pitcher,
            state.event_count,
        )
        _log_play(gi)
        return

    if is_batter(d):
        batting = _deref(player).batting
        batting.pa += 1
        res_pitcher.pitching.bf += 1
    res_pitcher.pitching.outs += outs_on_play(d)

    if is_official_ab(d):
        batting = _deref(player).batting
        batting.ab += 1
        res_pitcher.pitching.ab += 1

        if state.base_occupied(2) or state.base_occupied(3):
            box.risp_ab[bt] += 1

        if Ev.SINGLE <= d.event_type <= Ev.HOMERUN:
            batting.h += 1
            res_pitcher.pitching.h += 1
            if state.base_occupied(2) or state.base_occupied(3):
                box.risp_h[bt] += 1

            who_id = _deref(player).player_id
            if d.event_type == Ev.DOUBLE:
                add_event(box.b2_list, inning, bt, who_id, res_pitcher.player_id)
                batting.b2 += 1
                res_pitcher.pitching.b2 += 1
            elif d.event_type == Ev.TRIPLE:
                add_event(box.b3_list, inning, bt, who_id, res_pitcher.player_id)
                batting.b3 += 1
                res_pitcher.pitching.b3 += 1
            elif d.event_type == Ev.HOMERUN:
                event = add_event(box.hr_list, inning, bt, who_id, res_pitcher.player_id)
                event.runners = runs_on_play(d)
                event.outs = state.outs
                event.location = d.hit_location
                batting.hr += 1
                res_pitcher.pitching.hr += 1
                if rbi_on_play(d) == 4:
                    batting.hrslam += 1
                    res_pitcher.pitching.hrslam += 1
        elif d.event_type == Ev.STRIKEOUT:
            batting.so += 1
            res_pitcher.pitching.so += 1
        elif d.gdp_flag:
            batting.gdp += 1
            res_pitcher.pitching.gdp += 1

    elif d.event_type in (Ev.WALK, Ev.INTENTIONALWALK):
        who = _deref(player)
        who.batting.bb += 1
        res_pitcher.pitching.bb += 1
        if d.event_type == Ev.INTENTIONALWALK:
            who.batting.ibb += 1
            res_pitcher.pitching.ibb += 1
            add_event(box.ibb_list, inning, bt, who.player_id, res_pitcher.player_id)
    elif d.event_type == Ev.HITBYPITCH:
        who = _deref(player)
        who.batting.hp += 1
        res_pitcher.pitching.hb += 1
        add_event(box.hp_list, inning, bt, who.player_id, res_pitcher.player_id)
    elif d.event_type == Ev.BALK:
        res_pitcher.pitching.bk += 1
        add_event(box.bk_list, inning, bt, res_pitcher.player_id)
    elif d.event_type == Ev.INTERFERENCE:
        _deref(player).batting.xi += 1
        res_pitcher.pitching.xi += 1

    if d.event_type == Ev.GENERICOUT and not d.bunt_flag:
        if d.batted_ball_type == "G":
            res_pitcher.pitching.gb += 1
        elif d.batted_ball_type in ("F", "P", "L"):
            res_pitcher.pitching.fb += 1

    if d.wp_flag:
        catcher = find_current_player(box, state.fielders[2][1 - bt], False)
        if catcher is None:
            log.error(
                "ERROR: In %s, no entry for fielder at position 2 at event %d.",
                gi.game.game_id,
                state.event_count,
            )
            _log_play(gi)
            return
        add_event(box.wp_list, inning, bt, pitcher.player_id, catcher.player_id)
        pitcher.pitching.wp += 1

    if d.sh_flag:
        who = _deref(player)
        who.batting.sh += 1
        res_pitcher.pitching.sh += 1
        add_event(box.sh_list, inning, bt, who.player_id, res_pitcher.player_id)
    if d.sf_flag:
        who = _deref(player)
        who.batting.sf += 1
        res_pitcher.pitching.sf += 1
        add_event(box.sf_list, inning, bt, who.player_id, res_pitcher.player_id)

    if d.advance[0] >= 4:
        _deref(player).batting.r += 1
        res_pitcher.pitching.r += 1
        if d.advance[0] in (4, 6):
            res_pitcher.pitching.er += 1
        if d.advance[0] == 4:
            box.er[1 - bt] += 1

    if is_batter(d):
        batting = _deref(player).batting
        batting.bi += rbi_on_play(d)
        if state.outs == 2:
            batting.bi2out += rbi_on_play(d)

    if state.outs + outs_on_play(d) == 3:
        if state.base_occupied(3) and d.advance[3] < 4:
            _deref(player).batting.lisp += 1
        if state.base_occupied(2) and d.advance[2] < 4:
            _deref(player).batting.lisp += 1
    elif d.event_type == Ev.GENERICOUT:
        if (
            state.base_occupied(1)
            and d.advance[1] > 1
            and (d.advance[1] < 4 or (d.advance[1] >= 4 and d.rbi_flag[1] == 0))
        ):
            _deref(player).batting.movedup += 1
        if state.base_occupied(2) and (
            d.advance[2] == 3 or (d.advance[2] >= 4 and d.rbi_flag[2] == 0)
        ):
            _deref(player).batting.movedup += 1


def runner_stats(box: Boxscore, gi: GameIter) -> None:  # noqa: C901, PLR0912
    """``cw_box_runner_stats``: update baserunning stats with the current play"""
    d = gi.data
    state = gi.state
    bt = state.batting_team
    for base in (1, 2, 3):
        if not state.base_occupied(base):
            continue

        player = find_current_player(box, state.runners[base].runner, True)
        if player is None:
            log.error(
                "ERROR: In %s, no entry for runner '%s' at event %d.",
                gi.game.game_id,
                state.runners[base].runner,
                state.event_count,
            )
            _log_play(gi)
            return

        pitcher = find_pitcher(box, state.responsible_pitcher(d, base))
        if pitcher is None:
            log.error(
                "ERROR: In %s, no entry for responsible pitcher '%s' for base %d at event %d.",
                gi.game.game_id,
                state.runners[base].pitcher,
                base,
                state.event_count,
            )
            _log_play(gi)
            return

        # Since we only store pointers to the player IDs in the event, we need to point to the
        # player ID in the player's roster entry
        catcher = find_current_player(box, state.fielders[2][1 - bt], False)
        if catcher is None:
            log.error(
                "ERROR: In %s, no entry for catcher '%s' for base %d at event %d.",
                gi.game.game_id,
                state.fielders[2][1 - bt],
                base,
                state.event_count,
            )
            _log_play(gi)
            return

        if d.advance[base] >= 4:
            player.batting.r += 1
            pitcher.pitching.r += 1
            if d.advance[base] in (4, 6):
                pitcher.pitching.er += 1
            if d.advance[base] == 4:
                box.er[1 - bt] += 1

        pitcher = find_pitcher(box, state.charged_pitcher(d))

        if d.sb_flag[base]:
            event = add_event(
                box.sb_list,
                state.inning,
                bt,
                player.player_id,
                _deref(pitcher).player_id,
                catcher.player_id,
            )
            event.runners = base
            player.batting.sb += 1
            event.pickoff = 1 if d.po_flag[base] else 0

        if d.cs_flag[base]:
            event = add_event(
                box.cs_list,
                state.inning,
                bt,
                player.player_id,
                _deref(pitcher).player_id,
                catcher.player_id,
            )
            event.runners = base
            player.batting.cs += 1
            event.pickoff = _c0(d.play[base]) - 48 if d.po_flag[base] else 0

            if event.pickoff == 1:
                _deref(pitcher).pitching.pk += 1
        elif d.po_flag[base]:
            if _c0(d.play[base]) == ord("2"):
                event = add_event(
                    box.po_list, state.inning, bt, player.player_id, catcher.player_id
                )
            else:
                event = add_event(
                    box.po_list, state.inning, bt, player.player_id, _deref(pitcher).player_id
                )
            event.pickoff = _c0(d.play[base]) - 48
            if event.pickoff == 1:
                _deref(pitcher).pitching.pk += 1
            event.runners = base


def fielder_stats(box: Boxscore, gi: GameIter) -> None:  # noqa: C901, PLR0912
    """``cw_box_fielder_stats``: update fielding stats with the current play"""
    d = gi.data
    state = gi.state
    bt = state.batting_team

    for pos in range(1, 10):
        accepted = False
        player = find_current_player(box, state.fielders[pos][1 - bt], False)
        fielding = player.fielding[pos] if player is not None else None
        if player is None or fielding is None:
            log.error(
                "ERROR: In %s, no entry for fielder at position %d at event %d.",
                gi.game.game_id,
                pos,
                state.event_count,
            )
            _log_play(gi)
            return

        # Fielders are credited with a game played only if they are on the field at a position
        # for at least one event.
        fielding.g = 1
        fielding.outs += outs_on_play(d)

        if (
            d.event_type in (Ev.SINGLE, Ev.DOUBLE, Ev.TRIPLE)
            or (d.event_type == Ev.HOMERUN and d.fielded_by > 0)
            or d.event_type in (Ev.ERROR, Ev.GENERICOUT, Ev.FIELDERSCHOICE)
        ):
            fielding.bip += 1

        if outs_on_play(d) > 0 and d.fielded_by == pos:
            fielding.bf += 1

        if all(p != "99" for p in d.play):
            # If there are any unknown fielding credits, do not record putouts or assists for any
            # fielder. May be overly conservative if fielding credit for one part of a DP is
            # known, but I don't know if there is any instance where that occurs in Retrosheet.
            for i in range(3):
                if d.putouts[i] == pos:
                    fielding.po += 1
                    accepted = True

            for i in range(10):
                if d.assists[i] == pos:
                    fielding.a += 1
                    accepted = True

        for i in range(10):
            if d.errors[i] == pos:
                fielding.e += 1
                add_event(box.err_list, state.inning, bt, player.player_id)

        if accepted and d.dp_flag:
            fielding.dp += 1
        if accepted and d.tp_flag:
            fielding.tp += 1

        if pos == 2 and d.pb_flag:
            pitcher = _deref(find_pitcher(box, state.charged_pitcher(d)))
            fielding.pb += 1
            add_event(box.pb_list, state.inning, bt, pitcher.player_id, player.player_id)

        if pos == 2 and d.event_type == Ev.INTERFERENCE and d.errors[0] == 2:
            fielding.xi += 1

    if d.dp_flag or d.tp_flag:
        event = add_event(box.dp_list if d.dp_flag else box.tp_list, state.inning, bt)
        for i in range(d.num_touches):
            pos = d.touches[i]
            who = _deref(find_current_player(box, state.fielders[pos][1 - bt], False))
            _set_player(event, i, who.player_id)


def iterate_game(box: Boxscore, game: Game) -> None:
    """``cw_box_iterate_game``: iterate through the game, building the boxscore"""
    lead_change = 0
    gi = GameIter(game)

    while gi.event is not None:
        state = gi.state
        bt = state.batting_team
        row = box._inning_row(state.inning)
        if row[bt] < 0:
            row[bt] = 0

        pitch_stats(box, gi)
        if gi.event.event_text != "NP":
            batter_stats(box, gi)
            runner_stats(box, gi)
            fielder_stats(box, gi)
            if gi.data.dp_flag:
                box.dp[1 - bt] += 1
            if gi.data.tp_flag:
                box.tp[1 - bt] += 1
            row[bt] += runs_on_play(gi.data)
            if (
                state.score[bt] + runs_on_play(gi.data) > state.score[1 - bt]
                and state.score[bt] - state.score[1 - bt] <= 0
            ):
                lead_change = 1
            else:
                lead_change = 0
        add_substitute(box, gi)
        gi.next()

    state = gi.state
    box.outs_at_end = state.outs
    box.walk_off = lead_change

    for t in (0, 1):
        box.lob[t] = (
            state.num_batters[t] + state.num_auto_runners[t] - state.times_out[t] - state.score[t]
        )
        box.score[t] = state.score[t]
        box.hits[t] = state.hits[t]
        box.errors[t] = state.errors[t]


def process_boxscore_file(box: Boxscore, game: Game) -> None:  # noqa: C901, PLR0912, PLR0915
    """``cw_box_process_boxscore_file``

    In these files, all the statistical information is stored in extended stat records.
    """
    date = game.info_lookup("date")

    # Assume games ended with the conclusion of an inning...
    box.outs_at_end = 3

    for stat in game.stat:
        kind = stat[0]
        if kind == "bline":
            slot = _item_int(stat, 3)
            team = _item_int(stat, 2)
            _slot_team(slot, team)

            if _item_int(stat, 4) == 1:
                # Record for starter
                player = _deref(get_starter(box, team, slot))
            else:
                player = BoxPlayer(_deref(stat[1]), "")
                player.date = _date8(date)
                player.batting.g = 1
                last = _deref(box.slots[slot][team])
                last.next = player
                player.prev = last
                box.slots[slot][team] = player

            b = player.batting
            b.pa = -1
            b.ab = _item_int(stat, 5)
            b.r = _item_int(stat, 6)
            box.score[team] += b.r
            b.h = _item_int(stat, 7)
            box.hits[team] += b.h
            b.b2 = _item_int(stat, 8)
            for _ in range(1, b.b2 + 1):
                add_event(box.b2_list, -1, -1, player.player_id, "")
            b.b3 = _item_int(stat, 9)
            for _ in range(1, b.b3 + 1):
                add_event(box.b3_list, -1, -1, player.player_id, "")
            b.hr = _item_int(stat, 10)
            for _ in range(1, b.hr + 1):
                add_event(box.hr_list, -1, -1, player.player_id, "")
            b.hrslam = -1
            b.bi = _item_int(stat, 11)
            b.bi2out = -1
            b.sh = _item_int(stat, 12)
            for _ in range(1, b.sh + 1):
                add_event(box.sh_list, -1, -1, player.player_id, "")
            b.sf = _item_int(stat, 13)
            for _ in range(1, b.sf + 1):
                add_event(box.sf_list, -1, -1, player.player_id, "")
            b.hp = _item_int(stat, 14)
            b.bb = _item_int(stat, 15)
            b.ibb = _item_int(stat, 16)
            b.so = _item_int(stat, 17)
            b.sb = _item_int(stat, 18)
            for _ in range(1, b.sb + 1):
                # the C passes a count of 2 with three strings: only the first two are stored
                event = add_event(box.sb_list, -1, -1, player.player_id, "")
                event.runners = -1
                event.pickoff = -1
            b.cs = _item_int(stat, 19)
            for _ in range(1, b.cs + 1):
                event = add_event(box.cs_list, -1, -1, player.player_id, "")
                event.runners = -1
                event.pickoff = -1
            b.gdp = _item_int(stat, 20)
            b.xi = _item_int(stat, 21)
            b.lisp = -1
            b.movedup = -1
        elif kind == "pline":
            team = _item_int(stat, 2)
            seq = _item_int(stat, 3)
            _slot_team(0, team)

            if seq == 1:
                # Record for starter
                pitcher = _deref(get_starting_pitcher(box, team))
                pitcher.pitching.gs = 1
            else:
                pitcher = BoxPitcher(_deref(stat[1]), "")
                last_pitcher = _deref(box.pitchers[team])
                last_pitcher.next = pitcher
                pitcher.prev = last_pitcher
                box.pitchers[team] = pitcher
            p = pitcher.pitching
            p.g = 1
            p.outs = _item_int(stat, 4)
            p.xb = _item_int(stat, 5)
            p.bf = _item_int(stat, 6)
            p.h = _item_int(stat, 7)
            p.b2 = _item_int(stat, 8)
            p.b3 = _item_int(stat, 9)
            p.hr = _item_int(stat, 10)
            p.r = _item_int(stat, 11)
            p.er = _item_int(stat, 12)
            p.bb = _item_int(stat, 13)
            p.ibb = _item_int(stat, 14)
            p.so = _item_int(stat, 15)
            p.hb = _item_int(stat, 16)
            p.wp = _item_int(stat, 17)
            p.bk = _item_int(stat, 18)
            p.sh = _item_int(stat, 19)
            p.sf = _item_int(stat, 20)
            p.ab = -1
            p.gdp = -1
            p.xi = -1
            p.pk = -1
            p.inr = -1
            p.inrs = -1
            p.gb = -1
            p.fb = -1
        elif kind == "dline":
            team = _item_int(stat, 2)
            seq = _item_int(stat, 3)
            pos = _item_int(stat, 4)
            found = find_player(box, stat[1], pos != 1)
            if found is None:
                msg = (
                    f"ERROR: In {game.game_id}, cannot find entry for player '{stat[1]}' "
                    "listed in dline."
                )
                log.error(msg)
                raise ValueError(msg)
            if not 0 <= pos <= 9 or seq < 1:
                raise ValueError("dline position/sequence out of range (undefined behaviour in C)")
            if found.num_positions < seq:
                found.num_positions = seq
            while seq > len(found.positions):
                found.positions.append(0)
            found.positions[seq - 1] = pos
            if found.fielding[pos] is None:
                found.fielding[pos] = BoxFielding()
            f = _deref(found.fielding[pos])
            f.g = 1
            f.outs = _item_int(stat, 5)
            f.po = _item_int(stat, 6)
            f.a = _item_int(stat, 7)
            f.e = _item_int(stat, 8)
            _slot_team(0, team)
            box.errors[team] += f.e
            f.dp = _item_int(stat, 9)
            f.tp = _item_int(stat, 10)
            f.pb = _item_int(stat, 11)
            f.bip = -1
            f.bf = -1
            f.xi = -1
        elif kind in ("phline", "prline"):
            found = find_player(box, stat[1], True)
            if found is None:
                msg = (
                    f"ERROR: In {game.game_id}, cannot find entry for player '{stat[1]}' "
                    f"listed in {kind}."
                )
                log.error(msg)
                raise ValueError(msg)
            if kind == "phline":
                found.ph_inn = _item_int(stat, 2)
            else:
                found.pr_inn = _item_int(stat, 2)
        elif kind == "tline":
            team = _item_int(stat, 1)
            _slot_team(0, team)
            box.lob[team] = _item_int(stat, 2)
            box.er[team] = _item_int(stat, 3)
            box.dp[team] = _item_int(stat, 4)
            box.tp[team] = _item_int(stat, 5)

    for line in game.line:
        team = _item_int(line, 0)
        _slot_team(0, team)
        for i in range(1, len(line)):
            box._inning_row(i)[team] = _item_int(line, i)

    for stat in game.evdata:
        if stat[0] in ("dpline", "tpline"):
            event = add_event(
                box.dp_list if stat[0] == "dpline" else box.tp_list,
                -1,
                1 - _item_int(stat, 1),
            )
            for i in range(2, len(stat)):
                _set_player(event, i - 2, _deref(stat[i]))


def box_create(game: Game) -> Boxscore:
    """``cw_box_create``: compile a boxscore for ``game``"""
    box = Boxscore()

    enter_starters(box, game)
    if game.events:
        iterate_game(box, game)
    else:
        # There is no play-by-play; this is a new "boxscore event file"
        process_boxscore_file(box, game)

    for t in (0, 1):
        last = box.pitchers[t]
        if last is None:
            continue
        if last.prev is None:
            last.pitching.cg = 1
            if last.pitching.r == 0:
                last.pitching.sho = 1
        else:
            last.pitching.gf = 1
    wp = game.info_lookup("wp")
    if wp is not None:
        pitcher = find_pitcher(box, wp)
        if pitcher is not None:
            pitcher.pitching.w = 1
    lp = game.info_lookup("lp")
    if lp is not None:
        pitcher = find_pitcher(box, lp)
        if pitcher is not None:
            pitcher.pitching.l = 1
    save = game.info_lookup("save")
    if save is not None:
        pitcher = find_pitcher(box, save)
        if pitcher is not None:
            pitcher.pitching.sv = 1
    gwrbi = game.info_lookup("gwrbi")
    if gwrbi is not None:
        batter = find_player(box, gwrbi, True)
        if batter is not None:
            batter.batting.gw = 1
    return box


def get_starter(box: Boxscore, team: int, slot: int) -> BoxPlayer | None:
    """``cw_box_get_starter``: the starter for ``team`` in batting order position ``slot``"""
    player = box.slots[slot][team]
    if player is None:
        return None
    while player.prev is not None:
        player = player.prev
    return player


def get_starting_pitcher(box: Boxscore, team: int) -> BoxPitcher | None:
    """``cw_box_get_starting_pitcher``"""
    pitcher = box.pitchers[team]
    while pitcher is not None and pitcher.prev is not None:
        pitcher = pitcher.prev
    return pitcher
