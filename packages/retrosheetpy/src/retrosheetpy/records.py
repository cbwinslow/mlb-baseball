"""Lossless framing of Retrosheet event-file lines into typed records.

Every record keeps the exact source line (``raw``, without its line ending),
its file name, 1-based line number, and the game id in force. Nothing is
skipped: an unknown or malformed line raises ``ParseError`` (strict) or is
yielded as an explicit ``UnsupportedRecord`` (diagnostic).
"""

import csv
import re
from collections import Counter
from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field
from pathlib import Path

from retrosheetpy.client import iter_zip_members
from retrosheetpy.errors import ParseError


@dataclass(frozen=True, slots=True)
class Record:
    raw: str
    source: str
    line_no: int
    game_id: str | None


@dataclass(frozen=True, slots=True)
class IdRecord(Record):
    value: str


@dataclass(frozen=True, slots=True)
class VersionRecord(Record):
    version: str


@dataclass(frozen=True, slots=True)
class InfoRecord(Record):
    key: str
    value: str


@dataclass(frozen=True, slots=True)
class LineupRecord(Record):
    player_id: str
    name: str
    team: int
    batting_order: int
    position: int


@dataclass(frozen=True, slots=True)
class StartRecord(LineupRecord):
    pass


@dataclass(frozen=True, slots=True)
class SubRecord(LineupRecord):
    pass


@dataclass(frozen=True, slots=True)
class PlayRecord(Record):
    inning: int
    team: int
    player_id: str
    count: str
    pitches: str
    event: str


@dataclass(frozen=True, slots=True)
class DataRecord(Record):
    kind: str
    fields: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class CommentRecord(Record):
    text: str


@dataclass(frozen=True, slots=True)
class AdjustmentRecord(Record):
    kind: str
    fields: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class UnsupportedRecord(Record):
    record_type: str
    fields: tuple[str, ...]
    reason: str


ADJUSTMENT_KINDS = frozenset({"badj", "padj", "ladj", "radj", "presadj"})


@dataclass
class RecordStats:
    """Coverage counts. ``unsupported`` is keyed by record type."""

    lines: int = 0
    by_type: Counter[str] = field(default_factory=Counter)
    unsupported: Counter[str] = field(default_factory=Counter)


class _Bad(Exception):
    """Internal: the line is not a valid record of its type."""


def _split(line: str) -> list[str]:
    try:
        return next(csv.reader([line]))
    except (csv.Error, StopIteration) as exc:
        raise _Bad(f"unreadable CSV line: {exc}") from exc


def _int(value: str, what: str) -> int:
    try:
        return int(value)
    except ValueError:
        raise _Bad(f"{what} is not an integer") from None


def _need(f: list[str], n: int) -> None:
    if len(f) != n:
        raise _Bad(f"expected {n} fields, got {len(f)}")


def _build(rtype: str, f: list[str], base: dict[str, object]) -> Record | None:
    """Return a typed record, or None if ``rtype`` is not a known type."""
    if rtype == "id":
        _need(f, 2)
        return IdRecord(**base, value=f[1])  # type: ignore[arg-type]
    if rtype == "version":
        _need(f, 2)
        return VersionRecord(**base, version=f[1])  # type: ignore[arg-type]
    if rtype == "info":
        if len(f) < 3:
            raise _Bad(f"expected at least 3 fields, got {len(f)}")
        return InfoRecord(**base, key=f[1], value=",".join(f[2:]))  # type: ignore[arg-type]
    if rtype in ("start", "sub"):
        _need(f, 6)
        cls = StartRecord if rtype == "start" else SubRecord
        return cls(
            **base,  # type: ignore[arg-type]
            player_id=f[1],
            name=f[2],
            team=_int(f[3], "team"),
            batting_order=_int(f[4], "batting order"),
            position=_int(f[5], "fielding position"),
        )
    if rtype == "play":
        _need(f, 7)
        return PlayRecord(
            **base,  # type: ignore[arg-type]
            inning=_int(f[1], "inning"),
            team=_int(f[2], "team"),
            player_id=f[3],
            count=f[4],
            pitches=f[5],
            event=f[6],
        )
    if rtype == "data":
        if len(f) < 2:
            raise _Bad("data record has no kind")
        return DataRecord(**base, kind=f[1], fields=tuple(f[2:]))  # type: ignore[arg-type]
    if rtype == "com":
        if len(f) < 2:
            raise _Bad("comment has no text")
        return CommentRecord(**base, text=",".join(f[1:]))  # type: ignore[arg-type]
    if rtype in ADJUSTMENT_KINDS:
        return AdjustmentRecord(**base, kind=rtype, fields=tuple(f[1:]))  # type: ignore[arg-type]
    return None


def iter_records(
    lines: Iterable[bytes | str],
    *,
    source: str,
    strict: bool = True,
    stats: RecordStats | None = None,
) -> Iterator[Record]:
    """Stream typed records from raw lines (bytes are decoded as UTF-8).

    Invalid UTF-8 bytes are kept via ``surrogateescape`` so nothing is lost.
    """
    game_id: str | None = None
    for line_no, line in enumerate(lines, start=1):
        if isinstance(line, bytes):
            line = line.decode("utf-8", errors="surrogateescape")
        raw = line.rstrip("\r\n")
        rtype = raw.split(",", 1)[0]
        base: dict[str, object] = {"raw": raw, "source": source, "line_no": line_no}
        record: Record | None
        fields: list[str] = []
        stage = "record-type"
        try:
            fields = _split(raw) if raw else []
            if raw and rtype == "id" and len(fields) == 2:
                game_id = fields[1]
            base["game_id"] = game_id
            record = _build(rtype, fields, base) if raw else None
            reason = ""
            if record is None:
                reason = "unknown record type" if raw else "blank line"
        except _Bad as exc:
            base["game_id"] = game_id
            record, reason, stage = None, str(exc), "record-fields"
        if record is None:
            if strict:
                raise ParseError(
                    reason,
                    stage=stage,
                    source=source,
                    line_no=line_no,
                    game_id=game_id,
                    record_type=rtype,
                    raw=raw,
                )
            record = UnsupportedRecord(
                **base,  # type: ignore[arg-type]
                record_type=rtype,
                fields=tuple(fields[1:]),
                reason=reason,
            )
        if stats is not None:
            stats.lines += 1
            if isinstance(record, UnsupportedRecord):
                stats.unsupported[rtype] += 1
            else:
                stats.by_type[rtype] += 1
        yield record


def read_event_file(
    path: str | Path, *, strict: bool = True, stats: RecordStats | None = None
) -> Iterator[Record]:
    """Stream records from one event file on disk."""
    with open(path, "rb") as f:
        yield from iter_records(f, source=Path(path).name, strict=strict, stats=stats)


_EVENT_NAME = re.compile(r"\.(ev|ed)[a-z]$", re.IGNORECASE)


def is_event_filename(name: str) -> bool:
    """True for Retrosheet event files (.EVN/.EVA/.EVE/.EVF/.EVR, deduced .EDx)."""
    return bool(_EVENT_NAME.search(name))


def iter_event_zip(
    path: str | Path, *, strict: bool = True, stats: RecordStats | None = None
) -> Iterator[Record]:
    """Stream records from every event member of a Retrosheet zip archive.

    Roster/team members (``.ROS``, ``TEAMyyyy``) use other formats and are
    not event records; they are ignored by name, not by content.
    """
    for name, member in iter_zip_members(path):
        if is_event_filename(name):
            yield from iter_records(member, source=name, strict=strict, stats=stats)
