"""Port of Chadwick's game container (``src/cwlib/game.c``, reading side).

Chadwick is Copyright (c) 2002-2023 Dr T L Turocy and the Chadwick Baseball
Bureau, licensed GPL-2.0-or-later; this module is a derivative of it and keeps
that notice. It follows ``cw_game_read``: events carry the substitutions,
comments and adjustment records (``badj``, ``padj``, ``ladj``, ``radj``,
``presadj``) that appear after them in the file.
"""

import logging
from collections.abc import Iterator
from dataclasses import dataclass, field

from retrosheetpy.cw.file import BUFSIZE, CFile, StrTok, cw_atoi

log = logging.getLogger("retrosheetpy.cw")


@dataclass
class Appearance:
    """``CWAppearance``: a start or sub record."""

    player_id: str
    name: str
    team: int
    slot: int
    pos: int


@dataclass
class Comment:
    """``CWComment``: a ``com`` record, with the ``ej,`` and ``umpchange,`` fields split out."""

    text: str
    ejection: tuple[str | None, str | None, str | None, str | None] | None = None
    umpchange: tuple[str | None, str | None, str | None] | None = None


@dataclass
class Event:
    """``CWEvent``: one play record plus what trails it."""

    inning: int
    batting_team: int
    batter: str
    count: str
    pitches: str
    event_text: str
    batter_hand: str = " "
    pitcher_hand: str = " "
    pitcher_hand_id: str | None = None
    ladj_align: int = 0
    ladj_slot: int = 0
    auto_base: int = 0
    auto_runner_id: str | None = None
    presadj: list[str | None] = field(default_factory=lambda: [None] * 4)
    subs: list[Appearance] = field(default_factory=list)
    comments: list[Comment] = field(default_factory=list)


