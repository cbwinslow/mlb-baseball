"""Game-state engine: one event row per play, with state before and after.

Walks the records of each game in file order. Lineup records (``start``,
``sub``) and adjustment records are applied before the plays that follow them;
each ``play`` record produces one row keyed by ``cwevent`` column names. The
play text is read with ``parse_play`` and turned into runner movement here.

Rules come from Retrosheet's event-file documentation
(https://www.retrosheet.org/eventfile.htm) and are corrected against observed
``cwevent`` output; no Chadwick code is copied. Anything that cannot be
interpreted raises ``ParseError`` (stage ``state``) in strict mode.
"""

from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field, replace

from retrosheetpy.crosswalk import chadwick_fields
from retrosheetpy.errors import ParseError
from retrosheetpy.extended import (
    add_game_columns,
    exception_flags,
    force_fields,
    pitch_counts,
    safe_on_error,
)
from retrosheetpy.fielding import fielding_fields
from retrosheetpy.outcome import outcome_fields
from retrosheetpy.play import (
    AdvanceKind,
    EventKind,
    ModifierKind,
    Param,
    ParamKind,
    Play,
    PrimaryEvent,
    parse_play,
)
from retrosheetpy.playtext import play_text_fields
from retrosheetpy.records import (
    AdjustmentRecord,
    IdRecord,
    InfoRecord,
    PlayRecord,
    Record,
    StartRecord,
    SubRecord,
)

PH, PR, DH = 11, 12, 10
SCORED = 4  # destination code for a run; 5 and 6 are the unearned variants

# Events that are not plate appearances (no batter involved).
_NON_BATTER = frozenset(
    {
        EventKind.STOLEN_BASE,
        EventKind.CAUGHT_STEALING,
        EventKind.PICKOFF,
        EventKind.PICKOFF_CAUGHT_STEALING,
        EventKind.WILD_PITCH,
        EventKind.PASSED_BALL,
        EventKind.BALK,
        EventKind.OTHER_ADVANCE,
        EventKind.DEFENSIVE_INDIFFERENCE,
        EventKind.NO_PLAY,
        EventKind.FOUL_FLY_ERROR,
    }
)
_HIT_BASES = {
    EventKind.SINGLE: 1,
    EventKind.DOUBLE: 2,
    EventKind.GROUND_RULE_DOUBLE: 2,
    EventKind.TRIPLE: 3,
    EventKind.HOME_RUN: 4,
}
_FORCING = frozenset(
    {
        EventKind.WALK,
        EventKind.INTENTIONAL_WALK,
        EventKind.HIT_BY_PITCH,
        EventKind.CATCHER_INTERFERENCE,
    }
)


@dataclass(frozen=True, slots=True)
class Runner:
    player_id: str
    resp_pit: str = ""  # the pitcher charged with this runner
    resp_cat: str = ""  # the catcher on the field when this runner reached base
    origin: int = 0  # event number on which this runner reached base (0 if placed)
    auto: bool = False  # the automatic runner of an extra inning
    position: int = 0  # lineup position code when he reached base (11 pinch hitter, 12 runner)


@dataclass(frozen=True, slots=True)
class Slot:
    player_id: str
    position: int
    fresh: bool = False  # entered as a pinch hitter and has not completed a plate appearance
    replaced: tuple[str, int] | None = None  # (player, position) a pinch hitter took over from
    entered: int = 0  # position the player came into the game at


@dataclass(frozen=True, slots=True)
class Team:
    """Batting order (index 0 is the pitcher slot when a DH is used) and fielders."""

    order: tuple[Slot | None, ...] = (None,) * 10
    fielders: tuple[str | None, ...] = (None,) * 10  # index = position 1..9

    def slot_of(self, player_id: str) -> int | None:
        for i, slot in enumerate(self.order):
            if slot is not None and slot.player_id == player_id:
                return i
        return None


