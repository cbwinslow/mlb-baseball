"""Port of Chadwick's game iterator (``src/cwlib/gameiter.c``).

Chadwick is Copyright (c) 2002-2023 Dr T L Turocy and the Chadwick Baseball
Bureau, licensed GPL-2.0-or-later; this module is a derivative of it and keeps
that notice. Names map onto the C functions (``cw_gamestate_x`` -> ``State.x``
or a module function) so the two can be read side by side.

Unset C pointers (``NULL`` strings) are ``None`` here.
"""

from dataclasses import dataclass, field

from retrosheetpy.cw.game import Appearance, Event, Game
from retrosheetpy.cw.parse import (
    Ev,
    EventData,
    is_batter,
    outs_on_play,
    parse_event,
    runner_put_out,
    runs_on_play,
)
from retrosheetpy.cw.roster import Roster, roster_batting_hand, roster_throwing_hand

POS_P, POS_C, POS_MAX, POS_DH, POS_PH, POS_PR = 1, 2, 9, 10, 11, 12


@dataclass(slots=True)
class Runner:
    """One entry of ``CWGameState.runners``; base 0 is the batter-runner."""

    runner: str = ""
    pitcher: str = ""
    catcher: str = ""
    src_event: int = 0
    is_auto: int = 0

    def clear(self) -> None:
        self.runner = self.pitcher = self.catcher = ""
        self.src_event = 0
        self.is_auto = 0

    def copy_from(self, other: "Runner") -> None:
        self.runner = other.runner
        self.pitcher = other.pitcher
        self.catcher = other.catcher
        self.src_event = other.src_event
        self.is_auto = other.is_auto


@dataclass(slots=True)
class Slot:
    """One lineup entry (``CWLineupEntry``)."""

    player_id: str | None = None
    name: str | None = None
    position: int = 0


def _new_runners() -> list[Runner]:
    return [Runner() for _ in range(4)]


def _new_lineups() -> list[list[Slot]]:
    return [[Slot(), Slot()] for _ in range(10)]  # [slot][team]


