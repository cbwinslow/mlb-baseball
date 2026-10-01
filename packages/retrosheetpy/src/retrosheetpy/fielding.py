"""Fielding credit of one play: who fielded it, errors, putouts and assists.

Rules are from Retrosheet's event-file documentation and are corrected against
observed ``cwevent`` output.
"""

from dataclasses import dataclass, field

from retrosheetpy.play import (
    AdvanceKind,
    EventKind,
    ModifierKind,
    Param,
    ParamKind,
    Play,
    PrimaryEvent,
)

_RUNNER_EVENTS = frozenset(
    {
        EventKind.STOLEN_BASE,
        EventKind.WILD_PITCH,
        EventKind.PASSED_BALL,
        EventKind.BALK,
        EventKind.OTHER_ADVANCE,
        EventKind.DEFENSIVE_INDIFFERENCE,
        EventKind.PICKOFF,
        EventKind.PICKOFF_CAUGHT_STEALING,
    }
)
UNKNOWN_PLAY = "99"
MAX_PUTOUTS = 3
MAX_ASSISTS = 10
MAX_ERRORS = 3


@dataclass
class Credit:
    fielded_by: int = 0
    errors: list[tuple[int, str]] = field(default_factory=list)  # (fielder, F/T/D)
    putouts: list[int] = field(default_factory=list)
    assists: list[int] = field(default_factory=list)


def _digit(ch: str) -> int:
    return 0 if ch == "U" else int(ch)


def _credit_out(credit: Credit, sequence: list[int]) -> None:
    """One out: each fielder who threw to a different fielder assists; the last has the putout."""
    thrown: list[int] = []
    for here, there in zip(sequence, sequence[1:], strict=False):
        if here != there and here not in thrown:
            thrown.append(here)
    credit.assists.extend(thrown)
    credit.putouts.append(sequence[-1])


def _out_credit(credit: Credit, fielders: str) -> None:
    """A runner out with fielders ``54``: all but the last assist, the last has the putout."""
    if fielders != UNKNOWN_PLAY:  # "(99)": fielding unknown, nobody is credited
        _credit_out(credit, [_digit(c) for c in fielders])


def _chain_credit(credit: Credit, event: PrimaryEvent) -> None:
    """Credit a fielded-out chain; the fielder who made one out throws for the next."""
    carry: list[int] = []
    for step in event.chain:
        seq = carry + [_digit(c) for c in step.fielders]
        _credit_out(credit, seq)
        carry = [seq[-1]] if step.runner else []


def _param_error(
    param: Param, pickoff: bool = False, runner_event: bool = False
) -> tuple[int, str] | None:
    text = param.text
    if "E" not in text:
        return None
    before, _, after = text.partition("E")
    fielder = _digit(after[0])
    if "/TH" in after:
        return fielder, "T"
    if before:
        return fielder, "D"
    if pickoff:
        return fielder, "T" if fielder in (1, 2) else "D"
    return fielder, "D" if runner_event else "F"


def _assist_before_error(credit: Credit, params: tuple[Param, ...]) -> None:
    """``5E4``: the fielders before the error threw the ball and are credited with assists."""
    for p in params:
        if p.kind is ParamKind.ERROR and "E" in p.text:
            for ch in p.text.partition("E")[0]:
                if _digit(ch) not in credit.assists:
                    credit.assists.append(_digit(ch))


def _fielding_digits(params: tuple[Param, ...]) -> str:
    for p in params:
        if p.kind is ParamKind.FIELDING:
            return p.text
        if p.kind is ParamKind.FIELDING_THROW:
            return p.text.partition("/")[0]
    return ""