@dataclass(frozen=True, slots=True)
class GameState:
    """Everything the next play depends on. Replaced, never mutated."""

    game_id: str
    away: str
    home: str
    teams: tuple[Team, Team] = (Team(), Team())  # indexed by side: 0 visitor, 1 home
    inning: int = 1
    side: int = 0
    outs: int = 0
    bases: tuple[Runner | None, Runner | None, Runner | None] = (None, None, None)
    score: tuple[int, int] = (0, 0)
    events: int = 0  # emitted rows so far
    half_events: int = 0  # rows so far in this half-inning
    pit_hands: dict[str, str] = field(default_factory=dict)  # pitcher id -> hand (padj)
    pa_batter: str | None = (
        None  # batter announced by an NP line for the plate appearance in progress
    )
    pa_count: str = ""  # the count announced by an NP line for the plate appearance in progress
    pa_pitcher: str | None = None  # pitcher on the field when the count was announced by NP
    uncertain: bool = False  # an earlier play in this game could not be interpreted
    half_pa: int = 0  # plate appearances completed in this half-inning
    pa_hand: str | None = None
    pa_hand_player: str | None = (
        None  # batter hand set by badj for the plate appearance in progress
    )
    pinch_runners: tuple[tuple[int, str] | None, ...] = (
        None,
        None,
        None,
    )  # (base, runner replaced)
    starters: frozenset[str] = frozenset()  # players named in the game's starting lineup
    start_pitchers: frozenset[str] = frozenset()  # the pitchers who started the game
    htbf: bool = False  # the home team bats first
    auto: tuple[int, Runner, str] | None = (
        None  # (base, runner, player he replaced) for the next half
    )


@dataclass(frozen=True, slots=True)
class Moves:
    """What one play did: destinations (0 = out or no runner) and flags."""

    batter_event: bool
    batter_dest: int
    run_dest: tuple[int, int, int]
    outs: int
    runs: int


class StateError(ParseError):
    """The play cannot be applied to the current state."""


def _fail(message: str, rec: Record | None, token: str = "") -> StateError:
    return StateError(
        message,
        stage="state",
        source=rec.source if rec else "<play>",
        line_no=rec.line_no if rec else 0,
        game_id=rec.game_id if rec else None,
        record_type="play",
        raw=rec.raw if rec else token,
        token=token or None,
    )


# --- movement -------------------------------------------------------------------


def _base_number(base: str) -> int:
    return 4 if base == "H" else int(base)


def _safe_on_error(params: tuple[Param, ...]) -> bool:
    """``1X3(4E6)``: an error in the fielding parentheses made the runner safe.

    A separate fielding credit as well, as in ``1XH(E1)(72)``, means the out stood.
    """
    kinds = {p.kind for p in params}
    credited = {ParamKind.FIELDING, ParamKind.FIELDING_THROW}
    return ParamKind.ERROR in kinds and not kinds & credited


def _scored_code(target: int, params: tuple[Param, ...]) -> int:
    """A run is 4; an (UR) mark makes it 5 and (TUR) makes it 6."""
    if target == SCORED and any(p.kind is ParamKind.UNEARNED for p in params):
        return 6 if any(p.text == "TUR" for p in params) else 5
    return target


def _runner_event_moves(
    event: PrimaryEvent, bases: tuple[bool, bool, bool], dest: dict[int, int]
) -> None:
    """Apply the runner effect of a base-running primary event to ``dest``."""
    kind = event.kind
    if event.base is None:
        return
    target = _base_number(event.base)
    origin = target - 1
    safe_by_error = any(p.kind is ParamKind.ERROR for p in event.params)
    if kind is EventKind.STOLEN_BASE and origin in dest:
        dest[origin] = _scored_code(target, event.params)
    elif kind in (EventKind.CAUGHT_STEALING, EventKind.PICKOFF_CAUGHT_STEALING):
        if origin in dest:
            dest[origin] = _scored_code(target, event.params) if safe_by_error else 0
    elif kind is EventKind.PICKOFF and target in dest and not safe_by_error:
        dest[target] = 0


