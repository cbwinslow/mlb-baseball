"""Play-description syntax parser (no game state).

Parses the *event* field of a Retrosheet ``play`` record, e.g.
``S9/L9S.2-H;1-3``, into its syntactic parts: the primary event(s), the
``/`` modifiers and the ``;``-separated runner advances. It never decides what
the play *means* for the game (outs, runs, base state); that belongs to a
separate reducer. Every component keeps the exact source text it came from.

Written from Retrosheet's published event-file documentation
(https://www.retrosheet.org/eventfile.htm) and observed source records.
"""

import re
from collections.abc import Iterator
from dataclasses import dataclass
from enum import StrEnum

from retrosheetpy.errors import ParseError
from retrosheetpy.records import PlayRecord, Record

MARKER_CHARS = "#!?"  # uncertain / exceptional / questionable; documented as ignorable


class EventKind(StrEnum):
    FIELDED_OUT = "fielded_out"
    SINGLE = "single"
    DOUBLE = "double"
    TRIPLE = "triple"
    GROUND_RULE_DOUBLE = "ground_rule_double"
    HOME_RUN = "home_run"
    ERROR = "error"
    FOUL_FLY_ERROR = "foul_fly_error"
    FIELDERS_CHOICE = "fielders_choice"
    HIT_BY_PITCH = "hit_by_pitch"
    STRIKEOUT = "strikeout"
    WALK = "walk"
    INTENTIONAL_WALK = "intentional_walk"
    NO_PLAY = "no_play"
    BALK = "balk"
    DEFENSIVE_INDIFFERENCE = "defensive_indifference"
    OTHER_ADVANCE = "other_advance"
    PASSED_BALL = "passed_ball"
    WILD_PITCH = "wild_pitch"
    STOLEN_BASE = "stolen_base"
    CAUGHT_STEALING = "caught_stealing"
    PICKOFF = "pickoff"
    PICKOFF_CAUGHT_STEALING = "pickoff_caught_stealing"
    CATCHER_INTERFERENCE = "catcher_interference"
    UNKNOWN = "unknown"


class ModifierKind(StrEnum):
    CODE = "code"  # a documented plain code: FO, GDP, SF, ...
    TRAJECTORY = "trajectory"  # G/L/F/P/BG/BP/BL/BF plus an optional hit location
    LOCATION = "location"  # a bare hit location such as 78 or 7LD
    ERROR = "error"  # E$
    THROW = "throw"  # TH or TH%
    RELAY = "relay"  # R$ (one or more fielders)
    UNKNOWN = "unknown"


class AdvanceKind(StrEnum):
    SAFE = "safe"  # a-b
    OUT = "out"  # aXb
    UNKNOWN = "unknown"


class ParamKind(StrEnum):
    FIELDING = "fielding"  # fielders handling the ball, e.g. (26)
    FIELDING_THROW = "fielding_throw"  # fielders plus a throw note, e.g. (826/TH)
    ERROR = "error"  # (E5) or (E5/TH)
    THROW = "throw"  # (TH) (TH3) (THH)
    UNEARNED = "unearned"  # UR, TUR
    NO_RBI = "no_rbi"  # NR, NORBI
    RBI = "rbi"
    WILD_PITCH = "wild_pitch"
    PASSED_BALL = "passed_ball"
    INTERFERENCE = "interference"  # (5/INT)
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class Param:
    """A parenthesised annotation, e.g. ``(E5/TH)`` or ``(UR)``."""

    raw: str  # includes the parentheses
    kind: ParamKind
    text: str  # content between the parentheses, markers removed


@dataclass(frozen=True, slots=True)
class ChainStep:
    """One link of a fielded-out chain: fielders plus an optional runner out ``(1)``."""

    fielders: str
    runner: str | None


@dataclass(frozen=True, slots=True)
class PrimaryEvent:
    raw: str
    kind: EventKind
    fielders: str = ""  # fielders named in the event, in order ("" if none given)
    error_fielder: str | None = None  # E$ events: the fielder charged
    chain: tuple[ChainStep, ...] = ()  # FIELDED_OUT only
    base: str | None = None  # SB / CS / PO / POCS target base
    params: tuple[Param, ...] = ()  # parentheses following SB/CS/PO/POCS
    follow_on: "PrimaryEvent | None" = None  # the event after '+', e.g. K+WP