@dataclass
class Game:
    """``CWGame``"""

    game_id: str
    version: str | None = None
    info: list[tuple[str, str]] = field(default_factory=list)
    starters: list[Appearance] = field(default_factory=list)
    events: list[Event] = field(default_factory=list)
    comments: list[Comment] = field(default_factory=list)
    data: list[tuple[str | None, ...]] = field(default_factory=list)
    stat: list[tuple[str | None, ...]] = field(default_factory=list)
    evdata: list[tuple[str | None, ...]] = field(default_factory=list)
    line: list[tuple[str | None, ...]] = field(default_factory=list)

    def set_version(self, version: str | None) -> None:
        """``cw_game_set_version``"""
        self.version = version

    def info_append(self, label: str, data: str) -> None:
        """``cw_game_info_append``"""
        self.info.append((label, data))

    def info_set(self, label: str, data: str) -> None:
        """``cw_game_info_set``: replace the *first* record with this label, else append.

        (``info_lookup`` reads the last one; the C is inconsistent and so is this.)
        """
        for i, (key, _value) in enumerate(self.info):
            if key == label:
                self.info[i] = (key, data)
                return
        self.info_append(label, data)

    def starter_append(self, player_id: str, name: str, team: int, slot: int, pos: int) -> None:
        """``cw_game_starter_append``"""
        self.starters.append(Appearance(player_id, name, team, slot, pos))

    def event_append(
        self, inning: int, batting_team: int, batter: str, count: str, pitches: str, event_text: str
    ) -> Event:
        """``cw_game_event_append``"""
        event = Event(inning, batting_team, batter, count, pitches, event_text)
        self.events.append(event)
        return event

    def truncate(self, event: Event) -> None:
        """``cw_game_truncate``: drop ``event`` and every event after it"""
        for i, candidate in enumerate(self.events):
            if candidate is event:
                del self.events[i:]
                return
        raise ValueError("event is not in this game (Chadwick would corrupt its list)")

    def substitute_append(self, player_id: str, name: str, team: int, slot: int, pos: int) -> None:
        """``cw_game_substitute_append``: to the last event"""
        if not self.events:
            raise ValueError("no event to attach a substitute to (Chadwick would crash)")
        self.events[-1].subs.append(Appearance(player_id, name, team, slot, pos))

    def data_append(self, data: list[str | None]) -> None:
        """``cw_game_data_append``"""
        self.data.append(tuple(data))

    def stat_append(self, data: list[str | None]) -> None:
        """``cw_game_stat_append``"""
        self.stat.append(tuple(data))

    def evdata_append(self, data: list[str | None]) -> None:
        """``cw_game_evdata_append``"""
        self.evdata.append(tuple(data))

    def line_append(self, data: list[str | None]) -> None:
        """``cw_game_line_append``"""
        self.line.append(tuple(data))

    def data_set_er(self, player_id: str, er: int) -> None:
        """``cw_game_data_set_er``: set the earned runs of a pitcher's ``data,er`` record"""
        text = str(er)
        if len(text) > 9:
            raise ValueError("earned runs do not fit the C buffer (Chadwick would overflow)")
        for i, item in enumerate(self.data):
            if len(item) >= 3 and _strcmp_eq(item[0], "er") and _strcmp_eq(item[1], player_id):
                self.data[i] = (item[0], item[1], text, *item[3:])
                return
        self.data_append(["er", player_id, text])

    def comment_append(self, text: str) -> Comment:
        """``cw_game_comment_append``: to the last event, or the game before any event"""
        return _comment_append(self, text)

    def replace_player(self, key_old: str, key_new: str) -> None:
        """``cw_game_replace_player``: every use of the id, in the order the C visits them"""
        for starter in self.starters:
            if starter.player_id == key_old:
                starter.player_id = key_new
        for event in self.events:
            if event.batter == key_old:
                event.batter = key_new
            for sub in event.subs:
                if sub.player_id == key_old:
                    sub.player_id = key_new
        for i, item in enumerate(self.data):
            if len(item) >= 3 and _strcmp_eq(item[0], "er") and _strcmp_eq(item[1], key_old):
                self.data[i] = (item[0], key_new, *item[2:])
        for label in ("wp", "lp", "save"):
            if self.info_lookup(label) == key_old:
                self.info_set(label, key_new)

    def info_lookup(self, label: str) -> str | None:
        """``cw_game_info_lookup``: the last info record with this label."""
        for key, value in reversed(self.info):
            if key == label:
                return value
        return None

    def starter_find(self, team: int, slot: int) -> Appearance | None:
        """``cw_game_starter_find``"""
        for s in self.starters:
            if s.team == team and s.slot == slot:
                return s
        return None

    def starter_by_position(self, team: int, pos: int) -> Appearance | None:
        """``cw_game_starter_find_by_position``"""
        for s in self.starters:
            if s.team == team and s.pos == pos:
                return s
        return None


def _strcmp_eq(a: str | None, b: str) -> bool:
    """``!strcmp(a, b)``, which crashes in C when ``a`` is NULL"""
    if a is None:
        raise ValueError("NULL string passed to strcmp (Chadwick would crash)")
    return a == b


def event_comment_append(event: Event, text: str) -> Comment:
    """``cw_event_comment_append``: a comment on an event, with no ``ej,``/``umpchange,`` parsing"""
    comment = Comment(text)
    event.comments.append(comment)
    return comment


def _libc_strtok(text: str, start: int) -> list[str | None]:
    """The first four tokens of libc ``strtok(&text[start], ",")``, then ``None`` once exhausted."""
    tokens = [t for t in text[start:].split(",") if t != ""]
    return [*tokens, None, None, None, None]


def _comment_append(game: Game, text: str) -> Comment:
    """``cw_game_comment_append``"""
    comment = Comment(text)
    if text.startswith("ej,"):
        t = _libc_strtok(text, 3)
        comment.ejection = (t[0], t[1], t[2], t[3])
    if text.startswith("umpchange,"):
        t = _libc_strtok(text, 10)
        comment.umpchange = (t[0], t[1], t[2])
    if not game.events:
        game.comments.append(comment)
    else:
        game.events[-1].comments.append(comment)
    return comment