def _primary(credit: Credit, event: PrimaryEvent, play: Play) -> None:
    kind = event.kind
    thrown = any(m.kind is ModifierKind.THROW for m in play.modifiers) or any(
        m.code == "TH" for m in play.modifiers
    )
    if kind is EventKind.FIELDED_OUT and event.fielders == UNKNOWN_PLAY:
        pass  # "99": an out whose fielding is unknown; no one is credited
    elif kind is EventKind.FIELDED_OUT:
        credit.fielded_by = _digit(event.chain[0].fielders[0])
        _chain_credit(credit, event)
    elif kind is EventKind.ERROR:
        assert event.error_fielder is not None
        fielder = _digit(event.error_fielder)
        if event.fielders:
            credit.fielded_by = _digit(event.fielders[0])
            credit.errors.append((fielder, "D"))
            for ch in event.fielders:
                if _digit(ch) not in credit.assists:
                    credit.assists.append(_digit(ch))
        else:
            credit.fielded_by = fielder
            credit.errors.append((fielder, "T" if thrown else "F"))
    elif event.fielders and kind is not EventKind.STRIKEOUT:
        credit.fielded_by = _digit(event.fielders[0])
    if kind is EventKind.FOUL_FLY_ERROR and event.fielders:
        credit.errors.append((_digit(event.fielders), "F"))
    if kind is EventKind.STRIKEOUT and not any(a.from_base == "B" for a in play.advances):
        if event.fielders:
            _out_credit(credit, event.fielders)
        else:
            credit.putouts.append(2)
    if kind in (
        EventKind.CAUGHT_STEALING,
        EventKind.PICKOFF_CAUGHT_STEALING,
        EventKind.PICKOFF,
    ):
        digits = _fielding_digits(event.params)
        errored = any(p.kind is ParamKind.ERROR for p in event.params)
        if digits and not errored:
            _out_credit(credit, digits)
    pickoff = kind in (EventKind.PICKOFF, EventKind.PICKOFF_CAUGHT_STEALING)
    for p in event.params:
        err = _param_error(p, pickoff) if p.kind is ParamKind.ERROR else None
        if err:
            credit.errors.append(err)
    _assist_before_error(credit, event.params)


def credit_for(play: Play) -> Credit:
    credit = Credit()
    first = play.events[0]
    _primary(credit, first, play)
    runner_event = first.kind in _RUNNER_EVENTS
    node = first.follow_on
    while node is not None:
        _primary(credit, node, play)
        node = node.follow_on
    for event in play.events[1:]:
        _primary(credit, event, play)
    for m in play.modifiers:
        if m.kind is ModifierKind.ERROR:
            credit.errors.append((_digit(m.fielders), "F"))
    for adv in play.advances:
        for p in adv.params:
            err = _param_error(p, runner_event=runner_event) if p.kind is ParamKind.ERROR else None
            if err:
                credit.errors.append(err)
        _assist_before_error(credit, adv.params)
        if adv.kind is AdvanceKind.OUT:
            digits = _fielding_digits(adv.params)
            has_credit = any(
                p.kind in (ParamKind.FIELDING, ParamKind.FIELDING_THROW) for p in adv.params
            )
            if digits and (has_credit or not any(p.kind is ParamKind.ERROR for p in adv.params)):
                _out_credit(credit, digits)
    return credit


def fielding_fields(play: Play) -> dict[str, str]:
    credit = credit_for(play)
    row: dict[str, str] = {
        "FLD_CD": str(credit.fielded_by),
        "ERR_CT": str(len(credit.errors)),
    }
    for n in range(1, MAX_ERRORS + 1):
        fielder, kind = credit.errors[n - 1] if n <= len(credit.errors) else (0, "N")
        row[f"ERR{n}_FLD_CD"] = str(fielder)
        row[f"ERR{n}_CD"] = kind
    for n in range(1, MAX_PUTOUTS + 1):
        row[f"PO{n}_FLD_CD"] = str(credit.putouts[n - 1]) if n <= len(credit.putouts) else "0"
    for n in range(1, MAX_ASSISTS + 1):
        row[f"ASS{n}_FLD_CD"] = str(credit.assists[n - 1]) if n <= len(credit.assists) else "0"
    return row
