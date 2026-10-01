"""Extended ``cwevent`` columns (``-x``): look-ahead and plate-appearance bookkeeping.

``add_game_columns`` finishes the rows of one game once all of its plays are known: which
play ends a half-inning, runs scored later in it, and where each batter and runner ended up.
The pitch-count splits and force-play flags need only one play and are separate functions.
Rules are from Retrosheet's pitch-sequence documentation, corrected against ``cwevent`` output.
"""

from retrosheetpy.play import AdvanceKind, EventKind, Param, ParamKind, Play, PrimaryEvent

SCORED = 4
_BALLS = {
    "B": ("PA_CALLED_BALL_CT",),
    "I": ("PA_INTENT_BALL_CT",),
    "P": ("PA_PITCHOUT_BALL_CT",),
    "H": ("PA_HITBATTER_BALL_CT",),
}
_OTHER_BALL = "V"
_STRIKES = {
    "C": "PA_CALLED_STRIKE_CT",
    "S": "PA_SWINGMISS_STRIKE_CT",
    "M": "PA_SWINGMISS_STRIKE_CT",
    "Q": "PA_SWINGMISS_STRIKE_CT",
    "F": "PA_FOUL_STRIKE_CT",
    "L": "PA_FOUL_STRIKE_CT",
    "O": "PA_FOUL_STRIKE_CT",
    "R": "PA_FOUL_STRIKE_CT",
    "T": "PA_FOUL_STRIKE_CT",
    "X": "PA_INPLAY_STRIKE_CT",
    "Y": "PA_INPLAY_STRIKE_CT",
    "K": "PA_OTHER_STRIKE_CT",
}
PITCH_COLUMNS = (
    "PA_BALL_CT",
    "PA_CALLED_BALL_CT",
    "PA_INTENT_BALL_CT",
    "PA_PITCHOUT_BALL_CT",
    "PA_HITBATTER_BALL_CT",
    "PA_OTHER_BALL_CT",
    "PA_STRIKE_CT",
    "PA_CALLED_STRIKE_CT",
    "PA_SWINGMISS_STRIKE_CT",
    "PA_FOUL_STRIKE_CT",
    "PA_INPLAY_STRIKE_CT",
    "PA_OTHER_STRIKE_CT",
)


def pitch_counts(pitches: str) -> dict[str, str]:
    """Split a pitch sequence into the ball and strike kinds Chadwick counts."""
    count = dict.fromkeys(PITCH_COLUMNS, 0)
    for ch in pitches:
        if ch in _BALLS:
            count["PA_BALL_CT"] += 1
            for column in _BALLS[ch]:
                count[column] += 1
        elif ch == _OTHER_BALL:
            count["PA_OTHER_BALL_CT"] += 1
        elif ch in _STRIKES:
            count["PA_STRIKE_CT"] += 1
            count[_STRIKES[ch]] += 1
    return {k: str(v) for k, v in count.items()}


def force_fields(play: Play, occupied: tuple[bool, bool, bool]) -> dict[str, str]:
    """A forced runner retired in a fielded out sets the flag of the base he was forced at."""
    flags = {2: False, 3: False, 4: False}
    first = play.events[0]
    if {m.code for m in play.modifiers} & {"FO", "GDP"}:
        retired: list[str | None] = [step.runner for step in first.chain if step.runner]
        if first.kind in (EventKind.FIELDED_OUT, EventKind.FIELDERS_CHOICE) and not retired:
            retired = [a.from_base for a in play.advances if a.kind is AdvanceKind.OUT]
        for runner in retired:
            if runner is not None and runner.isdigit() and all(occupied[: int(runner)]):
                flags[int(runner) + 1] = True
    return {f"BASE{base}_FORCE_FL": "T" if on else "F" for base, on in flags.items()}


def safe_on_error(play: Play, batter_event: bool) -> bool:
    """The batter reached base on an error."""
    first = play.events[0]
    if not batter_event:
        return False
    return first.kind is EventKind.ERROR or (
        first.kind is EventKind.FIELDED_OUT
        and any(
            adv.from_base == "B"
            and adv.kind is AdvanceKind.OUT
            and any(p.kind is ParamKind.ERROR for p in adv.params)
            for adv in play.advances
        )
    )


