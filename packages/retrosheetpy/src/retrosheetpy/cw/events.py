"""Port of Chadwick's ``cwevent`` field logic (``src/cwtools/cwevent.c``).

Chadwick is Copyright (c) 2002-2023 Dr T L Turocy and the Chadwick Baseball
Bureau, licensed GPL-2.0-or-later; this module is a derivative of it and keeps
that notice. One function per ``cwevent`` field, in the same order, producing
the text ``cwevent -q`` (quoted/ascii mode) prints for that field. Rows are
dicts keyed by the cwevent column names.

A C ``NULL`` string printed through ``%s`` is "(null)" (glibc); ``None`` renders
that way here so unset players match.
"""

import re
from collections.abc import Callable, Collection, Iterator

from retrosheetpy.cw import game as cwgame
from retrosheetpy.cw.game import Game
from retrosheetpy.cw.gameiter import GameIter
from retrosheetpy.cw.parse import (
    Ev,
    is_batter,
    is_official_ab,
    outs_on_play,
    rbi_on_play,
    runs_on_play,
)
from retrosheetpy.cw.roster import League, Roster, roster_batting_hand, roster_throwing_hand
from retrosheetpy.cw.tools import iterate_games


def _s(value: str | None) -> str:
    return "(null)" if value is None else value


def _tf(flag: object) -> str:
    return "T" if flag else "F"


def _cmod(a: int, b: int) -> int:
    """C ``%``: the result takes the sign of the dividend."""
    r = abs(a) % b
    return -r if a < 0 else r


class _Ctx:
    """What a field function needs: the iterator, the lookahead cache and rosters."""

    def __init__(self, gi: GameIter, visitors: Roster | None, home: Roster | None) -> None:
        self.gi = gi
        self.visitors = visitors
        self.home = home
        self._fates: list[int] | None = None
        self._future: int | None = None
        self._trunc: bool | None = None

    @property
    def off_roster(self) -> Roster | None:
        ev = self.gi.event
        assert ev is not None
        return self.visitors if ev.batting_team == 0 else self.home

    @property
    def def_roster(self) -> Roster | None:
        ev = self.gi.event
        assert ev is not None
        return self.home if ev.batting_team == 0 else self.visitors

    def fate(self, base: int) -> int:
        if self._fates is None:
            self._fates = [self.gi.runner_fate(b) for b in range(4)]
        return self._fates[base]

    def future_runs(self) -> int:
        if self._future is None:
            self._future = self.gi.future_runs()
        return self._future

    def truncated(self) -> bool:
        if self._trunc is None:
            self._trunc = self.gi.truncated_pa()
        return self._trunc


Field = Callable[[_Ctx], str]


def _fielder(pos: int) -> Field:
    def f(c: _Ctx) -> str:
        return _s(c.gi.state.fielders[pos][1 - c.gi.state.batting_team])

    return f


def _runner(base: int) -> Field:
    return lambda c: c.gi.state.runners[base].runner


def _count_char(index: int) -> Field:
    def f(c: _Ctx) -> str:
        count = c.gi.event.count  # type: ignore[union-attr]
        if len(count) >= 2 and count[0] != "?" and count[1] != "?":
            return count[index]
        return "0"

    return f


def _batter_hand(c: _Ctx) -> str:
    ev, st = c.gi.event, c.gi.state
    assert ev is not None
    hand = ev.batter_hand
    if hand == " ":
        hand = roster_batting_hand(c.off_roster, ev.batter)
    if hand == "B":
        if st.pitcher_hand != " ":
            p = st.pitcher_hand
        else:
            p = roster_throwing_hand(c.def_roster, st.fielders[1][1 - st.batting_team])
        hand = "R" if p == "L" else "L" if p == "R" else "?"
    return hand


def _res_batter_hand(c: _Ctx) -> str:
    ev = c.gi.event
    assert ev is not None
    return c.gi.state.charged_batter_hand(ev.batter, c.gi.data, c.off_roster, c.def_roster)


def _pitcher_hand(c: _Ctx) -> str:
    ev, st = c.gi.event, c.gi.state
    assert ev is not None
    if ev.pitcher_hand == " ":
        return roster_throwing_hand(c.def_roster, st.fielders[1][1 - st.batting_team])
    return ev.pitcher_hand


def _res_pitcher_hand(c: _Ctx) -> str:
    ev, st = c.gi.event, c.gi.state
    assert ev is not None
    if ev.pitcher_hand == " ":
        return roster_throwing_hand(c.def_roster, st.charged_pitcher(c.gi.data))
    return ev.pitcher_hand


def _prev_play_exists(c: _Ctx) -> bool:
    events, i = c.gi.game.events, c.gi.index - 1
    while i >= 0 and events[i].event_text == "NP":
        i -= 1
    return i >= 0


def _next_play_exists(c: _Ctx) -> bool:
    events, i = c.gi.game.events, c.gi.index + 1
    while i < len(events) and events[i].event_text == "NP":
        i += 1
    return i < len(events)