@dataclass
class State:
    """``CWGameState``"""

    event_count: int = 0
    inning: int = 1
    batting_team: int = 0
    outs: int = 0
    inning_batters: int = 0
    inning_score: int = 0
    score: list[int] = field(default_factory=lambda: [0, 0])
    hits: list[int] = field(default_factory=lambda: [0, 0])
    errors: list[int] = field(default_factory=lambda: [0, 0])
    times_out: list[int] = field(default_factory=lambda: [0, 0])
    next_batter: list[int] = field(default_factory=lambda: [1, 1])
    num_batters: list[int] = field(default_factory=lambda: [0, 0])
    dh_slot: list[int] = field(default_factory=lambda: [0, 0])
    num_auto_runners: list[int] = field(default_factory=lambda: [0, 0])
    is_leadoff: int = 1
    is_new_pa: int = 1
    ph_flag: int = 0
    runners: list[Runner] = field(default_factory=_new_runners)
    lineups: list[list[Slot]] = field(default_factory=_new_lineups)
    fielders: list[list[str | None]] = field(
        default_factory=lambda: [[None, None] for _ in range(10)]
    )
    removed_for_ph: str | None = None
    removed_for_pr: list[str | None] = field(default_factory=lambda: [None] * 4)
    walk_pitcher: str | None = None
    strikeout_batter: str | None = None
    strikeout_batter_hand: str = " "
    removed_position: int = 0
    go_ahead_rbi: str | None = None
    batter_hand: str = " "
    pitcher_hand: str = " "
    date: str = ""  # updates on game resumption after suspension

    def copy(self) -> "State":
        """``cw_gamestate_copy``"""
        c = State(
            self.event_count,
            self.inning,
            self.batting_team,
            self.outs,
            self.inning_batters,
            self.inning_score,
            self.score[:],
            self.hits[:],
            self.errors[:],
            self.times_out[:],
            self.next_batter[:],
            self.num_batters[:],
            self.dh_slot[:],
            self.num_auto_runners[:],
            self.is_leadoff,
            self.is_new_pa,
            self.ph_flag,
        )
        for dst, src in zip(c.runners, self.runners, strict=True):
            dst.copy_from(src)
        c.lineups = [[Slot(s.player_id, s.name, s.position) for s in row] for row in self.lineups]
        c.fielders = [row[:] for row in self.fielders]
        c.removed_for_ph = self.removed_for_ph
        c.removed_for_pr = self.removed_for_pr[:]
        c.walk_pitcher = self.walk_pitcher
        c.strikeout_batter = self.strikeout_batter
        c.strikeout_batter_hand = self.strikeout_batter_hand
        c.removed_position = self.removed_position
        c.go_ahead_rbi = self.go_ahead_rbi
        c.batter_hand = self.batter_hand
        c.pitcher_hand = self.pitcher_hand
        c.date = self.date
        return c

    # -- runners ----------------------------------------------------------

    def base_occupied(self, base: int) -> bool:
        """``cw_gamestate_base_occupied``"""
        return self.runners[base].runner != ""

    def _place_runner(self, base: int, runner: str) -> None:
        """Tiebreaker runner: responsibility goes to the current pitcher and catcher."""
        r = self.runners[base]
        r.runner = runner
        r.pitcher = self.fielders[1][1 - self.batting_team] or ""
        r.catcher = self.fielders[2][1 - self.batting_team] or ""
        r.is_auto = 1
        self.num_auto_runners[self.batting_team] += 1

    def _place_batter(self, batter: str, event_type: int) -> None:
        r = self.runners[0]
        r.runner = batter
        if event_type in (Ev.WALK, Ev.INTENTIONALWALK) and self.walk_pitcher:
            r.pitcher = self.walk_pitcher
        else:
            r.pitcher = self.fielders[POS_P][1 - self.batting_team] or ""
        r.catcher = self.fielders[POS_C][1 - self.batting_team] or ""
        r.src_event = self.event_count
        r.is_auto = 0

    def _replace_runner(self, base: int, runner: str) -> None:
        self.runners[base].runner = runner

    def _move_runner(self, src: int, dest: int) -> None:
        s, d = self.runners[src], self.runners[dest]
        d.runner, d.pitcher, d.catcher = s.runner, s.pitcher, s.catcher
        d.src_event = s.src_event
        d.is_auto = s.is_auto
        s.is_auto = 0

    def _reassign_responsibility(self, base: int) -> None:
        """Rule 10.18(g): push responsibility back one runner on a force out / FC."""
        src = self.runners[base]
        for b in range(base - 1, 0, -1):
            if self.base_occupied(b):
                self._reassign_responsibility(b)
                dst = self.runners[b]
                dst.pitcher, dst.catcher, dst.is_auto = src.pitcher, src.catcher, src.is_auto
                return
        dst = self.runners[0]
        dst.pitcher, dst.catcher, dst.is_auto = src.pitcher, src.catcher, src.is_auto

    def _clear_all_runners(self) -> None:
        for r in self.runners:
            r.clear()

    # -- update -----------------------------------------------------------

    def _check_go_ahead_rbi(self, batter: str, d: EventData) -> None:
        diff = self.score[self.batting_team] - self.score[1 - self.batting_team]
        for base in range(3, -1, -1):
            if d.advance[base] >= 4:
                diff += 1
                if diff == 1:  # the go-ahead run
                    self.go_ahead_rbi = batter if d.rbi_flag[base] else None
                    return
                if diff == 0:  # the tying run
                    self.go_ahead_rbi = None

    def _process_advance(self, batter: str, d: EventData) -> None:
        self._place_batter(batter, d.event_type)

        if d.advance[3] >= 4 or runner_put_out(d, 3):
            if d.fc_flag[3] and runner_put_out(d, 3):
                self._reassign_responsibility(3)
            self.runners[3].clear()

        if d.advance[2] == 3:
            self._move_runner(2, 3)
        if d.advance[2] >= 3 or runner_put_out(d, 2):
            if d.fc_flag[2] and runner_put_out(d, 2):
                self._reassign_responsibility(2)
            self.runners[2].clear()

        if d.advance[1] == 2:
            self._move_runner(1, 2)
        elif d.advance[1] == 3:
            self._move_runner(1, 3)
        if d.advance[1] >= 2 or runner_put_out(d, 1):
            if d.fc_flag[1] and runner_put_out(d, 1):
                self._reassign_responsibility(1)
            self.runners[1].clear()

        # Backwards advances, processed after forward ones to avoid clobbering
        if d.advance[3] == 2:
            self._move_runner(3, 2)
            self.runners[3].clear()
        elif d.advance[3] == 1:
            self._move_runner(3, 1)
            self.runners[3].clear()
        if d.advance[2] == 1:
            self._move_runner(2, 1)
            self.runners[2].clear()

        if 1 <= d.advance[0] <= 3:
            self._move_runner(0, d.advance[0])

    def update(self, batter: str, d: EventData) -> None:
        """``cw_gamestate_update``"""
        self._check_go_ahead_rbi(batter, d)

        self.event_count += 1
        runs = runs_on_play(d)
        outs = outs_on_play(d)
        self.score[self.batting_team] += runs
        self.inning_score += runs
        if Ev.SINGLE <= d.event_type <= Ev.HOMERUN:
            self.hits[self.batting_team] += 1
        self.errors[1 - self.batting_team] += d.num_errors
        self.times_out[self.batting_team] += outs
        self.outs += outs

        self._process_advance(batter, d)

        if is_batter(d):
            t = self.batting_team
            self.num_batters[t] += 1
            self.next_batter[t] += 1
            if self.next_batter[t] == 10:
                self.next_batter[t] = 1
            self.inning_batters += 1
            self.ph_flag = 0
            self.is_leadoff = 0
            self.is_new_pa = 1
            self.removed_for_ph = None
            self.walk_pitcher = None
            self.strikeout_batter = None
        else:
            self.is_new_pa = 0

        for i in range(1, 4):
            self.removed_for_pr[i] = None

    def substitute(
        self, batter: str, count: str, player_id: str, name: str, team: int, slot: int, pos: int
    ) -> None:
        """``cw_gamestate_substitute``"""
        row = self.lineups[slot][team]
        removed_player, removed_position = row.player_id, row.position

        row.player_id = player_id
        row.name = name
        row.position = pos

        if len(count) == 2 and count[0] != "?" and count[1] != "?":
            if pos == 1 and (count in ("20", "21") or count[0] == "3"):
                self.walk_pitcher = self.fielders[1][team]
            elif pos == POS_PH and self.strikeout_batter is None and count[1] == "2":
                self.strikeout_batter = batter
                self.strikeout_batter_hand = self.batter_hand

        if pos <= POS_MAX:
            self.fielders[pos][team] = player_id
            if pos == 1 and slot > 0 and self.lineups[0][team].player_id is not None:
                # Pitcher substituted into the batting order: the DH is gone
                self.lineups[0][team].player_id = None
                self.lineups[0][team].name = None
                self.dh_slot[team] = 0
        elif pos == POS_PH:
            self.removed_for_ph = removed_player
            self.ph_flag = 1
            self.removed_position = removed_position
        elif pos == POS_PR:
            for b in (1, 2, 3):
                if self.runners[b].runner == removed_player:
                    self.removed_for_pr[b] = removed_player
                    self._replace_runner(b, player_id)
                    break

        if (
            slot > 0
            and self.lineups[0][team].player_id is not None
            and self.lineups[0][team].player_id == player_id
        ):
            # Should be illegal but happened on 1976/9/5 (Catfish Hunter as a
            # pinch-hitter for a player other than the DH)
            self.lineups[0][team].player_id = None
            self.lineups[0][team].name = None
            self.dh_slot[team] = 0

    def change_sides(self, event: Event) -> None:
        """``cw_gamestate_change_sides``"""
        self.inning = event.inning
        self.batting_team = event.batting_team
        self.outs = 0
        self.is_leadoff = 1
        self.is_new_pa = 1
        self.ph_flag = 0
        self.inning_batters = 0
        self.inning_score = 0
        self._clear_all_runners()

        # Pinch-hitters or -runners for the DH automatically become the DH
        for i in (0, 1):
            if self.dh_slot[i] > 0 and self.lineups[self.dh_slot[i]][i].position > 10:
                self.lineups[self.dh_slot[i]][i].position = 10

        # Clear removed batter, in case the inning ends on a non-batter event
        self.removed_for_ph = None

    def left_on_base(self, team: int) -> int:
        return (
            self.num_batters[team]
            + self.num_auto_runners[team]
            - self.score[team]
            - self.times_out[team]
        )

    def lineup_slot(self, team: int, player_id: str | None) -> int:
        """``cw_gamestate_lineup_slot``: search from slot 9 down to prefer batting-order slots."""
        for i in range(9, -1, -1):
            pid = self.lineups[i][team].player_id
            if pid is not None and pid == player_id:
                return i
        return -1

    def player_position(self, team: int, player_id: str | None) -> int:
        """``cw_gamestate_player_position``"""
        for i in range(1, 10):
            row = self.lineups[i][team]
            if row.player_id is not None and row.player_id == player_id:
                if row.position > 10 and self.dh_slot[team] == i:
                    # PH for the DH is treated as the DH right away (code 10)
                    return 10
                if row.position > 10 and not self.ph_flag:
                    # PH/PR who bat again in the same inning get position 0
                    return 0
                return row.position
        # Pitcher last: the pitcher can bat even though the DH was in effect
        row = self.lineups[0][team]
        if row.player_id is not None and row.player_id == player_id:
            return row.position
        return -1

    # -- responsibility (rule 10.18) --------------------------------------

    def charged_batter(self, batter: str, d: EventData) -> str:
        if d.event_type == Ev.STRIKEOUT and self.strikeout_batter is not None:
            return self.strikeout_batter
        return batter

    def charged_pitcher(self, d: EventData) -> str | None:
        if d.event_type in (Ev.WALK, Ev.INTENTIONALWALK) and self.walk_pitcher:
            return self.walk_pitcher
        return self.fielders[1][1 - self.batting_team]

    def charged_batter_hand(
        self,
        batter: str,
        d: EventData,
        off_roster: Roster | None,
        def_roster: Roster | None,
    ) -> str:
        """``cw_gamestate_charged_batter_hand``"""
        if (
            d.event_type == Ev.STRIKEOUT
            and self.strikeout_batter is not None
            and self.strikeout_batter_hand != " "
        ):
            return self.strikeout_batter_hand
        if self.batter_hand == " ":
            hand = roster_batting_hand(off_roster, self.charged_batter(batter, d))
        else:
            hand = self.batter_hand
        if hand == "B":
            if self.pitcher_hand != " ":
                p = self.pitcher_hand
            else:
                p = roster_throwing_hand(def_roster, self.charged_pitcher(d))
            return "R" if p == "L" else "L" if p == "R" else "?"
        return hand

    def _responsible_base(self, d: EventData, base: int) -> int:
        """Shift responsibility when a preceding runner is put out but a later one scores."""
        if base == 3:
            return 3
        third_fc_out = runner_put_out(d, 3) and d.fc_flag[3]
        if base == 2:
            return 3 if third_fc_out and d.advance[2] >= 4 else 2
        if third_fc_out and d.advance[2] >= 4:
            return 2
        if third_fc_out and not self.base_occupied(2) and d.advance[1] >= 4:
            return 3
        return 1

    def responsible_pitcher(self, d: EventData, base: int) -> str:
        if not self.base_occupied(base):
            return ""
        return self.runners[self._responsible_base(d, base)].pitcher

    def runner_is_auto(self, d: EventData, base: int) -> int:
        if not self.base_occupied(base):
            return 0
        return self.runners[self._responsible_base(d, base)].is_auto

    def responsible_catcher(self, d: EventData, base: int) -> str:
        if not self.base_occupied(base):
            return ""
        return self.runners[self._responsible_base(d, base)].catcher


