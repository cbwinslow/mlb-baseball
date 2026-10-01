"""Fields that can be read straight from one play string (no game state).

Retrosheet's yearly ``plays`` CSV and Chadwick's ``cwevent`` both publish
columns that follow from the play text alone (event type, hit kind, batted-ball
type, steal/pickoff flags...). Columns that need game state (outs, base
occupancy, runs, RBI, putout/assist credit) are deliberately not derived here.

``csv_fields`` uses the column names of Retrosheet's ``plays.csv``
(https://www.retrosheet.org/downloads/csvcontents.html). ``chadwick_fields``
uses the ``cwevent -d`` field names. Both are used only to *check* the parser;
no Chadwick source is copied, the rules come from the Retrosheet documentation
and are corrected against observed reference output.
"""

from retrosheetpy.play import EventKind, ModifierKind, ParamKind, Play, PrimaryEvent

_HIT_BASES = {
    EventKind.SINGLE: 1,
    EventKind.DOUBLE: 2,
    EventKind.GROUND_RULE_DOUBLE: 2,
    EventKind.TRIPLE: 3,
    EventKind.HOME_RUN: 4,
}

# cwevent EVENT_CD values (documented by `cwevent -d` / Chadwick documentation).
_EVENT_CD = {
    EventKind.FIELDED_OUT: 2,
    EventKind.STRIKEOUT: 3,
    EventKind.STOLEN_BASE: 4,
    EventKind.DEFENSIVE_INDIFFERENCE: 5,
    EventKind.CAUGHT_STEALING: 6,
    # cwevent 0.10.0 emits 8 for both PO and POCS (code 7, "pickoff error", never
    # occurred in 2019 reference output), so both map to 8.
    EventKind.PICKOFF: 8,
    EventKind.PICKOFF_CAUGHT_STEALING: 8,
    EventKind.WILD_PITCH: 9,
    EventKind.PASSED_BALL: 10,
    EventKind.BALK: 11,
    EventKind.OTHER_ADVANCE: 12,
    EventKind.FOUL_FLY_ERROR: 13,
    EventKind.WALK: 14,
    EventKind.INTENTIONAL_WALK: 15,
    EventKind.HIT_BY_PITCH: 16,
    EventKind.CATCHER_INTERFERENCE: 17,
    EventKind.ERROR: 18,
    EventKind.FIELDERS_CHOICE: 19,
    EventKind.SINGLE: 20,
    EventKind.DOUBLE: 21,
    EventKind.GROUND_RULE_DOUBLE: 21,
    EventKind.TRIPLE: 22,
    EventKind.HOME_RUN: 23,
}


def _event_cd(event: PrimaryEvent) -> int:
    # cwevent 0.10.0 reports "5E3" (fielder, then an error) as a generic out (2)
    # although the batter may reach; plain "E3" is an error (18).
    if event.kind is EventKind.ERROR and event.fielders:
        return 2
    return _EVENT_CD.get(event.kind, 0)


def _all_events(play: Play) -> list[PrimaryEvent]:
    """Every primary event including ``+`` follow-ons, in source order."""
    out: list[PrimaryEvent] = []
    for e in play.events:
        node: PrimaryEvent | None = e
        while node is not None:
            out.append(node)
            node = node.follow_on
    return out


def _codes(play: Play) -> set[str]:
    return {m.code for m in play.modifiers if m.kind is ModifierKind.CODE}


_TRAJECTORY_CODES = frozenset({"BG", "BP", "BL", "BF", "G", "L", "F", "P"})


def _trajectory(play: Play) -> tuple[str, str]:
    """``(code, location)`` of the first trajectory/location modifier, else ``("", "")``.

    A bare ``/P`` or ``/BG`` is parsed as a plain code; it is still a trajectory.
    """
    code = ""
    for m in play.modifiers:
        if m.kind is ModifierKind.TRAJECTORY:
            return m.code, m.location or ""
        if not code and m.kind is ModifierKind.CODE and m.code in _TRAJECTORY_CODES:
            code = m.code
    # A bare trajectory code may be followed by a separate location modifier (``HR/7/L``).
    for m in play.modifiers:
        if m.kind is ModifierKind.LOCATION:
            return code, m.location or ""
    return code, ""


def _advance_flag(play: Play, kind: ParamKind) -> bool:
    """True if a runner-advance parameter such as ``(WP)`` or ``(PB)`` is present."""
    return any(p.kind is kind for a in play.advances for p in a.params)


_ORIGIN = {"2": "1", "3": "2", "H": "3"}


def _picked_bases(play: Play) -> list[str]:
    """Bases the picked-off runners *occupied*: ``PO1`` -> 1, ``POCS2`` -> 1 (the steal origin)."""
    return _bases(play, EventKind.PICKOFF) + [
        _ORIGIN[b] for b in _bases(play, EventKind.PICKOFF_CAUGHT_STEALING)
    ]


def _bases(play: Play, kind: EventKind) -> list[str]:
    return [e.base for e in _all_events(play) if e.kind is kind and e.base]


def _is_bunt(traj: str, codes: set[str]) -> bool:
    # BGDP/BPDP are bunt double plays (observed in 1915-1985 reference output).
    return traj.startswith("B") or bool(codes & {"SH", "BGDP", "BPDP"})