@dataclass(frozen=True, slots=True)
class Modifier:
    raw: str
    kind: ModifierKind
    code: str = ""  # the code without location/strength markers
    location: str | None = None
    fielders: str = ""  # E$ / R$ fielders
    base: str | None = None  # TH% base
    strength: str | None = None  # "hard" (+) or "soft" (-)


@dataclass(frozen=True, slots=True)
class Advance:
    raw: str
    kind: AdvanceKind
    from_base: str | None = None
    to_base: str | None = None
    params: tuple[Param, ...] = ()


@dataclass(frozen=True, slots=True)
class Play:
    raw: str
    events: tuple[PrimaryEvent, ...]  # >1 only for ';'-joined events such as SB3;SB2
    modifiers: tuple[Modifier, ...]
    advances: tuple[Advance, ...]
    markers: str  # any of '#', '!', '?' found, in order

    def unsupported(self) -> list[str]:
        """Raw text of every component the parser could not classify."""
        return [token for _, token in _unsupported_with_stage(self)]

    def rebuild(self) -> str:
        """Re-join the component raw text; equals ``raw`` for every parsed play."""
        text = ";".join(e.raw for e in self.events)
        text += "".join("/" + m.raw for m in self.modifiers)
        if self.advances:
            text += "." + ";".join(a.raw for a in self.advances)
        return text


# --- tokenising ---------------------------------------------------------------


def _split_top(text: str, sep: str, base: int = 0) -> list[tuple[int, str]]:
    """Split ``text`` on ``sep`` outside parentheses; return (offset, piece) pairs."""
    pieces: list[tuple[int, str]] = []
    depth = 0
    start = 0
    for i, ch in enumerate(text):
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth = max(0, depth - 1)
        elif ch == sep and depth == 0:
            pieces.append((base + start, text[start:i]))
            start = i + 1
    pieces.append((base + start, text[start:]))
    return pieces


def _clean(text: str) -> str:
    return "".join(c for c in text if c not in MARKER_CHARS)


# --- parameters ---------------------------------------------------------------

_P_FIELDING = re.compile(r"[0-9U]+")
_P_FIELDING_THROW = re.compile(r"[0-9U]+/TH[123BH]?")
_P_ERROR = re.compile(r"[0-9U]*E[0-9U]?(?:/TH[123BH]?)?")
_P_THROW = re.compile(r"TH[123BH]?")
_P_INTERFERENCE = re.compile(r"[0-9U]/B?INT")


def _parse_param(raw: str) -> Param:
    text = _clean(raw[1:-1])
    if _P_FIELDING.fullmatch(text):
        kind = ParamKind.FIELDING
    elif _P_FIELDING_THROW.fullmatch(text):
        kind = ParamKind.FIELDING_THROW
    elif _P_ERROR.fullmatch(text):
        kind = ParamKind.ERROR
    elif _P_THROW.fullmatch(text):
        kind = ParamKind.THROW
    elif text in ("UR", "TUR"):
        kind = ParamKind.UNEARNED
    elif text in ("NR", "NORBI"):
        kind = ParamKind.NO_RBI
    elif text == "RBI":
        kind = ParamKind.RBI
    elif text == "WP":
        kind = ParamKind.WILD_PITCH
    elif text == "PB":
        kind = ParamKind.PASSED_BALL
    elif _P_INTERFERENCE.fullmatch(text):
        kind = ParamKind.INTERFERENCE
    else:
        kind = ParamKind.UNKNOWN
    return Param(raw, kind, text)


_PARENS = re.compile(r"\([^()]*\)")


def _parse_params(raw_params: str) -> tuple[Param, ...]:
    return tuple(_parse_param(m.group()) for m in _PARENS.finditer(raw_params))


# --- primary events -----------------------------------------------------------

