"""Fielding text of each out or attempt: ``BAT_PLAY_TX`` and ``RUN1/2/3_PLAY_TX``.

Rules are from Retrosheet's event-file documentation and are corrected against
observed ``cwevent`` output.
"""

from retrosheetpy.play import (
    AdvanceKind,
    EventKind,
    Param,
    ParamKind,
    Play,
    PrimaryEvent,
)

_ATTEMPTS = (EventKind.CAUGHT_STEALING, EventKind.PICKOFF_CAUGHT_STEALING, EventKind.PICKOFF)
_FIELDING_PARAMS = (ParamKind.FIELDING, ParamKind.FIELDING_THROW)


def _param_text(params: tuple[Param, ...]) -> str:
    """The fielding credit in the parentheses, else an error text such as ``E1``."""
    for wanted in (_FIELDING_PARAMS, (ParamKind.ERROR,)):
        for p in params:
            if p.kind in wanted:
                return p.text.partition("/")[0]
    return ""


def _event_texts(event: PrimaryEvent, texts: dict[str, str]) -> None:
    kind = event.kind
    if kind is EventKind.FIELDED_OUT:
        carry = ""
        for step in event.chain:
            # The fielder who made the last out throws on; he is not listed twice.
            seq = step.fielders if step.fielders.startswith(carry) else carry + step.fielders
            texts[step.runner or "B"] = seq
            carry = seq[-1] if step.runner else ""
    elif kind is EventKind.ERROR and event.fielders:
        texts["B"] = f"{event.fielders}E{event.error_fielder}"
    elif kind is EventKind.STRIKEOUT:
        texts["B"] = event.fielders or "2"
    elif kind in _ATTEMPTS and event.base is not None:
        base = 4 if event.base == "H" else int(event.base)
        origin = base if kind is EventKind.PICKOFF else base - 1
        text = _param_text(event.params)
        if text:
            texts[str(origin)] = text


def play_text_fields(play: Play) -> dict[str, str]:
    texts: dict[str, str] = {}
    node: PrimaryEvent | None = play.events[0]
    while node is not None:
        _event_texts(node, texts)
        node = node.follow_on
    for event in play.events[1:]:
        _event_texts(event, texts)
    for adv in play.advances:
        survived = adv.from_base == "B" and adv.kind is not AdvanceKind.OUT
        if survived and play.events[0].kind is EventKind.STRIKEOUT:
            texts.pop("B", None)  # a strikeout the batter survived has no out to describe
        if adv.kind is AdvanceKind.OUT and adv.from_base is not None:
            text = _param_text(adv.params)
            if text:
                texts[adv.from_base] = text
    return {
        "BAT_PLAY_TX": texts.get("B", ""),
        "RUN1_PLAY_TX": texts.get("1", ""),
        "RUN2_PLAY_TX": texts.get("2", ""),
        "RUN3_PLAY_TX": texts.get("3", ""),
    }
