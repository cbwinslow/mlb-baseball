"""Parse-coverage measurement for play strings."""

import re
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any

from retrosheetpy.play import _unsupported_with_stage, parse_play
from retrosheetpy.records import PlayRecord, Record


@dataclass
class FamilyStat:
    count: int = 0
    example: str = ""  # one full play string containing the syntax
    source: str = ""  # file and line of that example


def family_of(stage: str, token: str) -> str:
    """Group tokens by shape: digit runs become ``$`` (``R64`` and ``R65`` share ``R$``)."""
    return f"{stage}:{re.sub(r'[0-9]+', '$', token)}"


@dataclass
class PlayCoverage:
    plays: int = 0
    plays_unsupported: int = 0
    families: dict[str, FamilyStat] = field(default_factory=dict)

    def add(self, record: PlayRecord) -> None:
        self.plays += 1
        play = parse_play(record.event, strict=False)
        bad = list(_unsupported_with_stage(play))
        if not bad:
            return
        self.plays_unsupported += 1
        for stage, token in bad:
            stat = self.families.setdefault(family_of(stage, token), FamilyStat())
            if stat.count == 0:
                stat.example = record.event
                stat.source = f"{record.source}:{record.line_no}"
            stat.count += 1

    def add_records(self, records: Iterable[Record]) -> None:
        for rec in records:
            if isinstance(rec, PlayRecord):
                self.add(rec)

    def to_dict(self) -> dict[str, Any]:
        return {
            "plays": self.plays,
            "plays_parsed": self.plays - self.plays_unsupported,
            "plays_unsupported": self.plays_unsupported,
            "unsupported_families": {
                k: {"count": v.count, "example": v.example, "source": v.source}
                for k, v in sorted(self.families.items(), key=lambda kv: -kv[1].count)
            },
        }