def resolve(
    play: Play, bases: tuple[bool, bool, bool], rec: Record | None = None, outs_before: int = 0
) -> Moves:
    """Work out batter and runner destinations from the play text and occupied bases."""
    first = play.events[0]
    dest: dict[int, int] = {b: b for b in (1, 2, 3) if bases[b - 1]}
    batter_event = first.kind not in _NON_BATTER
    batter = 0
    if first.kind in _HIT_BASES:
        batter = _HIT_BASES[first.kind]
        if batter == SCORED:
            dest = {b: SCORED for b in dest}
    elif first.kind in _FORCING:
        batter = 1
    elif first.kind in (EventKind.ERROR, EventKind.FIELDERS_CHOICE):
        batter = 1
    elif first.kind is EventKind.FIELDED_OUT:
        markers = [s.runner for s in first.chain if s.runner]
        for m in markers:
            if m != "B" and int(m) in dest:
                dest[int(m)] = 0
        last_has_runner = bool(first.chain) and first.chain[-1].runner is not None
        if "B" in markers or not last_has_runner:
            batter = 0
        else:
            batter = 1
    for event in play.events:
        _runner_event_moves(event, bases, dest)
        if event.follow_on is not None:
            _runner_event_moves(event.follow_on, bases, dest)
    for adv in play.advances:
        if adv.kind is AdvanceKind.UNKNOWN or adv.from_base is None or adv.to_base is None:
            raise _fail("unsupported advance", rec, adv.raw)
        target = _scored_code(_base_number(adv.to_base), adv.params)
        # An out advance with an error in its parentheses means the runner was safe.
        out = adv.kind is AdvanceKind.OUT and not _safe_on_error(adv.params)
        if adv.from_base == "B":
            batter = 0 if out else target
            continue
        origin = int(adv.from_base)
        if origin not in dest:
            raise _fail(f"advance from empty base {origin}", rec, adv.raw)
        dest[origin] = 0 if out else target

    def count_outs() -> int:
        return sum(1 for b in dest if dest[b] == 0) + (1 if batter_event and batter == 0 else 0)

    inning_over = outs_before + count_outs() >= 3
    if batter == 1 and batter_event and not inning_over:
        # A batter reaching first pushes the runners ahead of him that nothing else moved.
        for base in (1, 2, 3):
            if dest.get(base) != base:
                break
            dest[base] = base + 1
    claimed = [d for d in (*dest.values(), batter) if 1 <= d <= 3]
    if not inning_over and len(claimed) != len(set(claimed)):
        raise _fail("two runners on one base", rec, play.raw)
    run_dest = (dest.get(1, 0), dest.get(2, 0), dest.get(3, 0))
    outs = count_outs()
    runs = sum(1 for d in (*run_dest, batter) if d >= SCORED)
    return Moves(batter_event, batter, run_dest, outs, runs)


# --- the engine -----------------------------------------------------------------


def _set_player(team: Team, rec: StartRecord | SubRecord) -> Team:
    order = list(team.order)
    fielders = list(team.fielders)
    old = order[rec.batting_order]
    elsewhere = team.slot_of(rec.player_id)
    if elsewhere is not None and elsewhere != rec.batting_order:
        order[elsewhere] = None  # the pitcher who goes to bat in a DH slot leaves the pitcher slot
    position = rec.position
    if position in (PH, PR) and old is not None and old.position == DH and elsewhere is None:
        position = DH  # a pinch hitter or runner for the DH takes over as the DH
    replaced = (old.player_id, old.entered) if old is not None and rec.position == PH else None
    order[rec.batting_order] = Slot(
        rec.player_id,
        position,
        fresh=rec.position == PH,
        replaced=replaced,
        entered=position if rec.position == PR else rec.position,
    )
    if 1 <= rec.position <= 9:
        fielders[rec.position] = rec.player_id
    return replace(team, order=tuple(order), fielders=tuple(fielders))