class GameIter:
    """``CWGameIterator``"""

    def __init__(self, game: Game) -> None:
        self.game = game
        self.index = 0
        self.state = State()
        self.data = EventData()
        self.parse_ok = True
        self._reset()

    @property
    def event(self) -> Event | None:
        return self.game.events[self.index] if self.index < len(self.game.events) else None

    def copy(self) -> "GameIter":
        """``cw_gameiter_copy``"""
        c = GameIter.__new__(GameIter)
        c.game = self.game
        c.index = self.index
        c.state = self.state.copy()
        c.data = _copy_data(self.data)
        c.parse_ok = self.parse_ok
        return c

    def _lineup_setup(self) -> None:
        for s in self.game.starters:
            self.state.lineups[s.slot][s.team] = Slot(s.player_id, s.name, s.pos)
            if s.pos <= 9:
                self.state.fielders[s.pos][s.team] = s.player_id
            elif s.pos == 10:
                self.state.dh_slot[s.team] = s.slot

    def _reset(self) -> None:
        """``cw_gameiter_reset``"""
        self.index = 0
        self.state = State()
        date = self.game.info_lookup("date")
        assert date is not None, "game has no date info record (Chadwick would crash)"
        self.state.date = date[0:4] + date[5:7] + date[8:10]
        self._lineup_setup()
        self.state.batting_team = 1 if self.game.info_lookup("htbf") == "true" else 0
        ev = self.event
        if ev is not None:
            if ev.event_text != "NP":
                self.state.batter_hand = ev.batter_hand
                self.state.pitcher_hand = ev.pitcher_hand
                self.data, self.parse_ok = parse_event(ev.event_text)
            else:
                # very rare: an NP as the first play
                self.parse_ok = True

    def _process_comments(self, ev: Event) -> None:
        """``cw_gameiter_process_comments``: a ``suspended,`` comment changes the date

        The C calls ``strtok`` on the comment text itself, which cuts the shared game record at
        the first comma. The comment is therefore only recognised the first time any iterator
        over this game (a copy made by ``runner_fate``, say) processes it; it is kept.
        """
        for comment in ev.comments:
            if comment.text.startswith("suspended,"):
                tokens = [t for t in comment.text.split(",") if t != ""]
                self.state.date = tokens[1][:8] if len(tokens) > 1 else ""
                comment.text = "suspended"

    def _process_subs(self, ev: Event) -> None:
        for sub in ev.subs:
            self.state.substitute(
                ev.batter, ev.count, sub.player_id, sub.name, sub.team, sub.slot, sub.pos
            )

    def next(self) -> None:
        """``cw_gameiter_next``"""
        ev = self.event
        assert ev is not None
        st = self.state
        if ev.event_text != "NP":
            st.update(ev.batter, self.data)
        else:
            st.batter_hand = ev.batter_hand
            st.pitcher_hand = ev.pitcher_hand

        self._process_comments(ev)
        self._process_subs(ev)

        self.index += 1
        ev = self.event
        if ev is None:
            return

        if st.inning != ev.inning or st.batting_team != ev.batting_team:
            st.change_sides(ev)

        if ev.ladj_slot != 0:
            st.next_batter[st.batting_team] = ev.ladj_slot
        if ev.auto_base != 0:
            assert ev.auto_runner_id is not None  # set together with auto_base by the reader
            st._place_runner(ev.auto_base, ev.auto_runner_id)
        for base in (1, 2, 3):
            pitcher = ev.presadj[base]
            if pitcher is not None:
                st.runners[base].pitcher = pitcher

        if ev.event_text != "NP":
            st.batter_hand = ev.batter_hand
            st.pitcher_hand = ev.pitcher_hand
            self.data, self.parse_ok = parse_event(ev.event_text)
            d = self.data
            for i in (1, 2, 3):
                if d.advance[i] == 0 and st.base_occupied(i) and not runner_put_out(d, i):
                    d.advance[i] = i

            if (d.event_type == Ev.ERROR and st.outs == 2 and d.rbi_flag[3] == 1) or (
                d.event_type in (Ev.WALK, Ev.INTENTIONALWALK)
                and (not st.base_occupied(2) or not st.base_occupied(1))
            ):
                d.rbi_flag[3] = 0

            for i in range(4):
                if d.rbi_flag[i] == 2:
                    d.rbi_flag[i] = 1

    def runner_fate(self, base: int) -> int:
        """``cw_gameiter_runner_fate``: where the runner on ``base`` ends up."""
        adv = self.data.advance[base]
        if adv == 0 or adv >= 4:
            return adv
        base = adv
        gi = self.copy()
        gi.next()
        while (
            gi.event is not None
            and gi.state.inning == self.state.inning
            and gi.state.batting_team == self.state.batting_team
        ):
            if gi.event.event_text != "NP":
                base = gi.data.advance[base]
                if base < 1 or base > 3:
                    break
            gi.next()
        return base

    def future_runs(self) -> int:
        """``cwevent_future_runs``: runs scored after this play in the half inning."""
        runs = 0
        gi = self.copy()
        gi.next()
        while (
            gi.event is not None
            and gi.state.inning == self.state.inning
            and gi.state.batting_team == self.state.batting_team
        ):
            if gi.event.event_text != "NP":
                runs += runs_on_play(gi.data)
            gi.next()
        return runs

    def truncated_pa(self) -> bool:
        """``cwevent_truncated_pa_flag``"""
        if is_batter(self.data):
            return False
        gi = self.copy()
        gi.next()
        while (
            gi.event is not None
            and gi.state.inning == self.state.inning
            and gi.state.batting_team == self.state.batting_team
        ):
            if gi.event.event_text != "NP" and is_batter(gi.data):
                return False
            gi.next()
        return True


def _copy_data(d: EventData) -> EventData:
    """``cw_event_data_copy``"""
    return EventData(
        d.event_type,
        d.advance[:],
        d.rbi_flag[:],
        d.fc_flag[:],
        d.muff_flag[:],
        d.play[:],
        d.sh_flag,
        d.sf_flag,
        d.dp_flag,
        d.gdp_flag,
        d.tp_flag,
        d.wp_flag,
        d.pb_flag,
        d.foul_flag,
        d.bunt_flag,
        d.force_flag,
        d.sb_flag[:],
        d.cs_flag[:],
        d.po_flag[:],
        d.fielded_by,
        d.num_putouts,
        d.num_assists,
        d.num_errors,
        d.num_touches,
        d.putouts[:],
        d.assists[:],
        d.errors[:],
        d.touches[:],
        d.error_types[:],
        d.batted_ball_type,
        d.hit_location,
    )


__all__ = ["Appearance", "GameIter", "Runner", "Slot", "State"]