def _half_inning_edge(c: _Ctx, step: int) -> str:
    """Start (step -1) / end (step +1) of half inning flag, skipping NP events."""
    ev = c.gi.event
    assert ev is not None
    events, i = c.gi.game.events, c.gi.index + step
    while 0 <= i < len(events):
        o = events[i]
        if o.inning != ev.inning or o.batting_team != ev.batting_team:
            return "T"
        if o.event_text != "NP":
            return "F"
        i += step
    return "T"


def _err_player(n: int) -> Field:
    return lambda c: str(c.gi.data.errors[n])


def _err_type(n: int) -> Field:
    return lambda c: c.gi.data.error_types[n]


def _advance(n: int) -> Field:
    return lambda c: str(c.gi.data.advance[n])


def _play(n: int) -> Field:
    return lambda c: c.gi.data.play[n]


def _flag(name: str, index: int | None = None) -> Field:
    def f(c: _Ctx) -> str:
        v = getattr(c.gi.data, name)
        return _tf(v[index] if index is not None else v)

    return f


def _resp(kind: str, base: int) -> Field:
    def f(c: _Ctx) -> str:
        st, d = c.gi.state, c.gi.data
        fn = st.responsible_pitcher if kind == "pitcher" else st.responsible_catcher
        return fn(d, base)

    return f


def _pr_flag(base: int) -> Field:
    return lambda c: _tf(c.gi.state.removed_for_pr[base])


def _removed_runner(base: int) -> Field:
    return lambda c: c.gi.state.removed_for_pr[base] or ""


def _putout(n: int) -> Field:
    return lambda c: str(c.gi.data.putouts[n])


def _assist(n: int) -> Field:
    return lambda c: str(c.gi.data.assists[n])


def _batter_is_starter(c: _Ctx) -> str:
    ev = c.gi.event
    assert ev is not None
    return _tf(any(a.player_id == ev.batter for a in c.gi.game.starters))


def _res_batter_is_starter(c: _Ctx) -> str:
    ev, st = c.gi.event, c.gi.state
    assert ev is not None
    who = st.charged_batter(ev.batter, c.gi.data)
    return _tf(any(a.player_id == who for a in c.gi.game.starters))


def _lineup_neighbour(offset: int) -> Field:
    def f(c: _Ctx) -> str:
        ev, st = c.gi.event, c.gi.state
        assert ev is not None
        slot = st.lineup_slot(st.batting_team, ev.batter)
        nxt = _cmod(slot + offset, 9) + 1  # lineups are 1-based
        return _s(st.lineups[nxt][st.batting_team].player_id)

    return f


def _pitcher_is_starter(resp: bool) -> Field:
    def f(c: _Ctx) -> str:
        st = c.gi.state
        app = c.gi.game.starter_by_position(1 - st.batting_team, 1)
        who = st.charged_pitcher(c.gi.data) if resp else st.fielders[1][1 - st.batting_team]
        return _tf(app is not None and app.player_id == who)

    return f


def _run_position(base: int) -> Field:
    def f(c: _Ctx) -> str:
        st = c.gi.state
        if not st.base_occupied(base):
            return "0"
        return str(st.player_position(st.batting_team, st.runners[base].runner))

    return f


def _run_lineup(base: int) -> Field:
    def f(c: _Ctx) -> str:
        st = c.gi.state
        if not st.base_occupied(base):
            return "0"
        return str(st.lineup_slot(st.batting_team, st.runners[base].runner))

    return f


def _src_event(base: int) -> Field:
    return lambda c: str(c.gi.state.runners[base].src_event)


def _pitches(criterion: frozenset[str]) -> Field:
    return lambda c: str(cwgame.count_pitches(c.gi.event.pitches, criterion))  # type: ignore[union-attr]


def _force(base: int) -> Field:
    def f(c: _Ctx) -> str:
        d = c.gi.data
        return _tf(d.fc_flag[base] and (d.gdp_flag or d.force_flag))

    return f


def _fielded_by_id(c: _Ctx) -> str:
    st, d = c.gi.state, c.gi.data
    if d.fielded_by == 0:
        return ""
    return _s(st.fielders[d.fielded_by][1 - st.batting_team])


def _team_id(c: _Ctx, which: str) -> str:
    g = c.gi.game
    return g.info_lookup(which) or "(null)"


def _base_state_end(c: _Ctx) -> str:
    adv = c.gi.data.advance
    r3 = int(any(a == 3 for a in adv))
    r2 = int(any(a == 2 for a in adv))
    r1 = int(any(a == 1 for a in adv))
    return str(4 * r3 + 2 * r2 + r1)


def _base_state_start(c: _Ctx) -> str:
    st = c.gi.state
    return str(
        (4 if st.base_occupied(3) else 0)
        + (2 if st.base_occupied(2) else 0)
        + (1 if st.base_occupied(1) else 0)
    )


def _half_inning(c: _Ctx) -> str:
    st = c.gi.state
    if c.gi.game.info_lookup("htbf") == "true":
        return str(1 - st.batting_team)
    return str(st.batting_team)


def _batting_team_id(c: _Ctx) -> str:
    key = "visteam" if c.gi.state.batting_team == 0 else "hometeam"
    return _team_id(c, key)


def _fielding_team_id(c: _Ctx) -> str:
    key = "visteam" if c.gi.state.batting_team == 1 else "hometeam"
    return _team_id(c, key)