def _unknown_param(params: tuple[Param, ...]) -> bool:
    return any(p.text.partition("/")[0] == "99" for p in params)


def exception_flags(play: Play) -> dict[str, str]:
    """Flags for an out whose fielders are unknown (``99``) and for a ``#`` uncertain play."""
    unknown = False
    for event in play.events:
        node: PrimaryEvent | None = event
        while node is not None:
            unknown = unknown or node.fielders == "99" or _unknown_param(node.params)
            node = node.follow_on
    unknown = unknown or any(_unknown_param(adv.params) for adv in play.advances)
    return {
        "UNKNOWN_OUT_EXC_FL": "T" if unknown else "F",
        "UNCERTAIN_PLAY_EXC_FL": "T" if "#" in play.markers else "F",
    }


def _bases_after(row: dict[str, str]) -> int:
    code = 0
    dests = [row.get(f"RUN{n}_DEST_ID", "") for n in "123"]
    if row.get("BAT_EVENT_FL") == "T":
        dests.append(row["BAT_DEST_ID"])
    for dest in dests:
        if dest in ("1", "2", "3"):
            code |= 1 << (int(dest) - 1)
    return code


def _fate(rows: list[dict[str, str]], i: int, who: str) -> str:
    """Where the runner of ``who`` (``B``, ``1``, ``2`` or ``3``) ended up in the half-inning."""
    key = "BAT_DEST_ID" if who == "B" else f"RUN{who}_DEST_ID"
    dest = rows[i].get(key, "")
    if who == "B" and rows[i].get("BAT_EVENT_FL") != "T":
        return "0"
    while dest in ("1", "2", "3") and i + 1 < len(rows):
        nxt = rows[i + 1]
        if (nxt["INN_CT"], nxt["BAT_HOME_ID"]) != (rows[i]["INN_CT"], rows[i]["BAT_HOME_ID"]):
            break
        i += 1
        dest = rows[i].get(f"RUN{dest}_DEST_ID", "")
    return dest


def add_game_columns(rows: list[dict[str, str]]) -> None:
    """Fill the columns that depend on plays after (or before) each play of one game."""
    pa = [0, 0]
    start = 0
    while start < len(rows):
        end = start
        half = (rows[start]["INN_CT"], rows[start]["BAT_HOME_ID"])
        while end < len(rows) and (rows[end]["INN_CT"], rows[end]["BAT_HOME_ID"]) == half:
            end += 1
        _finish_half(rows, start, end, pa)
        start = end


def _finish_half(rows: list[dict[str, str]], start: int, end: int, pa: list[int]) -> None:
    side = int(rows[start]["BAT_HOME_ID"])
    total = sum(int(r.get("EVENT_RUNS_CT") or 0) for r in rows[start:end])
    last_batter_event = max(
        (i for i in range(start, end) if rows[i].get("BAT_EVENT_FL") == "T"), default=start - 1
    )
    runs = 0
    in_half_pa = 0
    previous_batter_event = True
    for i in range(start, end):
        row = rows[i]
        row["INN_END_FL"] = "T" if i == end - 1 else "F"
        row["INN_RUNS_CT"] = str(runs)
        row["GAME_PA_CT"] = str(pa[side])
        row["INN_PA_CT"] = str(in_half_pa)
        row["PA_NEW_FL"] = "T" if previous_batter_event else "F"
        row["PA_TRUNC_FL"] = "T" if i > last_batter_event else "F"
        row["END_BASES_CD"] = str(_bases_after(row))
        gained = int(row.get("EVENT_RUNS_CT") or 0)
        runs += gained
        row["FATE_RUNS_CT"] = str(total - runs)
        row["BAT_FATE_ID"] = _fate(rows, i, "B")
        for n in "123":
            row[f"RUN{n}_FATE_ID"] = _fate(rows, i, n) if row[f"BASE{n}_RUN_ID"] else "0"
        if row.get("BAT_EVENT_FL") == "T":
            pa[side] += 1
            in_half_pa += 1
        previous_batter_event = row.get("BAT_EVENT_FL") == "T"