def _start_bases(
    auto: tuple[int, Runner, str] | None,
) -> tuple[Runner | None, Runner | None, Runner | None]:
    bases: list[Runner | None] = [None, None, None]
    if auto is not None:
        bases[auto[0] - 1] = auto[1]
    return (bases[0], bases[1], bases[2])


def _start_marks(
    auto: tuple[int, Runner, str] | None,
) -> tuple[tuple[int, str] | None, ...]:
    marks: list[tuple[int, str] | None] = [None, None, None]
    if auto is not None and auto[2]:
        marks[auto[0] - 1] = (auto[0], auto[2])
    return tuple(marks)


def _place_auto_runner(state: GameState, player_id: str, base: int) -> GameState:
    """Record the automatic runner who starts the coming extra half-inning on ``base``."""
    side = 0 if state.teams[0].slot_of(player_id) is not None else 1
    team, fielding = state.teams[side], state.teams[1 - side]
    seat = team.slot_of(player_id)
    listed = team.order[seat] if seat is not None else None
    runner = Runner(
        player_id,
        resp_pit=fielding.fielders[1] or "",
        resp_cat=fielding.fielders[2] or "",
        auto=True,
        position=listed.position if listed else 0,
    )
    return replace(state, auto=(base, runner, ""))


def _replace_runner(state: GameState, old: str, new: str, team: int) -> GameState:
    """A substitute takes over the base of the player he replaced (pinch runner)."""
    bases = list(state.bases)
    marks = list(state.pinch_runners)
    if state.auto is not None and state.auto[1].player_id == old:
        base, auto_runner, _ = state.auto
        roster = state.teams[team]
        seat = roster.slot_of(new)
        listed = roster.order[seat] if seat is not None else None
        pinch = replace(auto_runner, player_id=new, position=listed.position if listed else 0)
        state = replace(state, auto=(base, pinch, old))
    for i, runner in enumerate(bases):
        if team == state.side and runner is not None and runner.player_id == old:
            seat = state.teams[state.side].slot_of(new)
            listed = state.teams[state.side].order[seat] if seat is not None else None
            bases[i] = replace(runner, player_id=new, position=listed.position if listed else 0)
            marks[i] = (i + 1, old)
    return replace(
        state,
        bases=(bases[0], bases[1], bases[2]),
        pinch_runners=(marks[0], marks[1], marks[2]),
    )


def event_rows(records: Iterable[Record], *, strict: bool = True) -> Iterator[dict[str, str]]:
    """Yield one ``cwevent``-named row per play record (``NP`` is not emitted)."""
    info: dict[str, str] = {}
    state: GameState | None = None
    pending: list[tuple[PlayRecord, dict[str, str]]] = []
    for rec in records:
        if isinstance(rec, IdRecord):
            if pending:
                yield from _flush(pending)
                pending = []
            info, state = {}, None
        elif isinstance(rec, InfoRecord):
            info[rec.key] = rec.value
        elif isinstance(rec, (StartRecord, SubRecord)):
            if state is None:
                state = GameState(
                    rec.game_id or "",
                    info.get("visteam", ""),
                    info.get("hometeam", ""),
                    htbf=info.get("htbf") == "true",
                )
            teams = list(state.teams)
            if isinstance(rec, StartRecord):
                state = replace(
                    state,
                    starters=state.starters | {rec.player_id},
                    start_pitchers=state.start_pitchers
                    | ({rec.player_id} if rec.position == 1 else set()),
                )
            replaced = teams[rec.team].order[rec.batting_order]
            teams[rec.team] = _set_player(teams[rec.team], rec)
            state = replace(state, teams=(teams[0], teams[1]))
            if isinstance(rec, SubRecord) and replaced is not None:
                state = _replace_runner(state, replaced.player_id, rec.player_id, rec.team)
        elif isinstance(rec, AdjustmentRecord):
            if state is not None and len(rec.fields) == 2:
                if rec.kind == "badj":
                    state = replace(state, pa_hand=rec.fields[1], pa_hand_player=rec.fields[0])
                elif rec.kind == "presadj" and rec.fields[1] in ("1", "2", "3"):
                    base = int(rec.fields[1]) - 1
                    runner = state.bases[base]
                    if runner is not None:
                        bases = list(state.bases)
                        bases[base] = replace(runner, resp_pit=rec.fields[0])
                        state = replace(state, bases=(bases[0], bases[1], bases[2]))
                elif rec.kind == "radj" and rec.fields[1] in ("1", "2", "3"):
                    state = _place_auto_runner(state, rec.fields[0], int(rec.fields[1]))
                elif rec.kind == "padj":
                    state = replace(
                        state, pit_hands={**state.pit_hands, rec.fields[0]: rec.fields[1]}
                    )
        elif isinstance(rec, PlayRecord) and rec.event == "NP":
            # A pinch hitter inherits the count, but the batter who started it stays responsible.
            if state is not None and rec.count.isdigit() and rec.count != "00":
                balls, strikes = int(rec.count[0]), int(rec.count[1])
                # A reliever is not charged with a walk on a count of 2-0, 2-1, 3-0, 3-1, 3-2.
                charged_back = balls >= 2 and balls > strikes
                pitcher = state.teams[1 - rec.team].fielders[1] if charged_back else None
                state = replace(
                    state, pa_batter=rec.player_id, pa_pitcher=pitcher, pa_count=rec.count
                )
        elif isinstance(rec, PlayRecord):
            if state is None:
                raise _fail("play before any lineup record", rec)
            state, row = _play_row(state, rec, strict)
            pending.append((rec, row))
    yield from _flush(pending)