def _lineup_pos(c: _Ctx) -> str:
    ev, st = c.gi.event, c.gi.state
    assert ev is not None
    return str(st.lineup_slot(st.batting_team, ev.batter))


def _defensive_position(c: _Ctx) -> str:
    ev, st = c.gi.event, c.gi.state
    assert ev is not None
    return str(st.player_position(st.batting_team, ev.batter))


def _hit_value(c: _Ctx) -> str:
    t = c.gi.data.event_type
    return str(t - Ev.SINGLE + 1 if Ev.SINGLE <= t <= Ev.HOMERUN else 0)


def _batted_ball(c: _Ctx) -> str:
    b = c.gi.data.batted_ball_type
    return "" if b == " " else b


def _pitch_seq(c: _Ctx) -> str:
    # leading whitespace is dropped, as bevent does
    return c.gi.event.pitches.lstrip()  # type: ignore[union-attr]


def _unknown_out(c: _Ctx) -> str:
    return _tf(any(p == "99" for p in c.gi.data.play))


def _uncertain(c: _Ctx) -> str:
    text = c.gi.event.event_text  # type: ignore[union-attr]
    return _tf(text[-1:] == "#")


# (column, function) in cwevent field order: standard fields 0-96
_STANDARD: tuple[tuple[str, Field], ...] = (
    ("GAME_ID", lambda c: c.gi.game.game_id),
    ("AWAY_TEAM_ID", lambda c: c.gi.game.info_lookup("visteam") or "(null)"),
    ("INN_CT", lambda c: str(c.gi.event.inning)),  # type: ignore[union-attr]
    ("BAT_HOME_ID", lambda c: str(c.gi.event.batting_team)),  # type: ignore[union-attr]
    ("OUTS_CT", lambda c: str(c.gi.state.outs)),
    ("BALLS_CT", _count_char(0)),
    ("STRIKES_CT", _count_char(1)),
    ("PITCH_SEQ_TX", _pitch_seq),
    ("AWAY_SCORE_CT", lambda c: str(c.gi.state.score[0])),
    ("HOME_SCORE_CT", lambda c: str(c.gi.state.score[1])),
    ("BAT_ID", lambda c: c.gi.event.batter),  # type: ignore[union-attr]
    ("BAT_HAND_CD", _batter_hand),
    ("RESP_BAT_ID", lambda c: c.gi.state.charged_batter(c.gi.event.batter, c.gi.data)),  # type: ignore[union-attr]
    ("RESP_BAT_HAND_CD", _res_batter_hand),
    ("PIT_ID", _fielder(1)),
    ("PIT_HAND_CD", _pitcher_hand),
    ("RESP_PIT_ID", lambda c: _s(c.gi.state.charged_pitcher(c.gi.data))),
    ("RESP_PIT_HAND_CD", _res_pitcher_hand),
    ("POS2_FLD_ID", _fielder(2)),
    ("POS3_FLD_ID", _fielder(3)),
    ("POS4_FLD_ID", _fielder(4)),
    ("POS5_FLD_ID", _fielder(5)),
    ("POS6_FLD_ID", _fielder(6)),
    ("POS7_FLD_ID", _fielder(7)),
    ("POS8_FLD_ID", _fielder(8)),
    ("POS9_FLD_ID", _fielder(9)),
    ("BASE1_RUN_ID", _runner(1)),
    ("BASE2_RUN_ID", _runner(2)),
    ("BASE3_RUN_ID", _runner(3)),
    ("EVENT_TX", lambda c: c.gi.event.event_text),  # type: ignore[union-attr]
    ("LEADOFF_FL", lambda c: _tf(c.gi.state.is_leadoff)),
    ("PH_FL", lambda c: _tf(c.gi.state.ph_flag)),
    ("BAT_FLD_CD", _defensive_position),
    ("BAT_LINEUP_ID", _lineup_pos),
    ("EVENT_CD", lambda c: str(int(c.gi.data.event_type))),
    ("BAT_EVENT_FL", lambda c: _tf(is_batter(c.gi.data))),
    ("AB_FL", lambda c: _tf(is_official_ab(c.gi.data))),
    ("H_CD", _hit_value),
    ("SH_FL", _flag("sh_flag")),
    ("SF_FL", _flag("sf_flag")),
    ("EVENT_OUTS_CT", lambda c: str(outs_on_play(c.gi.data))),
    ("DP_FL", _flag("dp_flag")),
    ("TP_FL", _flag("tp_flag")),
    ("RBI_CT", lambda c: str(rbi_on_play(c.gi.data))),
    ("WP_FL", _flag("wp_flag")),
    ("PB_FL", _flag("pb_flag")),
    ("FLD_CD", lambda c: str(c.gi.data.fielded_by)),
    ("BATTEDBALL_CD", _batted_ball),
    ("BUNT_FL", _flag("bunt_flag")),
    ("FOUL_FL", _flag("foul_flag")),
    ("BATTEDBALL_LOC_TX", lambda c: c.gi.data.hit_location),
    ("ERR_CT", lambda c: str(c.gi.data.num_errors)),
    ("ERR1_FLD_CD", _err_player(0)),
    ("ERR1_CD", _err_type(0)),
    ("ERR2_FLD_CD", _err_player(1)),
    ("ERR2_CD", _err_type(1)),
    ("ERR3_FLD_CD", _err_player(2)),
    ("ERR3_CD", _err_type(2)),
    ("BAT_DEST_ID", _advance(0)),
    ("RUN1_DEST_ID", _advance(1)),
    ("RUN2_DEST_ID", _advance(2)),
    ("RUN3_DEST_ID", _advance(3)),
    ("BAT_PLAY_TX", _play(0)),
    ("RUN1_PLAY_TX", _play(1)),
    ("RUN2_PLAY_TX", _play(2)),
    ("RUN3_PLAY_TX", _play(3)),
    ("RUN1_SB_FL", _flag("sb_flag", 1)),
    ("RUN2_SB_FL", _flag("sb_flag", 2)),
    ("RUN3_SB_FL", _flag("sb_flag", 3)),
    ("RUN1_CS_FL", _flag("cs_flag", 1)),
    ("RUN2_CS_FL", _flag("cs_flag", 2)),
    ("RUN3_CS_FL", _flag("cs_flag", 3)),
    ("RUN1_PK_FL", _flag("po_flag", 1)),
    ("RUN2_PK_FL", _flag("po_flag", 2)),
    ("RUN3_PK_FL", _flag("po_flag", 3)),
    ("RUN1_RESP_PIT_ID", _resp("pitcher", 1)),
    ("RUN2_RESP_PIT_ID", _resp("pitcher", 2)),
    ("RUN3_RESP_PIT_ID", _resp("pitcher", 3)),
    ("GAME_NEW_FL", lambda c: _tf(not _prev_play_exists(c))),
    ("GAME_END_FL", lambda c: _tf(not _next_play_exists(c))),
    ("PR_RUN1_FL", _pr_flag(1)),
    ("PR_RUN2_FL", _pr_flag(2)),
    ("PR_RUN3_FL", _pr_flag(3)),
    ("REMOVED_FOR_PR_RUN1_ID", _removed_runner(1)),
    ("REMOVED_FOR_PR_RUN2_ID", _removed_runner(2)),
    ("REMOVED_FOR_PR_RUN3_ID", _removed_runner(3)),
    ("REMOVED_FOR_PH_BAT_ID", lambda c: c.gi.state.removed_for_ph or ""),
    (
        "REMOVED_FOR_PH_BAT_FLD_CD",
        lambda c: str(c.gi.state.removed_position if c.gi.state.removed_for_ph else 0),
    ),
    ("PO1_FLD_CD", _putout(0)),
    ("PO2_FLD_CD", _putout(1)),
    ("PO3_FLD_CD", _putout(2)),
    ("ASS1_FLD_CD", _assist(0)),
    ("ASS2_FLD_CD", _assist(1)),
    ("ASS3_FLD_CD", _assist(2)),
    ("ASS4_FLD_CD", _assist(3)),
    ("ASS5_FLD_CD", _assist(4)),
    ("EVENT_ID", lambda c: str(c.gi.state.event_count + 1)),
)

