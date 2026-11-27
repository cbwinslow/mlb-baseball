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
from typing import Any, Literal, Protocol

import psycopg

from mlb_baseball import manifest

# Retrosheet publishes a season after it ends; the other sources update in season.
Through = Literal["current", "prior"]

# Game types Statcast covers outside spring training (R regular, F wild card,
# D division series, L league series, W World Series).
STATCAST_GAME_TYPES = ("R", "F", "D", "L", "W")

# Schedule statuses of a game that was played to a result. "Completed Early" is an
# official game stopped by rain or similar; it has a box score like a "Final" one.
PLAYED_STATUSES = ("Final", "Completed Early")


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
    """One unit per played game (Final or Completed Early) in ``raw.mlb_schedule`` from
    season ``first`` on; held = the game's id appears in ``key`` of the table. A game whose
    ledger item (``ledger`` dataset, source ``mlb_api``, key ``<season>:<game>``) is
    ``unavailable`` is a recorded source gap: accounted for, not missing."""

    first: int
    ledger: str | None = None
    key: str = "game_pk"
    unit: str = "game"
    game_types: tuple[str, ...] | None = None  # None = every game type in the schedule

    @property
    def expectation(self) -> str:
        gaps = f"; ledger '{self.ledger}' unavailable = source gap" if self.ledger else ""
        types = f" (types {'/'.join(self.game_types)})" if self.game_types else ""
        return f"played games{types} in raw.mlb_schedule from {self.first}{gaps}"

    def inputs(self, table: str) -> tuple[str, ...]:
        return ("raw.mlb_schedule", table)

    def measure(self, cur: psycopg.Cursor, table: str) -> list[Group]:
        types = list(self.game_types) if self.game_types else None
        cur.execute(
            f"""
            WITH want AS (
                SELECT DISTINCT _season AS label, game_id AS k
                FROM raw.mlb_schedule
                WHERE status = ANY(%s) AND _season ~ '^[0-9]+$' AND _season::int >= %s::int
                  AND (%s::text[] IS NULL OR game_type = ANY(%s::text[]))
            ), have AS (SELECT DISTINCT {self.key}::text AS k FROM {table}),
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
            (list(PLAYED_STATUSES), self.first, types, types, self.ledger),
        )
        return [Group(*row) for row in cur.fetchall()]


@dataclass(frozen=True)
class KalshiCandles:
    """One unit per Kalshi market with an open and a close time; held = ledger item
    ``candles`` is ``loaded``, accounted = ``unavailable`` (the market has no candles).
    An item fetched before a now-settled market closed counts as neither: its history is
    cut off."""

    unit: str = "market"
    expectation: str = (
        "markets in raw.kalshi_market with open and close times; ledger 'candles' "
        "loaded after close = held, unavailable = no candles at the source"
    )

    def inputs(self, table: str) -> tuple[str, ...]:
        return ("raw.kalshi_market",)

    def measure(self, cur: psycopg.Cursor, table: str) -> list[Group]:
        cur.execute(
            """
            WITH want AS (
                SELECT ticker AS k, min(substr(close_time, 1, 4)) AS label,
                       max(nullif(close_time, ''))::timestamptz AS closed
                FROM raw.kalshi_market
                WHERE open_time IS NOT NULL AND close_time IS NOT NULL
                GROUP BY ticker
            ), item AS (
                SELECT item_key AS k, status, updated_at FROM meta.ingestion_item
                WHERE source = 'kalshi' AND dataset = 'candles'
            ), judged AS (
                SELECT want.label,
                       CASE WHEN want.closed < now() - interval '1 day'
                                 AND item.updated_at < want.closed THEN NULL
                            ELSE item.status END AS status
                FROM want LEFT JOIN item USING (k)
            )
            SELECT label, count(*),
                   count(*) FILTER (WHERE status = 'loaded'),
                   count(*) FILTER (WHERE status = 'unavailable')
            FROM judged
            GROUP BY label
            ORDER BY label
            """
        )
        return [Group(*row) for row in cur.fetchall()]


@dataclass(frozen=True)
class PolymarketWindows:
    """One unit per (token, 14-day window) the price-history backfill plans for every
    token; held = ledger item ``price_history`` is ``loaded``, accounted =
    ``unavailable``. A window fetched before it was over counts as neither. The window
    grid and the completeness rule are the connector's own."""

    unit: str = "window"
    expectation: str = (
        "14-day windows of every outcome token (the backfill's own plan); ledger "
        "'price_history' loaded after the window ended = held, unavailable = empty at "
        "the source"
    )

    def inputs(self, table: str) -> tuple[str, ...]:
        return ("raw.polymarket_event", "raw.polymarket_market", "raw.polymarket_outcome")

    def measure(self, cur: psycopg.Cursor, table: str) -> list[Group]:
        # Imported here: the connector pulls in network libraries other kinds do not need.
        from mlb_baseball.connectors import polymarket

        now = int(time.time())
        tokens = polymarket._price_tokens(cur.connection)
        # Every window, and separately those still to be fetched.
        batches, undated = polymarket._plan_batches(tokens, {}, now)
        fetched = polymarket.fetched_times(cur.connection, "polymarket", "price_history")
        pending_batches, _ = polymarket._plan_batches(tokens, fetched, now)
        pending = {
            f"{t['clob_token_id']}:{cell}"
            for cell, group in pending_batches
            if cell + polymarket.HISTORY_WINDOW_SECONDS < now - 86400
            for t in group
        }
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
            held = None if key in pending else status.get(key)
            row[0] += 1
            row[1] += held == "loaded"
            row[2] += held == "unavailable"
        return [Group(label, *row) for label, row in sorted(counts.items())]


@dataclass(frozen=True)
class MarketTrades:
    """One unit per traded market; held = ledger item ``trades`` is ``loaded`` and was
    fetched after the market ended, accounted = the same for ``unavailable``."""

    source: str
    unit: str = "market"
    expectation: str = (
        "traded markets in the source's market table; ledger 'trades' fetched after the "
        "market ended"
    )

    def inputs(self, table: str) -> tuple[str, ...]:
        return (f"raw.{self.source}_market",)

    def measure(self, cur: psycopg.Cursor, table: str) -> list[Group]:
        key, ended, volume = (
            ("ticker", "close_time", "volume_fp")
            if self.source == "kalshi"
            else ("conditionid", "closedtime", "volume")
        )
        cur.execute(
            f"""
            WITH want AS (
                SELECT {key} AS k, max(nullif({ended}, ''))::timestamptz AS ended
                FROM raw.{self.source}_market
                WHERE coalesce({key}, '') <> ''
                  AND coalesce(nullif({volume}, ''), '0')::numeric > 0
                GROUP BY 1
            ), judged AS (
                SELECT coalesce(to_char(want.ended, 'YYYY'), 'open') AS label,
                       CASE WHEN want.ended < now() - interval '1 day'
                                 AND item.updated_at < want.ended THEN NULL
                            ELSE item.status END AS status
                FROM want LEFT JOIN meta.ingestion_item item
                  ON item.source = %s AND item.dataset = 'trades' AND item.item_key = want.k
            )
            SELECT label, count(*),
                   count(*) FILTER (WHERE status = 'loaded'),
                   count(*) FILTER (WHERE status = 'unavailable')
            FROM judged GROUP BY label ORDER BY label
            """,
            (self.source,),
        )
        return [Group(*row) for row in cur.fetchall()]


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


def _id_text(column: str) -> str:
    """An id as text with a float suffix removed: the Stats API loader stores some ids
    as ``17.0`` in one table and ``17`` in another; they are the same id."""
    return f"regexp_replace({column}::text, '\\.0+$', '')"


@dataclass(frozen=True)
class Referenced:
    """An entity table (people, teams, venues): every id that other raw tables point at
    should exist in it. ``key`` is the entity's key column(s); ``refs`` lists
    ``(table, columns)`` that reference it. One group per referencing column, labelled
    ``table.column``: expected = distinct ids it uses (NULL and blank are not ids), held =
    those found in the entity table. The groups answer "where does an unknown id come
    from", so a table total counts an id once per referencing column. Whether a gap is a
    defect or a scope choice (for example minor-league teams the connector never loads) is
    a reading of the groups, recorded in the dataset's caveat."""

    key: tuple[str, ...]
    refs: tuple[tuple[str, tuple[str, ...]], ...]
    unit: str = "id"

    @property
    def expectation(self) -> str:
        return (
            f"every id used by the referencing tables exists here ({'/'.join(self.key)}); "
            "one line per referencing column"
        )

    def inputs(self, table: str) -> tuple[str, ...]:
        return (table, *dict.fromkeys(t for t, _ in self.refs))

    def measure(self, cur: psycopg.Cursor, table: str) -> list[Group]:
        width = len(self.key)
        names = [f"k{i}" for i in range(width)]
        key_select = ", ".join(
            f"{_id_text(c)} AS {n}" for c, n in zip(self.key, names, strict=True)
        )
        groups: list[Group] = []
        for ref_table, cols in self.refs:
            if len(cols) != width:
                raise ValueError(f"{ref_table} references {len(cols)} columns, key has {width}")
            select = ", ".join(f"{_id_text(c)} AS {n}" for c, n in zip(cols, names, strict=True))
            present = " AND ".join(f"{c} IS NOT NULL AND {c}::text <> ''" for c in cols)
            cur.execute(
                f"""
                WITH used AS (SELECT DISTINCT {select} FROM {ref_table} WHERE {present}),
                     have AS (SELECT DISTINCT {key_select} FROM {table})
                SELECT count(*), count(*) FILTER (WHERE have.k0 IS NOT NULL)
                FROM used LEFT JOIN have USING ({", ".join(names)})
                """
            )
            expected, held = cur.fetchone() or (0, 0)
            if expected:
                groups.append(Group(f"{ref_table}.{'/'.join(cols)}", int(expected), int(held)))
        return groups


@dataclass(frozen=True)
class ManifestFiles:
    """Every archive recorded in ``downloads/<source>/manifest.json`` should be ``loaded``.
    Entries with status ``reference`` are lookup files the connector reads but never loads;
    they are not counted. Reads one local file; the "table" of this dataset is that file."""

    source: str
    unit: str = "file"
    expectation: str = "archives in the download manifest: status loaded"

    def inputs(self, table: str) -> tuple[str, ...]:
        return ()

    def measure(self, cur: psycopg.Cursor, table: str) -> list[Group]:
        entries = [
            entry
            for entry in manifest.load_manifest(self.source).values()
            if entry.get("status") != "reference"
        ]
        loaded = sum(1 for entry in entries if entry.get("status") == "loaded")
        return [Group("files", len(entries), loaded)]


# Schedule statuses of a game that has not reached a result yet.
UNSETTLED_STATUSES = ("Scheduled", "Pre-Game", "Warmup", "In Progress", "Live", "Delayed")

SCHEDULE_SETTLED_LABEL = "raw.mlb_schedule (past games settled)"


@dataclass(frozen=True)
class ScheduleSettled:
    """One unit per regular-season or postseason game dated before yesterday (UTC) in
    ``raw.mlb_schedule``; held = the game has left the not-yet-played statuses (Final,
    Completed Early, Postponed, Cancelled and so on). A past game still "Scheduled" means
    the schedule was not refreshed. The dataset's "table" is a label, not a table name."""

    unit: str = "game"
    expectation: str = (
        "regular-season and postseason games dated before yesterday are no longer "
        "Scheduled, Pre-Game, Warmup, In Progress, Live or Delayed in raw.mlb_schedule"
    )

    def inputs(self, table: str) -> tuple[str, ...]:
        return ("raw.mlb_schedule",)

    def measure(self, cur: psycopg.Cursor, table: str) -> list[Group]:
        cur.execute(
            """
            SELECT _season, count(*), count(*) FILTER (WHERE NOT status = ANY(%s))
            FROM raw.mlb_schedule
            WHERE game_type = ANY(%s) AND _season ~ '^[0-9]+$'
              AND game_date < to_char((now() AT TIME ZONE 'UTC')::date - 1, 'YYYY-MM-DD')
            GROUP BY _season
            ORDER BY _season
            """,
            (list(UNSETTLED_STATUSES), list(STATCAST_GAME_TYPES)),
        )
        return [Group(*row) for row in cur.fetchall()]


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


class LiveCheck(Protocol):
    @property
    def description(self) -> str: ...

    def measure(self, cur: psycopg.Cursor, table: str) -> Any: ...


@dataclass(frozen=True)
class Dataset:
    """One registry entry: a table, what it should hold, and the command that fixes a gap.

    ``fix`` may contain ``{first}`` and ``{last}``: the first and last missing season."""

    source: str
    table: str
    spec: Expectation
    fix: str = ""
    caveat: str = ""
    date_column: str = ""  # text date column whose first/last value is reported
    live: "LiveCheck | None" = None  # asks the publisher; only run with --probe


# Specs whose Dataset.table is a label, so the engine must not look it up as a table.
LABEL_SPECS = (ManifestFiles, ScheduleSettled)


def manifest_label(source: str) -> str:
    return str(Path("downloads") / source / "manifest.json")
