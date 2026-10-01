"""Outcome flags of one play that follow from its text and the resolved movement.

Batter-event, at-bat, foul, double/triple-play and RBI columns. Rules are from
Retrosheet's event-file and scoring documentation, corrected against observed
``cwevent`` output.
"""

from retrosheetpy.play import EventKind, ModifierKind, ParamKind, Play

SCORED = 4
_NO_AB = frozenset(
    {
        EventKind.WALK,
        EventKind.INTENTIONAL_WALK,
        EventKind.HIT_BY_PITCH,
        EventKind.CATCHER_INTERFERENCE,
    }
)
_GROUND_DP = frozenset({"GDP", "BGDP", "BPDP"})
_DP = frozenset({"DP", "GDP", "LDP", "FDP", "BGDP", "BPDP"})
_TP = frozenset({"TP", "GTP", "LTP"})
# No RBI by default for these first events, unless the play text says (RBI).
_NO_DEFAULT_RBI = frozenset(
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


def _flag(value: bool) -> str:
    return "T" if value else "F"


def codes(play: Play) -> set[str]:
    return {m.code for m in play.modifiers if m.kind is ModifierKind.CODE}


def is_foul(play: Play) -> bool:
    """Foul territory: ``FL``, a foul fly error, or a hit location ending in ``F``."""
    if play.events[0].kind is EventKind.FOUL_FLY_ERROR or "FL" in codes(play):
        return True
    return any(m.location is not None and "F" in m.location for m in play.modifiers)


def rbi_count(
    play: Play, batter_event: bool, batter_dest: int, run_dest: tuple[int, int, int]
) -> int:
    """Runs credited as RBI: runs scored, less those marked ``(NR)``, plus forced ``(RBI)``."""
    first = play.events[0].kind
    default = batter_event and first not in _NO_DEFAULT_RBI and not codes(play) & _GROUND_DP
    # A strikeout earns no RBI by itself; after an error only the runner from third counts.
    default = default and first is not EventKind.STRIKEOUT
    marks: dict[str, ParamKind] = {}
    for adv in play.advances:
        for p in adv.params:
            if p.kind in (ParamKind.NO_RBI, ParamKind.RBI) and adv.from_base:
                marks[adv.from_base] = p.kind
    total = 0
    scorers = {"B": batter_dest, "1": run_dest[0], "2": run_dest[1], "3": run_dest[2]}
    for origin, dest in scorers.items():
        if dest < SCORED:
            continue
        mark = marks.get(origin)
        eligible = default and (first is not EventKind.ERROR or origin == "3")
        if mark is ParamKind.RBI or (eligible and mark is not ParamKind.NO_RBI):
            total += 1
    return total


def outcome_fields(
    play: Play, batter_event: bool, batter_dest: int, run_dest: tuple[int, int, int]
) -> dict[str, str]:
    cs = codes(play)
    first = play.events[0].kind
    return {
        "BAT_EVENT_FL": _flag(batter_event),
        "AB_FL": _flag(batter_event and first not in _NO_AB and not cs & {"SH", "SF"}),
        "FOUL_FL": _flag(is_foul(play)),
        "DP_FL": _flag(bool(cs & _DP)),
        "TP_FL": _flag(bool(cs & _TP)),
        "RBI_CT": str(rbi_count(play, batter_event, batter_dest, run_dest)),
    }