def _flush(pending: list[tuple[PlayRecord, dict[str, str]]]) -> Iterator[dict[str, str]]:
    rows = [row for _, row in pending]
    for i, row in enumerate(rows):
        row["GAME_END_FL"] = "T" if i == len(rows) - 1 else "F"
    add_game_columns(rows)
    yield from rows


def _play_row(state: GameState, rec: PlayRecord, strict: bool) -> tuple[GameState, dict[str, str]]:
    if (rec.inning, rec.team) != (state.inning, state.side):
        # A pinch hitter who did not finish a plate appearance in his half-inning is no longer
        # flagged as one.
        gone = state.teams[state.side]
        stale = tuple(replace(x, fresh=False) if x and x.fresh else x for x in gone.order)
        teams = list(state.teams)
        teams[state.side] = replace(gone, order=stale)
        state = replace(state, teams=(teams[0], teams[1]))
        state = replace(
            state,
            inning=rec.inning,
            side=rec.team,
            outs=0,
            bases=_start_bases(state.auto),
            auto=None,
            half_events=0,
            half_pa=0,
            pinch_runners=_start_marks(state.auto),
        )
    batting, fielding = state.teams[state.side], state.teams[1 - state.side]
    slot = batting.slot_of(rec.player_id)
    if slot is None:
        raise _fail(f"batter {rec.player_id} is not in the lineup", rec)
    occupied = (state.bases[0] is not None, state.bases[1] is not None, state.bases[2] is not None)
    play: Play | None = None
    moves: Moves | None = None
    unsupported = ""
    try:
        play = parse_play(rec.event, strict=strict, where=rec)
        if play.unsupported():
            raise _fail("unsupported play syntax", rec, play.unsupported()[0])
        moves = resolve(play, occupied, rec, state.outs)
    except ParseError as exc:
        if strict:
            raise
        unsupported = f"{exc.stage}: {exc.message}"
    first_kind = play.events[0].kind if play else None
    # A substitute batter finishing a count of 2 strikes by strikeout, or of 3 balls (and fewer
    # than 2 strikes) by walk, is not charged with it: the batter who started the count is.
    decided = (first_kind is EventKind.STRIKEOUT and state.pa_count[1:] == "2") or (
        first_kind is EventKind.WALK and state.pa_count[:1] == "3" and state.pa_count[1:] != "2"
    )
    resp_bat = state.pa_batter if decided else None
    resp_bat = resp_bat or rec.player_id
    resp_pit = (
        state.pa_pitcher if first_kind in (EventKind.WALK, EventKind.INTENTIONAL_WALK) else None
    )
    resp_pit = resp_pit or fielding.fielders[1] or ""
    batter_pos = batting.order[slot].position  # type: ignore[union-attr]
    row: dict[str, str] = {
        "GAME_ID": state.game_id,
        "AWAY_TEAM_ID": state.away,
        "INN_CT": str(state.inning),
        "BAT_HOME_ID": str(state.side),
        "OUTS_CT": str(state.outs),
        "BALLS_CT": rec.count[:1] if rec.count[:1].isdigit() else "0",
        "STRIKES_CT": rec.count[1:2] if rec.count[1:2].isdigit() else "0",
        "PITCH_SEQ_TX": rec.pitches,
        "AWAY_SCORE_CT": str(state.score[0]),
        "HOME_SCORE_CT": str(state.score[1]),
        "BAT_ID": rec.player_id,
        "RESP_BAT_ID": resp_bat,
        "PIT_ID": fielding.fielders[1] or "",
        "RESP_PIT_ID": resp_pit,
        "BASE1_RUN_ID": state.bases[0].player_id if state.bases[0] else "",
        "BASE2_RUN_ID": state.bases[1].player_id if state.bases[1] else "",
        "BASE3_RUN_ID": state.bases[2].player_id if state.bases[2] else "",
        "EVENT_TX": rec.event,
        "LEADOFF_FL": "T" if state.half_pa == 0 else "F",
        "PH_FL": "T" if batting.order[slot].fresh else "F",  # type: ignore[union-attr]
        "BAT_FLD_CD": str(
            0 if batter_pos == PR else batter_pos
        ),  # a runner batting has no position
        "BAT_LINEUP_ID": str(slot),
        "EVENT_OUTS_CT": str(moves.outs) if moves else "",
        "BAT_DEST_ID": (str(moves.batter_dest if moves.batter_event else 0) if moves else ""),
        "RUN1_DEST_ID": str(moves.run_dest[0]) if moves else "",
        "RUN2_DEST_ID": str(moves.run_dest[1]) if moves else "",
        "RUN3_DEST_ID": str(moves.run_dest[2]) if moves else "",
        "EVENT_RUNS_CT": str(moves.runs) if moves else "",
        "UNSUPPORTED": unsupported,
        "STATE_UNCERTAIN": "T" if state.uncertain else "F",
        "GAME_NEW_FL": "T" if state.events == 0 else "F",
        "EVENT_ID": str(state.events + 1),
    }
    if play is not None and moves is not None:
        row.update(outcome_fields(play, moves.batter_event, moves.batter_dest, moves.run_dest))
        row.update(fielding_fields(play))
        row.update(play_text_fields(play))
        row.update({"BATTEDBALL_CD": "", "BATTEDBALL_LOC_TX": ""})
        row.update({k: str(v) for k, v in chadwick_fields(play).items()})
        if not row["BATTEDBALL_CD"]:
            row["BATTEDBALL_CD"] = _inferred_battedball(play)
        row.update(force_fields(play, occupied))
        row.update(exception_flags(play))
        row["BAT_SAFE_ERR_FL"] = "T" if safe_on_error(play, moves.batter_event) else "F"
    batter_slot = batting.order[slot]
    assert batter_slot is not None
    removed = batter_slot.replaced if batter_slot.fresh else None
    row["REMOVED_FOR_PH_BAT_ID"] = removed[0] if removed else ""
    row["REMOVED_FOR_PH_BAT_FLD_CD"] = str(removed[1]) if removed else "0"
    for n in (1, 2, 3):
        mark = state.pinch_runners[n - 1]
        runner = state.bases[n - 1]
        row[f"PR_RUN{n}_FL"] = "T" if mark else "F"
        row[f"REMOVED_FOR_PR_RUN{n}_ID"] = mark[1] if mark else ""
        row[f"RUN{n}_RESP_PIT_ID"] = runner.resp_pit if runner else ""
    for pos in range(2, 10):
        row[f"POS{pos}_FLD_ID"] = fielding.fielders[pos] or ""
    bat_team, fld_team = (state.home, state.away) if state.side else (state.away, state.home)
    row["HOME_TEAM_ID"] = state.home
    row["BAT_TEAM_ID"] = bat_team
    row["FLD_TEAM_ID"] = fld_team
    row["BAT_LAST_ID"] = str(state.side ^ int(state.htbf))
    row["INN_NEW_FL"] = "T" if state.half_events == 0 else "F"
    row["START_BAT_SCORE_CT"] = str(state.score[state.side])
    row["START_FLD_SCORE_CT"] = str(state.score[1 - state.side])
    row["START_BASES_CD"] = str(sum(1 << i for i, on in enumerate(occupied) if on))
    row["BAT_START_FL"] = "T" if rec.player_id in state.starters else "F"
    row["RESP_BAT_START_FL"] = "T" if resp_bat in state.starters else "F"
    row["PIT_START_FL"] = "T" if fielding.fielders[1] in state.start_pitchers else "F"
    row["RESP_PIT_START_FL"] = "T" if resp_pit in state.start_pitchers else "F"
    for name, offset in (("BAT_ON_DECK_ID", 1), ("BAT_IN_HOLD_ID", 2)):
        coming = batting.order[(slot - 1 + offset) % 9 + 1]
        row[name] = coming.player_id if coming else ""
    row["COUNT_TX"] = rec.count
    row.update(pitch_counts(rec.pitches))
    fielded = int(row.get("FLD_CD") or 0)
    row["FLD_ID"] = (fielding.fielders[fielded] or "") if 1 <= fielded <= 9 else ""
    for n in (1, 2, 3):
        runner = state.bases[n - 1]
        runner_slot = batting.slot_of(runner.player_id) if runner else None
        row[f"RUN{n}_LINEUP_CD"] = str(runner_slot or 0)
        # A pinch hitter or runner is listed at his position only while a pinch hitter bats.
        listed = runner.position if runner else 0
        row[f"RUN{n}_FLD_CD"] = str(0 if listed > DH and row["PH_FL"] == "F" else listed)
        row[f"RUN{n}_ORIGIN_EVENT_ID"] = str(runner.origin) if runner else "0"
        row[f"RUN{n}_RESP_CAT_ID"] = runner.resp_cat if runner else ""
        row[f"RUN{n}_AUTO_FL"] = "T" if runner and runner.auto else "F"
    pa_hand = state.pa_hand or "?"
    row["RESP_BAT_HAND_CD"] = pa_hand
    row["BAT_HAND_CD"] = pa_hand if state.pa_hand_player == rec.player_id else "?"
    row["PIT_HAND_CD"] = state.pit_hands.get(fielding.fielders[1] or "", "?")
    row["RESP_PIT_HAND_CD"] = state.pit_hands.get(row["RESP_PIT_ID"], "?")
    if moves is None:
        # The play was not understood, so nothing about the state after it is known.
        uncertain = replace(state, events=state.events + 1, uncertain=True)
        return uncertain, row
    choice = first_kind is EventKind.FIELDERS_CHOICE or (
        play is not None and any(step.runner for step in play.events[0].chain)
    )
    return (
        _after_play(state, rec, moves, slot, row["RESP_PIT_ID"], choice, batter_pos),
        row,
    )


