"""Compare parser-derived fields with reference rows and report disagreements.

References are plain row mappings (``csv.DictReader`` output): Chadwick
``cwevent`` output or Retrosheet's yearly ``plays.csv``. Nothing here runs a
native tool; callers supply the rows. A disagreement is never resolved in
either direction: it is counted and an example is kept, so three sources
(our parser, Chadwick, the CSV) can be compared by a person.
"""

from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any

from retrosheetpy.crosswalk import chadwick_fields, csv_fields
from retrosheetpy.play import Play, parse_play
from retrosheetpy.records import PlayRecord, Record

MAX_EXAMPLES = 5
Derive = Callable[[Play], Mapping[str, int | str]]
Row = Mapping[str, str]


@dataclass
class FieldStat:
    compared: int = 0
    mismatches: int = 0
    examples: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class Comparison:
    """Outcome of comparing one reference against the parser."""

    reference: str
    games: int = 0  # games present on both sides
    games_only_ours: int = 0
    games_only_reference: int = 0
    plays_compared: int = 0
    # Games where the reference rows do not line up one-to-one with our play records
    # (different count or different event text). Their plays are not field-compared.
    games_misaligned: int = 0
    misaligned_examples: list[dict[str, Any]] = field(default_factory=list)
    fields: dict[str, FieldStat] = field(default_factory=dict)

    @property
    def mismatches(self) -> int:
        return sum(s.mismatches for s in self.fields.values())

    def to_dict(self) -> dict[str, Any]:
        return {
            "reference": self.reference,
            "games": self.games,
            "games_only_ours": self.games_only_ours,
            "games_only_reference": self.games_only_reference,
            "plays_compared": self.plays_compared,
            "games_misaligned": self.games_misaligned,
            "misaligned_examples": self.misaligned_examples,
            "mismatches": self.mismatches,
            "fields": {
                name: {"compared": s.compared, "mismatches": s.mismatches, "examples": s.examples}
                for name, s in sorted(self.fields.items())
            },
        }


def _play_records_by_game(records: Iterable[Record]) -> dict[str, list[PlayRecord]]:
    games: dict[str, list[PlayRecord]] = {}
    for rec in records:
        if isinstance(rec, PlayRecord) and rec.game_id and rec.event != "NP":
            games.setdefault(rec.game_id, []).append(rec)
    return games


def _normalise(name: str, value: str) -> str:
    # The CSV marks hit-location strength with a trailing +/- that the event text may omit.
    return value.rstrip("+-") if name == "loc" else value


def compare(
    reference: str,
    records: Iterable[Record],
    rows: Iterable[Row],
    *,
    game_col: str,
    event_col: str,
    derive: Derive,
) -> Comparison:
    """Field-compare ``derive(parse_play(event))`` against ``rows``, game by game.

    ``NP`` (no-play) lines are dropped from both sides before aligning, because
    the references disagree about whether to emit them.
    """
    ours = _play_records_by_game(records)
    theirs: dict[str, list[Row]] = {}
    for row in rows:
        if row[event_col] != "NP":
            theirs.setdefault(row[game_col], []).append(row)
    out = Comparison(reference)
    for game_id in sorted(ours.keys() | theirs.keys()):
        mine, ref = ours.get(game_id, []), theirs.get(game_id, [])
        if not ref:
            out.games_only_ours += 1
            continue
        if not mine:
            out.games_only_reference += 1
            continue
        out.games += 1
        if [r.event for r in mine] != [r[event_col] for r in ref]:
            out.games_misaligned += 1
            if len(out.misaligned_examples) < MAX_EXAMPLES:
                ours_tx = [r.event for r in mine]
                ref_tx = [r[event_col] for r in ref]
                idx = next(
                    (i for i, (a, b) in enumerate(zip(ours_tx, ref_tx, strict=False)) if a != b),
                    min(len(ours_tx), len(ref_tx)),
                )
                out.misaligned_examples.append(
                    {
                        "game_id": game_id,
                        "ours": len(mine),
                        "reference": len(ref),
                        "first_difference": idx,
                        "ours_event": ours_tx[idx] if idx < len(ours_tx) else None,
                        "reference_event": ref_tx[idx] if idx < len(ref_tx) else None,
                    }
                )
            continue
        for rec, row in zip(mine, ref, strict=True):
            out.plays_compared += 1
            for name, value in derive(parse_play(rec.event, strict=False)).items():
                if name not in row:
                    raise ValueError(
                        f"{reference}: reference rows have no column {name!r}; "
                        "refusing to skip it silently"
                    )
                stat = out.fields.setdefault(name, FieldStat())
                stat.compared += 1
                expected = _normalise(name, row[name])
                if _normalise(name, str(value)) != expected:
                    stat.mismatches += 1
                    if len(stat.examples) < MAX_EXAMPLES:
                        stat.examples.append(
                            {
                                "game_id": game_id,
                                "source": f"{rec.source}:{rec.line_no}",
                                "event": rec.event,
                                "ours": value,
                                "reference": row[name],
                            }
                        )
    return out


def compare_chadwick(
    records: Iterable[Record], rows: Iterable[Row], *, version: str = ""
) -> Comparison:
    """Compare against ``cwevent`` output (needs ``GAME_ID`` and ``EVENT_TX`` columns)."""
    label = f"chadwick cwevent {version}".strip()
    return compare(
        label, records, rows, game_col="GAME_ID", event_col="EVENT_TX", derive=chadwick_fields
    )


def compare_plays_csv(records: Iterable[Record], rows: Iterable[Row]) -> Comparison:
    """Compare against Retrosheet's yearly ``plays.csv`` (``gid`` and ``event`` columns)."""
    return compare(
        "retrosheet plays.csv", records, rows, game_col="gid", event_col="event", derive=csv_fields
    )