# extended fields 0-66 (``cwevent -x``)
_EXTENDED: tuple[tuple[str, Field], ...] = (
    ("HOME_TEAM_ID", lambda c: _team_id(c, "hometeam")),
    ("BAT_TEAM_ID", _batting_team_id),
    ("FLD_TEAM_ID", _fielding_team_id),
    ("BAT_LAST_ID", _half_inning),
    ("INN_NEW_FL", lambda c: _half_inning_edge(c, -1)),
    ("INN_END_FL", lambda c: _half_inning_edge(c, +1)),
    ("START_BAT_SCORE_CT", lambda c: str(c.gi.state.score[c.gi.state.batting_team])),
    ("START_FLD_SCORE_CT", lambda c: str(c.gi.state.score[1 - c.gi.state.batting_team])),
    ("INN_RUNS_CT", lambda c: str(c.gi.state.inning_score)),
    ("GAME_PA_CT", lambda c: str(c.gi.state.num_batters[c.gi.state.batting_team])),
    ("INN_PA_CT", lambda c: str(c.gi.state.inning_batters)),
    ("PA_NEW_FL", lambda c: _tf(c.gi.state.is_new_pa)),
    ("PA_TRUNC_FL", lambda c: _tf(c.truncated())),
    ("START_BASES_CD", _base_state_start),
    ("END_BASES_CD", _base_state_end),
    ("BAT_START_FL", _batter_is_starter),
    ("RESP_BAT_START_FL", _res_batter_is_starter),
    ("BAT_ON_DECK_ID", _lineup_neighbour(0)),
    ("BAT_IN_HOLD_ID", _lineup_neighbour(1)),
    ("PIT_START_FL", _pitcher_is_starter(False)),
    ("RESP_PIT_START_FL", _pitcher_is_starter(True)),
    ("RUN1_FLD_CD", _run_position(1)),
    ("RUN1_LINEUP_CD", _run_lineup(1)),
    ("RUN1_ORIGIN_EVENT_ID", _src_event(1)),
    ("RUN2_FLD_CD", _run_position(2)),
    ("RUN2_LINEUP_CD", _run_lineup(2)),
    ("RUN2_ORIGIN_EVENT_ID", _src_event(2)),
    ("RUN3_FLD_CD", _run_position(3)),
    ("RUN3_LINEUP_CD", _run_lineup(3)),
    ("RUN3_ORIGIN_EVENT_ID", _src_event(3)),
    ("RUN1_RESP_CAT_ID", _resp("catcher", 1)),
    ("RUN2_RESP_CAT_ID", _resp("catcher", 2)),
    ("RUN3_RESP_CAT_ID", _resp("catcher", 3)),
    ("PA_BALL_CT", _pitches(cwgame.PITCH_BALL_THROWN)),
    ("PA_CALLED_BALL_CT", _pitches(cwgame.PITCH_BALL_CALLED)),
    ("PA_INTENT_BALL_CT", _pitches(cwgame.PITCH_BALL_INTENTIONAL)),
    ("PA_PITCHOUT_BALL_CT", _pitches(cwgame.PITCH_BALL_PITCHOUT)),
    ("PA_HITBATTER_BALL_CT", _pitches(cwgame.PITCH_BALL_HIT_BATTER)),
    ("PA_OTHER_BALL_CT", _pitches(cwgame.PITCH_BALL_OTHER)),
    ("PA_STRIKE_CT", _pitches(cwgame.PITCH_STRIKE_THROWN)),
    ("PA_CALLED_STRIKE_CT", _pitches(cwgame.PITCH_STRIKE_CALLED)),
    ("PA_SWINGMISS_STRIKE_CT", _pitches(cwgame.PITCH_STRIKE_SWINGING)),
    ("PA_FOUL_STRIKE_CT", _pitches(cwgame.PITCH_STRIKE_FOUL)),
    ("PA_INPLAY_STRIKE_CT", _pitches(cwgame.PITCH_STRIKE_INPLAY)),
    ("PA_OTHER_STRIKE_CT", _pitches(cwgame.PITCH_STRIKE_OTHER)),
    ("EVENT_RUNS_CT", lambda c: str(runs_on_play(c.gi.data))),
    ("FLD_ID", _fielded_by_id),
    ("BASE2_FORCE_FL", _force(1)),
    ("BASE3_FORCE_FL", _force(2)),
    ("BASE4_FORCE_FL", _force(3)),
    (
        "BAT_SAFE_ERR_FL",
        lambda c: _tf(
            c.gi.data.event_type == Ev.ERROR
            or (c.gi.data.event_type == Ev.GENERICOUT and c.gi.data.muff_flag[0])
        ),
    ),
    ("BAT_FATE_ID", lambda c: str(c.fate(0))),
    ("RUN1_FATE_ID", lambda c: str(c.fate(1))),
    ("RUN2_FATE_ID", lambda c: str(c.fate(2))),
    ("RUN3_FATE_ID", lambda c: str(c.fate(3))),
    ("FATE_RUNS_CT", lambda c: str(c.future_runs())),
    ("ASS6_FLD_CD", _assist(5)),
    ("ASS7_FLD_CD", _assist(6)),
    ("ASS8_FLD_CD", _assist(7)),
    ("ASS9_FLD_CD", _assist(8)),
    ("ASS10_FLD_CD", _assist(9)),
    ("UNKNOWN_OUT_EXC_FL", _unknown_out),
    ("UNCERTAIN_PLAY_EXC_FL", _uncertain),
    ("COUNT_TX", lambda c: c.gi.event.count),  # type: ignore[union-attr]
    ("RUN1_AUTO_FL", lambda c: _tf(c.gi.state.runner_is_auto(c.gi.data, 1))),
    ("RUN2_AUTO_FL", lambda c: _tf(c.gi.state.runner_is_auto(c.gi.data, 2))),
    ("RUN3_AUTO_FL", lambda c: _tf(c.gi.state.runner_is_auto(c.gi.data, 3))),
)

