"""What a dataset should hold, and how to count what it does hold.

A ``Dataset`` pairs one raw table with one expectation. Every expectation measures
itself into ``Group`` rows (one per season, or one for the whole table): how many
units it expects, how many the database holds, and how many are accounted for
without being held (a source gap recorded in the ledger). All measurement is plain
SELECTs; nothing here writes.
"""

import time
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Literal, Protocol

import psycopg

from mlb_baseball import manifest

# Retrosheet publishes a season after it ends; the other sources update in season.
Through = Literal["current", "prior"]

# Game types Statcast covers outside spring training (R regular, F wild card,
# D division series, L league series, W World Series).
STATCAST_GAME_TYPES = ("R", "F", "D", "L", "W")


@dataclass(frozen=True)
class Group:
    """One bucket of an expectation. ``missing`` is what is neither held nor accounted for."""

    label: str
    expected: int
    held: int
    accounted: int = 0

    @property
    def missing(self) -> int:
        return self.expected - self.held - self.accounted


class Expectation(Protocol):
    @property
    def unit(self) -> str: ...

    @property
    def expectation(self) -> str: ...

    def inputs(self, table: str) -> tuple[str, ...]:
        """Tables that must exist for this expectation to be measured."""

    def measure(self, cur: psycopg.Cursor, table: str) -> list[Group]: ...


def _last_year(through: Through) -> int:
    return date.today().year - (1 if through == "prior" else 0)


@dataclass(frozen=True)
class Seasons:
    """One unit per season from ``first`` to the last published one; held = the season
    appears in ``column`` of the table."""

    first: int
    through: Through = "current"
    column: str = "_season"
    unit: str = "season"

    @property
    def expectation(self) -> str:
        last = "last completed season" if self.through == "prior" else "current season"
        return f"every season {self.first} to the {last} ({self.column})"

    def inputs(self, table: str) -> tuple[str, ...]:
        return (table,)

    def measure(self, cur: psycopg.Cursor, table: str) -> list[Group]:
        cur.execute(
            f"""
            WITH want AS (SELECT s::text AS label FROM generate_series(%s::int, %s::int) AS s),
                 have AS (SELECT DISTINCT {self.column}::text AS label FROM {table})
            SELECT want.label, 1, (have.label IS NOT NULL)::int
            FROM want LEFT JOIN have USING (label)
            ORDER BY want.label
            """,
            (self.first, _last_year(self.through)),
        )
        return [Group(label, expected, held) for label, expected, held in cur.fetchall()]


@dataclass(frozen=True)
class Games:
    """One unit per final game in ``raw.mlb_schedule`` from season ``first`` on; held = the
    game's id appears in ``key`` of the table. A game whose ledger item (``ledger`` dataset,
    source ``mlb_api``, key ``<season>:<game>``) is ``unavailable`` is a recorded source gap:
    accounted for, not missing."""

    first: int
    ledger: str | None = None
    key: str = "game_pk"
    unit: str = "game"

    @property
    def expectation(self) -> str:
        gaps = f"; ledger '{self.ledger}' unavailable = source gap" if self.ledger else ""
        return f"final games in raw.mlb_schedule from {self.first}{gaps}"

    def inputs(self, table: str) -> tuple[str, ...]:
        return ("raw.mlb_schedule", table)

    def measure(self, cur: psycopg.Cursor, table: str) -> list[Group]:
        cur.execute(
            f"""
            WITH want AS (
                SELECT DISTINCT _season AS label, game_id AS k
                FROM raw.mlb_schedule
                WHERE status = 'Final' AND _season ~ '^[0-9]+$' AND _season::int >= %s::int
            ), have AS (SELECT DISTINCT {self.key} AS k FROM {table}),
            gap AS (
                SELECT DISTINCT split_part(item_key, ':', 2) AS k
                FROM meta.ingestion_item
                WHERE source = 'mlb_api' AND dataset = %s AND status = 'unavailable'
            )
            SELECT want.label, count(*), count(have.k),
                   count(*) FILTER (WHERE have.k IS NULL AND gap.k IS NOT NULL)
            FROM want
            LEFT JOIN have ON have.k = want.k
            LEFT JOIN gap ON gap.k = want.k
            GROUP BY want.label
            ORDER BY want.label
            """,
            (self.first, self.ledger),
        )
        return [Group(*row) for row in cur.fetchall()]


@dataclass(frozen=True)
class GameDates:
    """One unit per calendar date with a final non-spring game in ``raw.mlb_schedule`` from
    season ``first`` on; held = the date appears in ``game_date`` of the table."""

    first: int
    unit: str = "date"

    @property
    def expectation(self) -> str:
        types = "/".join(STATCAST_GAME_TYPES)
        return f"dates of final games (types {types}) in raw.mlb_schedule from {self.first}"

    def inputs(self, table: str) -> tuple[str, ...]:
        return ("raw.mlb_schedule", table)

    def measure(self, cur: psycopg.Cursor, table: str) -> list[Group]:
        cur.execute(
            f"""
            WITH want AS (
                SELECT DISTINCT _season AS label, game_date AS k
                FROM raw.mlb_schedule
                WHERE status = 'Final' AND game_type = ANY(%s)
                  AND _season ~ '^[0-9]+$' AND _season::int >= %s::int
            ), have AS (SELECT DISTINCT game_date AS k FROM {table})
            SELECT want.label, count(*), count(have.k)
            FROM want LEFT JOIN have USING (k)
            GROUP BY want.label
            ORDER BY want.label
            """,
            (list(STATCAST_GAME_TYPES), self.first),
        )
        return [Group(*row) for row in cur.fetchall()]