def _warn_invalid_record(game: Game, line: str) -> None:
    """``cw_game_warn_invalid_record``"""
    log.warning("WARNING: In %s, skipping invalid record:\n         %s", game.game_id, line)


def _tokens(tok: StrTok, stop_blank: bool, stop_space: bool) -> list[str | None]:
    """The ``data[256]`` loops of ``cw_game_read``: tokens up to the terminating one.

    Returns the tokens before the terminator, or all 256 (so the caller can tell the
    record was not appended) when none terminated.
    """
    out: list[str | None] = []
    for _ in range(256):
        t = tok(None)
        if (
            t is None
            or (stop_space and t[:1] in (" ", "\t", "\n", "\v", "\f", "\r"))
            or (stop_blank and t == "")
        ):
            return out
        out.append(t)
    return [*out, None]


def read_game(file: CFile) -> Game | None:
    """``cw_game_read``: the next game, or ``None`` at the end of the file or on a bad header."""
    tok = StrTok()
    bat_hand, bat_hand_batter = " ", ""
    pit_hand, pit_hand_pitcher = " ", ""
    auto_runner = ""
    presadj = ["", "", "", ""]
    ladj_align = ladj_slot = auto_base = 0

    buf = file.fgets(BUFSIZE)
    if buf is None:
        return None
    first = tok(buf)
    if first == "id":
        game_id = tok(None)
        if game_id is None:
            return None
        game = Game(game_id)
    else:
        return None

    while not file.eof:
        filepos = file.getpos()
        buf = file.fgets(BUFSIZE)
        if buf is None:
            if file.eof:
                break
            return None
        if file.eof:
            break

        line = buf
        rtype = tok(buf)
        if rtype is None or rtype == "id":
            file.setpos(filepos)
            break
        if rtype == "version":
            version = tok(None)
            if version is not None:
                game.version = version
        elif rtype == "info":
            field_ = tok(None)
            value = tok(None)
            if field_ is not None:
                game.info.append((field_, value if value is not None else ""))
        elif rtype == "start":
            f = [tok(None) for _ in range(5)]
            if all(x is not None for x in f):
                pid, name, team, slot, pos = f
                assert pid is not None and name is not None
                assert team is not None and slot is not None and pos is not None
                game.starters.append(
                    Appearance(pid, name, cw_atoi(team), cw_atoi(slot), cw_atoi(pos))
                )
        elif rtype == "play":
            f = [tok(None) for _ in range(6)]
            inning, batting_team, batter, count, pitches, play = f
            if (
                inning is not None
                and batting_team is not None
                and batter is not None
                and count is not None
                and pitches is not None
                and play is not None
            ):
                game.events.append(
                    Event(cw_atoi(inning), cw_atoi(batting_team), batter, count, pitches, play)
                )
            # the C dereferences ``last_event`` and ``batter`` here without checking them
            last = game.events[-1] if game.events else None
            if bat_hand != " " and batter is not None and bat_hand_batter == batter:
                _need_event(last, line).batter_hand = bat_hand
            else:
                # once the batter changes, clear this out
                bat_hand, bat_hand_batter = " ", ""
            if pit_hand != " ":
                ev = _need_event(last, line)
                ev.pitcher_hand = pit_hand
                ev.pitcher_hand_id = pit_hand_pitcher
                pit_hand, pit_hand_pitcher = " ", ""
            if ladj_slot != 0:
                ev = _need_event(last, line)
                ev.ladj_align = ladj_align
                ev.ladj_slot = ladj_slot
                ladj_align = ladj_slot = 0
            if auto_base != 0:
                ev = _need_event(last, line)
                ev.auto_base = auto_base
                ev.auto_runner_id = auto_runner
                auto_base, auto_runner = 0, ""
            for b in (1, 2, 3):
                if presadj[b] != "":
                    _need_event(last, line).presadj[b] = presadj[b]
                    presadj[b] = ""
        elif rtype == "sub":
            f = [tok(None) for _ in range(5)]
            if all(x is not None for x in f):
                pid, name, team, slot, pos = f
                assert pid is not None and name is not None
                assert team is not None and slot is not None and pos is not None
                _need_event(game.events[-1] if game.events else None, line).subs.append(
                    Appearance(pid, name, cw_atoi(team), cw_atoi(slot), cw_atoi(pos))
                )
        elif rtype == "com":
            comment = tok(None)
            if comment is not None:
                _comment_append(game, comment)
        elif rtype == "data":
            items = _tokens(tok, stop_blank=False, stop_space=False)
            if items[-1:] != [None]:
                game.data.append(tuple(items))
        elif rtype == "stat":
            items = _tokens(tok, stop_blank=False, stop_space=True)
            if items[-1:] != [None]:
                game.stat.append(tuple(items))
        elif rtype == "event":
            items = _tokens(tok, stop_blank=False, stop_space=True)
            if items[-1:] != [None]:
                game.evdata.append(tuple(items))
        elif rtype == "line":
            items = _tokens(tok, stop_blank=True, stop_space=False)
            if items[-1:] != [None]:
                game.line.append(tuple(items))
        elif rtype == "badj":
            batter, bats = tok(None), tok(None)
            if batter is not None and bats is not None:
                bat_hand_batter = batter[: BUFSIZE - 1]
                bat_hand = bats[:1] or "\0"
        elif rtype == "padj":
            pitcher, throws = tok(None), tok(None)
            if pitcher is not None and throws is not None:
                pit_hand_pitcher = pitcher[: BUFSIZE - 1]
                pit_hand = throws[:1] or "\0"
        elif rtype == "ladj":
            align, slot = tok(None), tok(None)
            if align is not None and slot is not None:
                ladj_align = cw_atoi(align)
                ladj_slot = cw_atoi(slot)
        elif rtype in ("cw:itb", "radj"):
            # cw:itb is the old Chadwick extension with the same meaning as radj (2020)
            runner, auto_str = tok(None), tok(None)
            if runner is not None and auto_str is not None:
                auto_runner = runner[: BUFSIZE - 1]
                auto_base = cw_atoi(auto_str)
        elif rtype == "presadj":
            pitcher, base_str = tok(None), tok(None)
            if pitcher is not None and base_str is not None:
                base = cw_atoi(base_str)
                if 1 <= base <= 3:
                    presadj[base] = pitcher[: BUFSIZE - 1]
                else:
                    _warn_invalid_record(game, line)
        else:
            _warn_invalid_record(game, line)

    return game


def _need_event(event: Event | None, line: str) -> Event:
    """Where the C would dereference a NULL ``last_event`` (a crash) a ``ValueError`` is raised."""
    if event is None:
        raise ValueError(f"record needs a preceding play record (Chadwick would crash): {line!r}")
    return event


def read_games(data: bytes) -> Iterator[Game]:
    """Every game ``cw_game_read`` returns from the file contents, as ``cwevent`` reads them.

    Reading stops, as in Chadwick, when ``cw_game_read`` returns ``NULL``. If bytes
    are left unread then (a file not starting with an ``id`` record, say) a warning
    is logged, because Chadwick stops there without a message.
    """
    file = CFile(data)
    while (game := read_game(file)) is not None:
        yield game
    if file.pos < len(data):
        log.warning("WARNING: reading stopped at byte %d of %d", file.pos, len(data))


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


def pitch_ball_thrown(c: str) -> bool:
    """``cw_pitch_ball_thrown``"""
    return c in ("B", "H", "I", "P")


def pitch_strike_thrown(c: str) -> bool:
    """``cw_pitch_strike_thrown``"""
    return c in ("C", "F", "K", "L", "M", "O", "Q", "R", "S", "T", "X", "Y")