def _battedball(traj: str, codes: set[str]) -> str:
    """cwevent BATTEDBALL_CD for an explicit trajectory; an infield fly is a pop-up."""
    if traj == "F" and "IF" in codes:
        return "P"
    return traj[-1]


def csv_fields(play: Play) -> dict[str, int | str]:
    """Stateless columns of Retrosheet's ``plays.csv`` derivable from ``play``."""
    events = _all_events(play)
    kinds = {e.kind for e in events}
    first = play.events[0].kind
    codes = _codes(play)
    traj, loc = _trajectory(play)
    bunt = _is_bunt(traj, codes)
    fields: dict[str, int | str] = {
        "single": int(first is EventKind.SINGLE),
        "double": int(first in (EventKind.DOUBLE, EventKind.GROUND_RULE_DOUBLE)),
        "triple": int(first is EventKind.TRIPLE),
        "hr": int(first is EventKind.HOME_RUN),
        "sh": int("SH" in codes),
        "sf": int("SF" in codes),
        "hbp": int(first is EventKind.HIT_BY_PITCH),
        "walk": int(first in (EventKind.WALK, EventKind.INTENTIONAL_WALK)),
        "iw": int(first is EventKind.INTENTIONAL_WALK),
        "k": int(first is EventKind.STRIKEOUT),
        "fle": int(first is EventKind.FOUL_FLY_ERROR),
        "wp": int(EventKind.WILD_PITCH in kinds or _advance_flag(play, ParamKind.WILD_PITCH)),
        "pb": int(EventKind.PASSED_BALL in kinds or _advance_flag(play, ParamKind.PASSED_BALL)),
        "bk": int(EventKind.BALK in kinds),
        "di": int(first is EventKind.DEFENSIVE_INDIFFERENCE),
        "bunt": int(bunt),
    }
    if traj:
        # Only an explicit trajectory modifier is read from the text; the CSV also
        # infers a type/location for plays without one, which is not derivable here.
        # The CSV flags are mutually exclusive: a bunt ground ball is bunt, not ground.
        fields["ground"] = int(traj == "G")
        fields["fly"] = int(traj in ("F", "P"))
        fields["line"] = int(traj == "L")
        fields["hittype"] = traj
    if loc:
        fields["loc"] = loc
    stolen = _bases(play, EventKind.STOLEN_BASE)
    caught = _bases(play, EventKind.CAUGHT_STEALING) + _bases(
        play, EventKind.PICKOFF_CAUGHT_STEALING
    )
    # The CSV books a POCS as a caught stealing only, unlike cwevent which also sets PK.
    picked = _bases(play, EventKind.PICKOFF)
    for base, name in (("2", "2"), ("3", "3"), ("H", "h")):
        fields[f"sb{name}"] = int(base in stolen)
        fields[f"cs{name}"] = int(base in caught)
    for base in "123":
        fields[f"pko{base}"] = int(base in picked)
    return fields


def chadwick_fields(play: Play) -> dict[str, int | str]:
    """Stateless ``cwevent`` columns derivable from ``play`` (names as in ``cwevent -d``)."""
    first = play.events[0].kind
    codes = _codes(play)
    traj, loc = _trajectory(play)
    stolen = _bases(play, EventKind.STOLEN_BASE)
    caught = _bases(play, EventKind.CAUGHT_STEALING) + _bases(
        play, EventKind.PICKOFF_CAUGHT_STEALING
    )
    picked = _picked_bases(play)
    kinds = {e.kind for e in _all_events(play)}
    wild_pitch = EventKind.WILD_PITCH in kinds or _advance_flag(play, ParamKind.WILD_PITCH)
    passed_ball = EventKind.PASSED_BALL in kinds or _advance_flag(play, ParamKind.PASSED_BALL)
    fields: dict[str, int | str] = {
        "EVENT_CD": _event_cd(play.events[0]),
        "H_CD": _HIT_BASES.get(first, 0),
        "SH_FL": "T" if "SH" in codes else "F",
        "SF_FL": "T" if "SF" in codes else "F",
        "WP_FL": "T" if wild_pitch else "F",
        "PB_FL": "T" if passed_ball else "F",
        "BUNT_FL": "T" if _is_bunt(traj, codes) else "F",
        "RUN1_SB_FL": "T" if "2" in stolen else "F",
        "RUN2_SB_FL": "T" if "3" in stolen else "F",
        "RUN3_SB_FL": "T" if "H" in stolen else "F",
        "RUN1_CS_FL": "T" if "2" in caught else "F",
        "RUN2_CS_FL": "T" if "3" in caught else "F",
        "RUN3_CS_FL": "T" if "H" in caught else "F",
        "RUN1_PK_FL": "T" if "1" in picked else "F",
        "RUN2_PK_FL": "T" if "2" in picked else "F",
        "RUN3_PK_FL": "T" if "3" in picked else "F",
    }
    if traj and traj != "BF":
        fields["BATTEDBALL_CD"] = _battedball(traj, codes)
    if loc:
        fields["BATTEDBALL_LOC_TX"] = loc
    return fields