_F = "[0-9U]"
_CHAIN = re.compile(rf"{_F}+(?:\([B123]\){_F}*)*")
_CHAIN_STEP = re.compile(rf"({_F}+)(?:\(([B123])\))?")
_PARAMS = r"((?:\([^()]*\))*)"
_SIMPLE: list[tuple[re.Pattern[str], EventKind]] = [
    (re.compile(r"NP"), EventKind.NO_PLAY),
    (re.compile(r"BK"), EventKind.BALK),
    (re.compile(r"DI"), EventKind.DEFENSIVE_INDIFFERENCE),
    (re.compile(r"OA"), EventKind.OTHER_ADVANCE),
    (re.compile(r"PB"), EventKind.PASSED_BALL),
    (re.compile(r"WP"), EventKind.WILD_PITCH),
    (re.compile(r"HP"), EventKind.HIT_BY_PITCH),
    (re.compile(r"W"), EventKind.WALK),
    (re.compile(r"IW?"), EventKind.INTENTIONAL_WALK),
    (re.compile(r"C"), EventKind.CATCHER_INTERFERENCE),
]
_WITH_FIELDERS: list[tuple[re.Pattern[str], EventKind]] = [
    (re.compile(rf"DGR({_F}*)"), EventKind.GROUND_RULE_DOUBLE),
    (re.compile(rf"FLE({_F})"), EventKind.FOUL_FLY_ERROR),
    (re.compile(rf"FC({_F}*)"), EventKind.FIELDERS_CHOICE),
    (re.compile(rf"HR?({_F}*)"), EventKind.HOME_RUN),
    (re.compile(rf"S({_F}*)"), EventKind.SINGLE),
    (re.compile(rf"D({_F}*)"), EventKind.DOUBLE),
    (re.compile(rf"T({_F}*)"), EventKind.TRIPLE),
    (re.compile(rf"K({_F}*)"), EventKind.STRIKEOUT),
]
_ERROR_EVENT = re.compile(rf"({_F}*)E({_F})")
_BASE_EVENT = re.compile(rf"(SB|CS|POCS|PO)([123H]){_PARAMS}")


def _parse_event(raw: str) -> PrimaryEvent:
    """Parse one ``;``-separated event, including a ``+`` follow-on event."""
    clean = _clean(raw)
    plus = _split_top(raw, "+")
    if len(plus) > 1:
        head_raw = plus[0][1]
        head = _parse_event(head_raw)
        tail = _parse_event(raw[len(head_raw) + 1 :])
        return PrimaryEvent(
            raw=raw,
            kind=head.kind,
            fielders=head.fielders,
            error_fielder=head.error_fielder,
            chain=head.chain,
            base=head.base,
            params=head.params,
            follow_on=tail,
        )
    for pattern, kind in _SIMPLE:
        if pattern.fullmatch(clean):
            return PrimaryEvent(raw, kind)
    for pattern, kind in _WITH_FIELDERS:
        m = pattern.fullmatch(clean)
        if m:
            return PrimaryEvent(raw, kind, fielders=m.group(1))
    m = _BASE_EVENT.fullmatch(clean)
    if m:
        kinds = {
            "SB": EventKind.STOLEN_BASE,
            "CS": EventKind.CAUGHT_STEALING,
            "PO": EventKind.PICKOFF,
            "POCS": EventKind.PICKOFF_CAUGHT_STEALING,
        }
        return PrimaryEvent(
            raw, kinds[m.group(1)], base=m.group(2), params=_parse_params(m.group(3))
        )
    m = _ERROR_EVENT.fullmatch(clean)
    if m:
        return PrimaryEvent(raw, EventKind.ERROR, fielders=m.group(1), error_fielder=m.group(2))
    if _CHAIN.fullmatch(clean):
        steps = tuple(ChainStep(sm.group(1), sm.group(2)) for sm in _CHAIN_STEP.finditer(clean))
        return PrimaryEvent(
            raw, EventKind.FIELDED_OUT, fielders="".join(s.fielders for s in steps), chain=steps
        )
    return PrimaryEvent(raw, EventKind.UNKNOWN)


# --- modifiers ----------------------------------------------------------------

_KNOWN_CODES = frozenset(
    "AP BP BG BGDP BINT BL BOOT BPDP BR C COUB COUF COUR DP F FDP FINT FL FO G GDP GTP IF INT "
    "IPHR L LDP LTP MREV NDP OBS P PASS RINT SF SH TH TP UINT UREV".split()
)
# Not in the published list but frequent in source files (e.g. K/BF); meaning not interpreted.
_OBSERVED_CODES = frozenset({"BF"})
_M_ERROR = re.compile(r"E([0-9U])")
_M_THROW = re.compile(r"TH([123BH])")
_M_RELAY = re.compile(rf"R({_F}+)")
# BF is not in the published list but is common in source files.
_M_TRAJ = re.compile(r"(BG|BP|BL|BF|G|L|F|P)([0-9]+[A-Z]*)")
_M_LOCATION = re.compile(r"[0-9]+[A-Z]*")