COLUMNS = tuple(name for name, _ in _STANDARD + _EXTENDED)
MAX_FIELD = len(_STANDARD) - 1
MAX_EXT_FIELD = len(_EXTENDED) - 1

# The fields ``cwevent`` prints by default (its ``fields[]``): 0-6, 8-9, 12-13, 16-17, 26-40,
# 43-45, 51 and 58-61
DEFAULT_FIELDS = (
    *range(0, 7),
    8,
    9,
    12,
    13,
    16,
    17,
    *range(26, 41),
    *range(43, 46),
    51,
    *range(58, 62),
)


def game_rows(
    game: Game, visitors: Roster | None = None, home: Roster | None = None
) -> Iterator[dict[str, str]]:
    """``cwevent_process_game``: one row per non-NP event of the game."""
    gi = GameIter(game)
    while gi.event is not None:
        if gi.event.event_text == "NP":
            gi.next()
            continue
        ctx = _Ctx(gi, visitors, home)
        yield {name: fn(ctx) for name, fn in _STANDARD + _EXTENDED}
        gi.next()


def event_rows(
    data: bytes,
    league: League | None = None,
    game_id: str = "",
    first_date: str = "0101",
    last_date: str = "1231",
) -> Iterator[dict[str, str]]:
    """Rows for the selected games of an event file, as ``cwevent -q -f 0-96 -x 0-66`` does.

    ``league`` holds the rosters read from the team file; without it every hand not given by
    a ``badj``/``padj`` record is ``?``.
    """
    for game, visitors, home in iterate_games(data, league, game_id, first_date, last_date):
        yield from game_rows(game, visitors, home)