def _shift_pitchers(state: GameState, moves: Moves, new_bases: list[Runner | None]) -> None:
    """A runner retired on a ball in play passes his pitcher back to those behind him.

    Runners still on base, lead runner first, take the pitchers of the runners who were on
    base before the play (those who scored leave theirs behind). A batter who reaches thus
    ends up with the pitcher of the runner he replaced and his own pitcher drops out. The
    automatic-runner mark travels with them, except that after a double play the batter
    does not take it.
    """
    if not any(r is not None and d == 0 for r, d in zip(state.bases, moves.run_dest, strict=True)):
        return
    retired = sum(
        r is not None and d == 0 for r, d in zip(state.bases, moves.run_dest, strict=True)
    )
    pool = [
        (runner.resp_pit, runner.resp_cat, runner.auto)
        for runner, d in zip(reversed(state.bases), reversed(moves.run_dest), strict=True)
        if runner is not None and d < SCORED
    ]
    survivors = [b for b in (2, 1, 0) if new_bases[b] is not None]
    for i, base in enumerate(survivors):
        runner = new_bases[base]
        assert runner is not None
        inherits = retired == 1 or runner.origin != state.events + 1
        new_bases[base] = replace(
            runner, resp_pit=pool[i][0], resp_cat=pool[i][1], auto=pool[i][2] and inherits
        )


