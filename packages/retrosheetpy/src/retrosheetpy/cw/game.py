"""Port of Chadwick's game container (``src/cwlib/game.c``, reading side).

Chadwick is Copyright (c) 2002-2023 Dr T L Turocy and the Chadwick Baseball
Bureau, licensed GPL-2.0-or-later; this module is a derivative of it and keeps
that notice. It follows ``cw_game_read``: events carry the substitutions,
comments and adjustment records (``badj``, ``padj``, ``ladj``, ``radj``,
``presadj``) that appear after them in the file.
"""

from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field

from retrosheetpy.errors import ParseError
from retrosheetpy.records import (
    AdjustmentRecord,
    CommentRecord,
    IdRecord,
    InfoRecord,
    PlayRecord,
    Record,
    StartRecord,
    SubRecord,
)


@dataclass
class Appearance:
    """``CWAppearance``: a start or sub record."""

    player_id: str
    name: str
    team: int
    slot: int
    pos: int


@dataclass
class Event:
    """``CWEvent``: one play record plus what trails it."""

    inning: int
    batting_team: int
    batter: str
    count: str
    pitches: str
    event_text: str
    line_no: int
    batter_hand: str = " "
    pitcher_hand: str = " "
    ladj_slot: int = 0
    auto_base: int = 0
    auto_runner_id: str = ""
    presadj: list[str | None] = field(default_factory=lambda: [None] * 4)
    subs: list[Appearance] = field(default_factory=list)
    comments: list[str] = field(default_factory=list)


@dataclass
class Game:
    """``CWGame``"""

    game_id: str
    info: list[tuple[str, str]] = field(default_factory=list)
    starters: list[Appearance] = field(default_factory=list)
    events: list[Event] = field(default_factory=list)
    comments: list[str] = field(default_factory=list)

    def info_lookup(self, label: str) -> str | None:
        """``cw_game_info_lookup``: the last info record with this label."""
        for key, value in reversed(self.info):
            if key == label:
                return value
        return None

    def starter_by_position(self, team: int, pos: int) -> Appearance | None:
        """``cw_game_starter_find_by_position``"""
        for s in self.starters:
            if s.team == team and s.pos == pos:
                return s
        return None


def read_games(records: Iterable[Record]) -> Iterator[Game]:
    """Group records into games the way ``cw_game_read`` does."""
    game: Game | None = None
    bat_hand, bat_hand_batter = " ", ""
    pit_hand = " "
    ladj_slot = 0
    auto_base, auto_runner = 0, ""
    presadj: list[str] = ["", "", "", ""]

    for rec in records:
        if isinstance(rec, IdRecord):
            if game is not None:
                yield game
            game = Game(rec.value)
            bat_hand, bat_hand_batter, pit_hand = " ", "", " "
            ladj_slot, auto_base, auto_runner = 0, 0, ""
            presadj = ["", "", "", ""]
            continue
        if game is None:
            raise ParseError(
                "record before the first id record",
                stage="game",
                source=rec.source,
                line_no=rec.line_no,
                game_id=rec.game_id,
                record_type=type(rec).__name__,
                raw=rec.raw,
            )
        if isinstance(rec, InfoRecord):
            game.info.append((rec.key, rec.value))
        elif isinstance(rec, StartRecord):
            game.starters.append(
                Appearance(rec.player_id, rec.name, rec.team, rec.batting_order, rec.position)
            )
        elif isinstance(rec, PlayRecord):
            ev = Event(
                rec.inning, rec.team, rec.player_id, rec.count, rec.pitches, rec.event, rec.line_no
            )
            game.events.append(ev)
            if bat_hand != " " and bat_hand_batter == rec.player_id:
                ev.batter_hand = bat_hand
            else:
                # once the batter changes, clear this out
                bat_hand, bat_hand_batter = " ", ""
            if pit_hand != " ":
                ev.pitcher_hand = pit_hand
                pit_hand = " "
            if ladj_slot != 0:
                ev.ladj_slot = ladj_slot
                ladj_slot = 0
            if auto_base != 0:
                ev.auto_base = auto_base
                ev.auto_runner_id = auto_runner
                auto_base, auto_runner = 0, ""
            for b in (1, 2, 3):
                if presadj[b] != "":
                    ev.presadj[b] = presadj[b]
                    presadj[b] = ""
        elif isinstance(rec, SubRecord):
            if not game.events:
                raise ParseError(
                    "sub record before the first play",
                    stage="game",
                    source=rec.source,
                    line_no=rec.line_no,
                    game_id=rec.game_id,
                    record_type="sub",
                    raw=rec.raw,
                )
            game.events[-1].subs.append(
                Appearance(rec.player_id, rec.name, rec.team, rec.batting_order, rec.position)
            )
        elif isinstance(rec, CommentRecord):
            (game.events[-1].comments if game.events else game.comments).append(rec.text)
        elif isinstance(rec, AdjustmentRecord):
            f = rec.fields
            if rec.kind == "badj" and len(f) >= 2:
                bat_hand_batter, bat_hand = f[0], f[1][:1] or " "
            elif rec.kind == "padj" and len(f) >= 2:
                pit_hand = f[1][:1] or " "
            elif rec.kind == "ladj" and len(f) >= 2:
                ladj_slot = _atoi(f[1])
            elif rec.kind == "radj" and len(f) >= 2:
                auto_runner, auto_base = f[0], _atoi(f[1])
            elif rec.kind == "presadj" and len(f) >= 2:
                base = _atoi(f[1])
                if 1 <= base <= 3:
                    presadj[base] = f[0]
        # version, data and other record types do not affect iteration
    if game is not None:
        yield game


def _atoi(text: str) -> int:
    """C ``atoi`` for the plain integers found in these fields."""
    digits = ""
    for ch in text.strip():
        if ch.isdigit() or (not digits and ch in "+-"):
            digits += ch
        else:
            break
    try:
        return int(digits)
    except ValueError:
        return 0


# Pitch classification (``cw_pitch_*`` in game.c)
PITCH_BALL_THROWN = frozenset("BHIP")
PITCH_BALL_CALLED = frozenset("B")
PITCH_BALL_INTENTIONAL = frozenset("I")
PITCH_BALL_PITCHOUT = frozenset("P")
PITCH_BALL_HIT_BATTER = frozenset("H")
PITCH_BALL_OTHER = frozenset("V")
PITCH_STRIKE_THROWN = frozenset("CFKLMOQRSTXY")
PITCH_STRIKE_CALLED = frozenset("C")
PITCH_STRIKE_SWINGING = frozenset("SMQ")
PITCH_STRIKE_FOUL = frozenset("FLOTR")
PITCH_STRIKE_INPLAY = frozenset("XY")
PITCH_STRIKE_OTHER = frozenset("AK")


def count_pitches(pitches: str, criterion: frozenset[str]) -> int:
    """``cw_pitch_count_pitches``"""
    return sum(c in criterion for c in pitches)