# ``(ascii format, fixed format)`` of each field, the ``sprintf`` formats of the C field functions
# (``(ascii) ? A : B``, or the one format when the C does not distinguish), in field order:
# the 97 standard fields, then the 67 extended ones. ``None`` marks the four fields whose format
# depends on the play (``_CUSTOM``). The ``%s``/``%c``/``%d`` conversions take the field's value.
_FORMATS: tuple[tuple[str, str] | None, ...] = (
    ('"%s"', "%-12s"),
    ('"%s"', "%-3s"),
    ("%d", "%4d"),
    ("%d", "%d"),
    ("%d", "%d"),
    ("%s", "%s"),
    ("%s", "%s"),
    ('"%s"', "%-20s"),
    ("%d", "%2d"),
    ("%d", "%2d"),
    ('"%s"', "%-8s"),
    ('"%c"', "%c"),
    ('"%s"', "%-8s"),
    ('"%c"', "%c"),
    ('"%s"', "%-8s"),
    ('"%c"', "%c"),
    ('"%s"', "%-8s"),
    ('"%c"', "%c"),
    ('"%s"', "%-8s"),
    ('"%s"', "%-8s"),
    ('"%s"', "%-8s"),
    ('"%s"', "%-8s"),
    ('"%s"', "%-8s"),
    ('"%s"', "%-8s"),
    ('"%s"', "%-8s"),
    ('"%s"', "%-8s"),
    ('"%s"', "%-8s"),
    ('"%s"', "%-8s"),
    ('"%s"', "%-8s"),
    ('"%s"', "%-20s"),
    ('"%c"', "%c"),
    ('"%c"', "%c"),
    ("%d", "%2d"),
    ("%d", "%d"),
    ("%d", "%2d"),
    ('"%c"', "%c"),
    ('"%c"', "%c"),
    ("%d", "%d"),
    ('"%c"', "%c"),
    ('"%c"', "%c"),
    ("%d", "%d"),
    ('"%c"', "%c"),
    ('"%c"', "%c"),
    ("%d", "%d"),
    ('"%c"', "%c"),
    ('"%c"', "%c"),
    ("%d", "%d"),
    None,
    ('"%c"', "%c"),
    ('"%c"', "%c"),
    ('"%s"', "%4s"),
    ("%d", "%d"),
    ("%d", "%d"),
    ('"%c"', "   %c"),
    ("%d", "%d"),
    ('"%c"', "   %c"),
    ("%d", "%d"),
    ('"%c"', "   %c"),
    ("%d", "%d"),
    ("%d", "%d"),
    ("%d", "%d"),
    ("%d", "%d"),
    ('"%s"', "%12s"),
    ('"%s"', "%12s"),
    ('"%s"', "%12s"),
    ('"%s"', "%12s"),
    ('"%c"', "%c"),
    ('"%c"', "%c"),
    ('"%c"', "%c"),
    ('"%c"', "%c"),
    ('"%c"', "%c"),
    ('"%c"', "%c"),
    ('"%c"', "%c"),
    ('"%c"', "%c"),
    ('"%c"', "%c"),
    ('"%s"', "%-8s"),
    ('"%s"', "%-8s"),
    ('"%s"', "%-8s"),
    ('"%c"', "%c"),
    ('"%c"', "%c"),
    ('"%c"', "       %c"),
    ('"%c"', "       %c"),
    ('"%c"', "       %c"),
    ('"%s"', "%-8s"),
    ('"%s"', "%-8s"),
    ('"%s"', "%-8s"),
    ('"%s"', "%-8s"),
    ("%d", "%2d"),
    ("%d", "%d"),
    ("%d", "%d"),
    ("%d", "%d"),
    ("%d", "%d"),
    ("%d", "%d"),
    ("%d", "%d"),
    ("%d", "%d"),
    ("%d", "%d"),
    ("%d", "%3d"),
    ('"%s"', "%-3s"),
    ('"%s"', "%-3s"),
    ('"%s"', "%-3s"),
    ("%d", "%d"),
    ('"%c"', "%c"),
    ('"%c"', "%c"),
    ("%d", "%2d"),
    ("%d", "%2d"),
    ("%d", "%2d"),
    ("%d", "%3d"),
    ("%d", "%2d"),
    ('"%c"', "%c"),
    ('"%c"', "%c"),
    ("%d", "%d"),
    ("%d", "%d"),
    ('"%c"', "%c"),
    ('"%c"', "%c"),
    ('"%s"', "%-8s"),
    ('"%s"', "%-8s"),
    ('"%c"', "%c"),
    ('"%c"', "%c"),
    None,
    ("%d", "%d"),
    ("%d", "%3d"),
    None,
    ("%d", "%d"),
    ("%d", "%3d"),
    None,
    ("%d", "%d"),
    ("%d", "%3d"),
    ('"%s"', "%-8s"),
    ('"%s"', "%-8s"),
    ('"%s"', "%-8s"),
    ("%d", "%02d"),
    ("%d", "%02d"),
    ("%d", "%02d"),
    ("%d", "%02d"),
    ("%d", "%02d"),
    ("%d", "%02d"),
    ("%d", "%02d"),
    ("%d", "%02d"),
    ("%d", "%02d"),
    ("%d", "%02d"),
    ("%d", "%02d"),
    ("%d", "%02d"),
    ("%d", "%d"),
    ('"%s"', "%-8s"),
    ('"%c"', "%c"),
    ('"%c"', "%c"),
    ('"%c"', "%c"),
    ('"%c"', "%c"),
    ("%d", "%d"),
    ("%d", "%d"),
    ("%d", "%d"),
    ("%d", "%d"),
    ("%d", "%02d"),
    ("%d", "%d"),
    ("%d", "%d"),
    ("%d", "%d"),
    ("%d", "%d"),
    ("%d", "%d"),
    ('"%c"', "%c"),
    ('"%c"', "%c"),
    ('"%s"', "%-2s"),
    ('"%c"', "%c"),
    ('"%c"', "%c"),
    ('"%c"', "%c"),
)