def _inferred_battedball(play: Play) -> str:
    """The batted-ball type of a play with no trajectory in the text.

    A fielder's choice is a ground ball; so is an error, unless an outfielder made it (then a
    fly ball). A foul fly error is a pop-up, or a fly ball if an outfielder dropped it. An out
    is a pop-up on an infield fly, a line drive on a line-drive double play, a ground ball on
    a sacrifice bunt, a force out, a ground-ball double or triple play, or an out with more
    than one fielder (so also an unknown `99`), and otherwise a fly ball.
    """
    first = play.events[0]
    if first.kind is EventKind.FIELDERS_CHOICE:
        return "G"
    if first.kind is EventKind.ERROR:
        return "F" if (first.error_fielder or "0") >= "7" else "G"
    if first.kind is EventKind.FOUL_FLY_ERROR:
        return "F" if first.fielders >= "7" else "P"
    if first.kind is not EventKind.FIELDED_OUT:
        return ""
    codes = {m.code for m in play.modifiers}
    if "IF" in codes:
        return "P"
    if "LDP" in codes:
        return "L"
    if codes & {"SH", "FO", "GDP", "GTP"} or len(first.chain[0].fielders) > 1:
        return "G"
    return "F"


def _after_play(
    state: GameState,
    rec: PlayRecord,
    moves: Moves,
    slot: int,
    resp_pit: str,
    choice: bool,
    batter_position: int,
) -> GameState:
    """The state once ``moves`` have happened."""
    new_bases: list[Runner | None] = [None, None, None]
    for base in (1, 2, 3):
        runner = state.bases[base - 1]
        d = moves.run_dest[base - 1]
        if runner is not None and 1 <= d <= 3:
            new_bases[d - 1] = runner
    if moves.batter_event and 1 <= moves.batter_dest <= 3:
        catcher = state.teams[1 - state.side].fielders[2] or ""
        new_bases[moves.batter_dest - 1] = Runner(
            rec.player_id, resp_pit, catcher, state.events + 1, position=batter_position
        )
    if choice:
        _shift_pitchers(state, moves, new_bases)
    batting = state.teams[state.side]
    if moves.batter_event:
        order = list(batting.order)
        done = order[slot]
        assert done is not None
        position = 0 if done.position == PH else done.position
        order[slot] = replace(done, position=position, fresh=False, entered=position)
        teams = list(state.teams)
        teams[state.side] = replace(batting, order=tuple(order))
        state = replace(state, teams=(teams[0], teams[1]))
    score = list(state.score)
    score[state.side] += moves.runs
    ended = moves.batter_event
    return replace(
        state,
        outs=state.outs + moves.outs,
        bases=(new_bases[0], new_bases[1], new_bases[2]),
        score=(score[0], score[1]),
        events=state.events + 1,
        half_events=state.half_events + 1,
        pa_batter=None if ended else state.pa_batter,
        pa_pitcher=None if ended else state.pa_pitcher,
        pa_count="" if ended else state.pa_count,
        pa_hand=None if ended else state.pa_hand,
        half_pa=state.half_pa + (1 if ended else 0),
        pinch_runners=(None, None, None),
    )


__all__ = ["GameState", "ModifierKind", "Moves", "StateError", "event_rows", "resolve"]