def _parse_modifier(raw: str) -> Modifier:
    text = _clean(raw)
    strength = None
    if text.endswith("+"):
        text, strength = text[:-1], "hard"
    elif text.endswith("-"):
        text, strength = text[:-1], "soft"
    if text in _KNOWN_CODES or text in _OBSERVED_CODES:
        return Modifier(raw, ModifierKind.CODE, code=text, strength=strength)
    m = _M_ERROR.fullmatch(text)
    if m:
        return Modifier(raw, ModifierKind.ERROR, code="E", fielders=m.group(1), strength=strength)
    m = _M_THROW.fullmatch(text)
    if m:
        return Modifier(raw, ModifierKind.THROW, code="TH", base=m.group(1), strength=strength)
    m = _M_RELAY.fullmatch(text)
    if m:
        return Modifier(raw, ModifierKind.RELAY, code="R", fielders=m.group(1), strength=strength)
    m = _M_TRAJ.fullmatch(text)
    if m:
        return Modifier(
            raw, ModifierKind.TRAJECTORY, code=m.group(1), location=m.group(2), strength=strength
        )
    if _M_LOCATION.fullmatch(text):
        return Modifier(raw, ModifierKind.LOCATION, location=text, strength=strength)
    return Modifier(raw, ModifierKind.UNKNOWN)


# --- advances -----------------------------------------------------------------

_ADVANCE = re.compile(rf"([123B])(-|X)([123H]){_PARAMS}")


def _parse_advance(raw: str) -> Advance:
    m = _ADVANCE.fullmatch(_clean(raw))
    if not m:
        return Advance(raw, AdvanceKind.UNKNOWN)
    kind = AdvanceKind.SAFE if m.group(2) == "-" else AdvanceKind.OUT
    return Advance(raw, kind, m.group(1), m.group(3), _parse_params(m.group(4)))


# --- entry points -------------------------------------------------------------


def _where(where: Record | None) -> dict[str, object]:
    if where is None:
        return {"source": "<play>", "line_no": 0, "game_id": None}
    return {"source": where.source, "line_no": where.line_no, "game_id": where.game_id}


def parse_play(event: str, *, strict: bool = True, where: Record | None = None) -> Play:
    """Parse the event field of a play record.

    Strict mode raises ``ParseError`` (stage ``play-event``, ``play-modifier``,
    ``play-advance`` or ``play-param``) on any component it cannot classify.
    Otherwise those components are returned with kind ``UNKNOWN`` and listed by
    ``Play.unsupported()``. Nothing is dropped either way.
    """
    main, dot, adv_text = event.partition(".")
    main_pieces = _split_top(main, "/")
    event_pieces = _split_top(main_pieces[0][1], ";")
    events = tuple(_parse_event(p) for _, p in event_pieces)
    modifiers = tuple(_parse_modifier(p) for _, p in main_pieces[1:])
    advances = tuple(_parse_advance(p) for _, p in _split_top(adv_text, ";")) if dot else ()
    markers = "".join(c for c in event if c in MARKER_CHARS)
    play = Play(event, events, modifiers, advances, markers)
    if strict:
        _raise_first_unsupported(play, where)
    return play


def _raise_first_unsupported(play: Play, where: Record | None) -> None:
    for stage, token in _unsupported_with_stage(play):
        raise ParseError(
            "unsupported play syntax",
            stage=stage,
            record_type="play",
            raw=play.raw,
            token=token,
            offset=play.raw.find(token),
            **_where(where),  # type: ignore[arg-type]
        )


def _unsupported_with_stage(play: Play) -> Iterator[tuple[str, str]]:
    def event(e: PrimaryEvent) -> Iterator[tuple[str, str]]:
        if e.kind is EventKind.UNKNOWN:
            yield "play-event", e.raw
        for p in e.params:
            if p.kind is ParamKind.UNKNOWN:
                yield "play-param", p.raw
        if e.follow_on is not None:
            yield from event(e.follow_on)

    for e in play.events:
        yield from event(e)
    for m in play.modifiers:
        if m.kind is ModifierKind.UNKNOWN:
            yield "play-modifier", m.raw
    for a in play.advances:
        if a.kind is AdvanceKind.UNKNOWN:
            yield "play-advance", a.raw
        for p in a.params:
            if p.kind is ParamKind.UNKNOWN:
                yield "play-param", p.raw


def parse_play_record(record: PlayRecord, *, strict: bool = True) -> Play:
    """Parse ``record.event`` with the record's file/line/game as error context."""
    return parse_play(record.event, strict=strict, where=record)