def _c_format(fmt: str, value: str) -> str:
    """One ``sprintf`` conversion (``%s``, ``%c`` or ``%d`` with ``-``/``0`` flag and width) of
    ``fmt`` applied to ``value``, with the text around it kept"""
    found = re.search(r"%(-?)(0?)(\d*)([scd])", fmt)
    assert found is not None
    left, zero, width, kind = found.groups()
    text = str(int(value)) if kind == "d" else value
    w = int(width) if width else 0
    if left:
        text = text.ljust(w)
    elif zero and kind == "d":
        text = f"{int(value):0{w}d}"
    else:
        text = text.rjust(w)
    return fmt[: found.start()] + text + fmt[found.end() :]


def _custom(index: int, ascii_: bool, c: _Ctx, value: str) -> str:
    """The fields whose format depends on the play"""
    if index == 47:  # cwevent_batted_ball_type
        if c.gi.data.batted_ball_type != " ":
            return f'"{value}"' if ascii_ else value
        return '""' if ascii_ else " "
    # cwevent_runner{1,2,3}_defensive_position
    base = {118: 1, 121: 2, 124: 3}[index]
    if not c.gi.state.base_occupied(base):
        return "0"
    return value if ascii_ else f"{int(value):2d}"


def _render(index: int, ascii_: bool, c: _Ctx, value: str) -> str:
    fmt = _FORMATS[index]
    if fmt is None:
        return _custom(index, ascii_, c, value)
    return _c_format(fmt[0] if ascii_ else fmt[1], value)


def header_line(fields: Collection[int], ext_fields: Collection[int]) -> str:
    """``cwevent_initialize`` with ``-n``: the quoted column names (ascii format only)"""
    names = [f'"{COLUMNS[i]}"' for i in range(MAX_FIELD + 1) if i in fields]
    names += [
        f'"{COLUMNS[MAX_FIELD + 1 + i]}"' for i in range(MAX_EXT_FIELD + 1) if i in ext_fields
    ]
    return ",".join(names)


def game_lines(
    game: Game,
    visitors: Roster | None = None,
    home: Roster | None = None,
    ascii_: bool = True,
    fields: Collection[int] = DEFAULT_FIELDS,
    ext_fields: Collection[int] = (),
) -> Iterator[str]:
    """``cwevent_process_game``: one output line per non-NP event of the game"""
    gi = GameIter(game)
    table = _STANDARD + _EXTENDED
    while gi.event is not None:
        if gi.event.event_text == "NP":
            gi.next()
            continue
        ctx = _Ctx(gi, visitors, home)
        parts = [
            _render(i, ascii_, ctx, table[i][1](ctx)) for i in range(MAX_FIELD + 1) if i in fields
        ]
        parts += [
            _render(MAX_FIELD + 1 + i, ascii_, ctx, table[MAX_FIELD + 1 + i][1](ctx))
            for i in range(MAX_EXT_FIELD + 1)
            if i in ext_fields
        ]
        yield ("," if ascii_ else "").join(parts)
        gi.next()


def event_lines(
    data: bytes,
    league: League | None = None,
    game_id: str = "",
    first_date: str = "0101",
    last_date: str = "1231",
    ascii_: bool = True,
    fields: Collection[int] = DEFAULT_FIELDS,
    ext_fields: Collection[int] = (),
) -> Iterator[str]:
    """Lines for the selected games of an event file, as ``cwevent`` prints them."""
    for game, visitors, home in iterate_games(data, league, game_id, first_date, last_date):
        yield from game_lines(game, visitors, home, ascii_, fields, ext_fields)