@dataclass(frozen=True)
class KalshiCandles:
    """One unit per Kalshi market with an open and a close time; held = ledger item
    ``candles`` is ``loaded``, accounted = ``unavailable`` (the market has no candles)."""

    unit: str = "market"
    expectation: str = (
        "markets in raw.kalshi_market with open and close times; ledger 'candles' "
        "loaded = held, unavailable = no candles at the source"
    )

    def inputs(self, table: str) -> tuple[str, ...]:
        return ("raw.kalshi_market",)

    def measure(self, cur: psycopg.Cursor, table: str) -> list[Group]:
        cur.execute(
            """
            WITH want AS (
                SELECT ticker AS k, min(substr(close_time, 1, 4)) AS label
                FROM raw.kalshi_market
                WHERE open_time IS NOT NULL AND close_time IS NOT NULL
                GROUP BY ticker
            ), item AS (
                SELECT item_key AS k, status FROM meta.ingestion_item
                WHERE source = 'kalshi' AND dataset = 'candles'
            )
            SELECT want.label, count(*),
                   count(*) FILTER (WHERE item.status = 'loaded'),
                   count(*) FILTER (WHERE item.status = 'unavailable')
            FROM want LEFT JOIN item USING (k)
            GROUP BY want.label
            ORDER BY want.label
            """
        )
        return [Group(*row) for row in cur.fetchall()]


@dataclass(frozen=True)
class PolymarketWindows:
    """One unit per (token, 14-day window) the price-history backfill plans for every token
    of an MLB daily-game event; held = ledger item ``price_history`` is ``loaded``,
    accounted = ``unavailable``. The window grid is the connector's own."""

    unit: str = "window"
    expectation: str = (
        "14-day windows of every MLB daily-game token (the backfill's own plan); ledger "
        "'price_history' loaded = held, unavailable = empty at the source"
    )

    def inputs(self, table: str) -> tuple[str, ...]:
        return ("raw.polymarket_event", "raw.polymarket_market", "raw.polymarket_outcome")

    def measure(self, cur: psycopg.Cursor, table: str) -> list[Group]:
        # Imported here: the connector pulls in network libraries other kinds do not need.
        from mlb_baseball.connectors import polymarket

        tokens = polymarket._daily_game_tokens(cur.connection)
        batches, undated = polymarket._plan_batches(tokens, set(), int(time.time()))
        planned: dict[str, str] = {}
        for cell, group in batches:
            label = str(datetime.fromtimestamp(cell, UTC).year)
            for token in group:
                planned[f"{token['clob_token_id']}:{cell}"] = label
        for token in undated:
            planned[f"{token['clob_token_id']}:0"] = "undated"
        cur.execute(
            "SELECT item_key, status FROM meta.ingestion_item "
            "WHERE source = 'polymarket' AND dataset = 'price_history'"
        )
        status: dict[str, str] = dict(cur.fetchall())
        counts: dict[str, list[int]] = {}
        for key, label in planned.items():
            row = counts.setdefault(label, [0, 0, 0])
            row[0] += 1
            row[1] += status.get(key) == "loaded"
            row[2] += status.get(key) == "unavailable"
        return [Group(label, *row) for label, row in sorted(counts.items())]


@dataclass(frozen=True)
class Present:
    """A reference table the publisher ships whole: expected to hold at least one row."""

    unit: str = "table"
    expectation: str = "published whole-file reference table: at least one row"

    def inputs(self, table: str) -> tuple[str, ...]:
        return (table,)

    def measure(self, cur: psycopg.Cursor, table: str) -> list[Group]:
        cur.execute(f"SELECT EXISTS (SELECT 1 FROM {table})")
        (held,) = cur.fetchone() or (False,)
        return [Group("table", 1, int(held))]


@dataclass(frozen=True)
class ManifestFiles:
    """Every archive recorded in ``downloads/<source>/manifest.json`` should be ``loaded``.
    Reads one local file; the "table" of this dataset is that file."""

    source: str
    unit: str = "file"
    expectation: str = "archives in the download manifest: status loaded"

    def inputs(self, table: str) -> tuple[str, ...]:
        return ()

    def measure(self, cur: psycopg.Cursor, table: str) -> list[Group]:
        entries = manifest.load_manifest(self.source)
        loaded = sum(1 for entry in entries.values() if entry.get("status") == "loaded")
        return [Group("files", len(entries), loaded)]


@dataclass(frozen=True)
class NoExpectation:
    """No expectation can be derived; ``reason`` says why, in the output."""

    reason: str
    unit: str = "-"

    @property
    def expectation(self) -> str:
        return self.reason

    def inputs(self, table: str) -> tuple[str, ...]:
        return ()

    def measure(self, cur: psycopg.Cursor, table: str) -> list[Group]:
        return []


@dataclass(frozen=True)
class Dataset:
    """One registry entry: a table, what it should hold, and the command that fixes a gap.

    ``fix`` may contain ``{first}`` and ``{last}``: the first and last missing season."""

    source: str
    table: str
    spec: Expectation
    fix: str = ""
    caveat: str = ""


def manifest_label(source: str) -> str:
    return str(Path("downloads") / source / "manifest.json")