# The field descriptions ``cwevent -d`` lists, in field order
DESCRIPTIONS = (
    "game id*",
    "visiting team*",
    "inning*",
    "batting_team*",
    "outs*",
    "balls*",
    "strikes*",
    "pitch sequence",
    "vis score*",
    "home score*",
    "batter",
    "batter hand",
    "res batter*",
    "res batter hand*",
    "pitcher",
    "pitcher hand",
    "res pitcher*",
    "res pitcher hand*",
    "catcher",
    "first base",
    "second base",
    "third base",
    "shortstop",
    "left field",
    "center field",
    "right field",
    "first runner*",
    "second runner*",
    "third runner*",
    "event text*",
    "leadoff flag*",
    "pinchhit flag*",
    "defensive position*",
    "lineup position*",
    "event type*",
    "batter event flag*",
    "ab flag*",
    "hit value*",
    "SH flag*",
    "SF flag*",
    "outs on play*",
    "double play flag",
    "triple play flag",
    "RBI on play*",
    "wild pitch flag*",
    "passed ball flag*",
    "fielded by",
    "batted ball type",
    "bunt flag",
    "foul flag",
    "hit location",
    "num errors*",
    "1st error player",
    "1st error type",
    "2nd error player",
    "2nd error type",
    "3rd error player",
    "3rd error type",
    "batter dest* (5 if scores and unearned, 6 if team unearned)",
    "runner on 1st dest* (5 if scores and unearned, 6 if team unearned)",
    "runner on 2nd dest* (5 if scores and unearned, 6 if team unearned)",
    "runner on 3rd dest* (5 if scores and unearned, 6 if team unearned)",
    "play on batter",
    "play on runner on first",
    "play on runner on second",
    "play on runner on third",
    "SB for runner on 1st flag",
    "SB for runner on 2nd flag",
    "SB for runner on 3rd flag",
    "CS for runner on 1st flag",
    "CS for runner on 2nd flag",
    "CS for runner on 3rd flag",
    "PO for runner on 1st flag",
    "PO for runner on 2nd flag",
    "PO for runner on 3rd flag",
    "Responsible pitcher for runner on 1st",
    "Responsible pitcher for runner on 2nd",
    "Responsible pitcher for runner on 3rd",
    "New Game Flag",
    "End Game Flag",
    "Pinch-runner on 1st",
    "Pinch-runner on 2nd",
    "Pinch-runner on 3rd",
    "Runner removed for pinch-runner on 1st",
    "Runner removed for pinch-runner on 2nd",
    "Runner removed for pinch-runner on 3rd",
    "Batter removed for pinch-hitter ",
    "Position of batter removed for pinch-hitter",
    "Fielder with First Putout (0 if none)",
    "Fielder with Second Putout (0 if none)",
    "Fielder with Third Putout (0 if none)",
    "Fielder with First Assist (0 if none)",
    "Fielder with Second Assist (0 if none)",
    "Fielder with Third Assist (0 if none)",
    "Fielder with Fourth Assist (0 if none)",
    "Fielder with Fifth Assist (0 if none)",
    "event num",
)
EXT_DESCRIPTIONS = (
    "home team id",
    "batting team id",
    "fielding team id",
    "half inning (differs from batting team if home team bats first",
    "start of half inning flag",
    "end of half inning flag",
    "score for team on offense",
    "score for team on defense",
    "runs scored in this half inning",
    "number of plate appearances in game for team on offense",
    "number of plate appearances in inning for team on offense",
    "start of plate appearance flag",
    "truncated plate appearance flag",
    "base state at start of play",
    "base state at end of play",
    "batter is starter flag",
    "result batter is starter flag",
    "ID of batter on deck",
    "ID of batter in the hold",
    "pitcher is starter flag",
    "result pitcher is starter flag",
    "defensive position of runner on first",
    "lineup position of runner on first",
    "event number on which runner on first reached base",
    "defensive position of runner on second",
    "lineup position of runner on second",
    "event number on which runner on second reached base",
    "defensive position of runner on third",
    "lineup position of runner on third",
    "event number on which runner on third reached base",
    "Responsible catcher for runner on 1st",
    "Responsible catcher for runner on 2nd",
    "Responsible catcher for runner on 3rd",
    "number of balls thrown in plate appearance",
    "number of called balls in plate appearance",
    "number of intentional balls in plate appearance",
    "number of pitchouts in plate appearance",
    "number of pitches hitting batter in plate appearance",
    "number of other balls in plate appearance",
    "number of strikes thrown in plate appearance",
    "number of called strikes in plate appearance",
    "number of swinging strikes in plate appearance",
    "number of foul balls in plate appearance",
    "number of balls in play in plate appearance",
    "number of other strikes in plate appearance",
    "number of runs on play",
    "id of player fielding batted ball",
    "force play at second flag",
    "force play at third flag",
    "force play at home flag",
    "batter safe on error flag",
    "fate of batter (base ultimately advanced to)",
    "fate of runner on first",
    "fate of runner on second",
    "fate of runner on third",
    "runs scored in half inning after this event",
    "fielder with sixth assist",
    "fielder with seventh assist",
    "fielder with eighth assist",
    "fielder with ninth assist",
    "fielder with tenth assist",
    "unknown fielding credit flag",
    "uncertain play flag",
    "text of count as appears in event file",
    "whether runner on first is an automatic runner",
    "whether runner on second is an automatic runner",
    "whether runner on third is an automatic runner",
)
