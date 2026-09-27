"""Retrosheet tie-out gate: comparison logic, explained-differences register, and
read-only database access.

Spec: ``openspec/changes/raw-source-tieout/`` (design D1-D8, pass marks and the
initial register in ``passmarks.md``). The gate proves the redundant Retrosheet
sources agree with each other and with ``core``. It only reads; the thin
entry point is ``scripts/verify_retrosheet_tie_out.py``.

This module is deliberately split in two:

* **Pure logic** (``Series``, ``compare``, ``Register``, ``assess``, ``Report``):
  plain counts in, verdicts out, no database. Everything a reviewer needs to
  trust the pass mark is testable without PostgreSQL.
* **Read-only access** (``open_readonly``, ``series_from_rows``): the only code
  that touches a connection, and it refuses to run unless the connected
  database is the one the caller named.

Rules the code enforces (they are the pass marks, not tuning knobs):

* The tolerance is **zero**. Two sources describing the same fact must match
  exactly, or a register entry must reproduce the difference exactly.
* A key absent from one side counts as zero for every fact (a count of events
  that never happened), but it is still shown as absent in the report so a
  missing game or player is visible, not just a number.
* A source that does not cover a season is **not comparable** for it. That is
  never reported as a pass.
* A register entry that predicts a difference which is absent, or a different
  size, is **stale** and fails the gate, so an old excuse cannot hide a new
  problem.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable, Collection, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Literal

import psycopg

# Every key starts with the season so a series can be split or restricted by
# season without knowing the level.
Key = tuple[str, ...]
Counts = Mapping[str, int]

LEVELS = ("season", "game", "player_game")
# Number of key columns per level (season first, then game id, then player id).
KEY_COLUMNS: dict[str, tuple[str, ...]] = {
    "season": ("season",),
    "game": ("season", "game_id"),
    "player_game": ("season", "game_id", "player_id"),
}

Status = Literal["match", "explained", "unexplained", "not_comparable"]


class TieOutError(RuntimeError):
    """The gate cannot run or cannot be trusted (bad target, bad input)."""


@dataclass(frozen=True)
class Series:
    """One source's counts at one level.

    ``counts`` maps a key to ``{fact: value}``. ``facts`` is the set of facts
    the source can supply; only facts both sides of a comparison supply are
    compared. A fact a source cannot supply is *not comparable*, never zero.
    """

    source: str
    level: str
    facts: frozenset[str]
    counts: Mapping[Key, Counts]

    def __post_init__(self) -> None:
        if self.level not in LEVELS:
            raise ValueError(f"unknown level {self.level!r}; expected one of {LEVELS}")
        width = len(KEY_COLUMNS[self.level])
        for key in self.counts:
            if len(key) != width:
                raise ValueError(
                    f"{self.source} {self.level}: key {key!r} has {len(key)} parts, "
                    f"expected {width}"
                )

    def seasons(self) -> set[str]:
        return {key[0] for key in self.counts}


@dataclass(frozen=True)
class Difference:
    """One fact at one key where two sources disagree. ``None`` means the key
    is absent from that source."""

    level: str
    key: Key
    fact: str
    a_source: str
    a_value: int | None
    b_source: str
    b_value: int | None

    @property
    def a_number(self) -> int:
        return self.a_value or 0

    @property
    def b_number(self) -> int:
        return self.b_value or 0

    def describe(self) -> str:
        def show(v: int | None) -> str:
            return "absent" if v is None else str(v)

        return (
            f"{self.level} {'/'.join(self.key)} {self.fact}: "
            f"{self.a_source} {show(self.a_value)} vs {self.b_source} {show(self.b_value)}"
        )


@dataclass(frozen=True)
class Coverage:
    """Which seasons two series can be compared for."""

    comparable: frozenset[str]
    only_a: frozenset[str]
    only_b: frozenset[str]


def coverage(a: Series, b: Series) -> Coverage:
    """Split the seasons into those both sources cover and those only one does."""
    seasons_a = a.seasons()
    seasons_b = b.seasons()
    return Coverage(
        comparable=frozenset(seasons_a & seasons_b),
        only_a=frozenset(seasons_a - seasons_b),
        only_b=frozenset(seasons_b - seasons_a),
    )


@dataclass(frozen=True)
class Comparison:
    """Raw result of comparing two series over a set of seasons."""

    a_source: str
    b_source: str
    level: str
    facts: tuple[str, ...]
    seasons: frozenset[str]
    keys_compared: int
    differences: tuple[Difference, ...]
    # Differences found beyond ``max_differences`` that were counted but not kept.
    # Any overflow fails the comparison: it can never pass by being large.
    overflow: int = 0


def compare(
    a: Series,
    b: Series,
    *,
    seasons: Collection[str],
    max_differences: int | None = None,
) -> Comparison:
    """Compare two series exactly, key by key, for the given seasons.

    Only facts both sources supply are compared. The caller decides ``seasons``
    (normally ``coverage(...).comparable``); keys outside them are ignored.
    ``max_differences`` bounds memory when a source is badly broken: further
    differences are counted in ``overflow`` (which fails the comparison) rather
    than kept.
    """
    if a.level != b.level:
        raise ValueError(f"cannot compare {a.level} with {b.level}")
    wanted = frozenset(seasons)
    facts = tuple(sorted(a.facts & b.facts))
    keys = {k for k in a.counts if k[0] in wanted} | {k for k in b.counts if k[0] in wanted}
    differences: list[Difference] = []
    overflow = 0
    for key in sorted(keys):
        row_a = a.counts.get(key)
        row_b = b.counts.get(key)
        for fact in facts:
            value_a = None if row_a is None else row_a.get(fact, 0)
            value_b = None if row_b is None else row_b.get(fact, 0)
            if (value_a or 0) != (value_b or 0):
                if max_differences is not None and len(differences) >= max_differences:
                    overflow += 1
                else:
                    differences.append(
                        Difference(a.level, key, fact, a.source, value_a, b.source, value_b)
                    )
    return Comparison(
        a_source=a.source,
        b_source=b.source,
        level=a.level,
        facts=facts,
        seasons=wanted,
        keys_compared=len(keys),
        differences=tuple(differences),
        overflow=overflow,
    )


def merge_comparisons(
    parts: Sequence[Comparison], *, max_differences: int | None = None
) -> Comparison:
    """Combine per-season comparisons of the same pair and level into one, so
    the register is applied once over the whole run."""
    if not parts:
        raise ValueError("nothing to merge")
    first = parts[0]
    for part in parts[1:]:
        if (part.a_source, part.b_source, part.level, part.facts) != (
            first.a_source,
            first.b_source,
            first.level,
            first.facts,
        ):
            raise ValueError("cannot merge comparisons of different pairs, levels or facts")
    kept: list[Difference] = []
    overflow = 0
    for part in parts:
        overflow += part.overflow
        for diff in part.differences:
            if max_differences is not None and len(kept) >= max_differences:
                overflow += 1
            else:
                kept.append(diff)
    return Comparison(
        a_source=first.a_source,
        b_source=first.b_source,
        level=first.level,
        facts=first.facts,
        seasons=frozenset().union(*(part.seasons for part in parts)),
        keys_compared=sum(part.keys_compared for part in parts),
        differences=tuple(kept),
        overflow=overflow,
    )


# --- Register ---------------------------------------------------------------

Context = Mapping[tuple[str, str], Series]
"""Every series loaded for the run, keyed by ``(source, level)``, so a rule can
consult a third source (for example the post-season game log)."""


@dataclass(frozen=True)
class Expectation:
    """A difference a register entry predicts. If the entry applies to a
    comparison and this difference is absent or a different size, the entry is
    stale."""

    level: str
    key: Key
    fact: str


@dataclass(frozen=True)
class Entry:
    """One explained difference (see ``passmarks.md`` section 2)."""

    id: str
    summary: str
    cause: str
    evidence: str
    facts: frozenset[str]
    levels: frozenset[str]
    applies_to: Callable[[str, str], bool]
    explains: Callable[[Difference, Context], bool]
    expects: Callable[[Comparison, Context], Iterable[Expectation]]


@dataclass(frozen=True)
class StaleEntry:
    entry_id: str
    expectation: Expectation
    found: Difference | None

    def describe(self) -> str:
        where = f"{self.expectation.level} {'/'.join(self.expectation.key)} {self.expectation.fact}"
        if self.found is None:
            return f"{self.entry_id} predicted a difference at {where}, but the sources agree"
        return (
            f"{self.entry_id} predicted a difference at {where}, "
            f"but it is not the size the rule gives: {self.found.describe()}"
        )


@dataclass(frozen=True)
class Register:
    entries: tuple[Entry, ...]

    def find(self, diff: Difference, ctx: Context) -> Entry | None:
        for entry in self.entries:
            if (
                diff.fact in entry.facts
                and diff.level in entry.levels
                and entry.applies_to(diff.a_source, diff.b_source)
                and entry.explains(diff, ctx)
            ):
                return entry
        return None


# --- Assessment -------------------------------------------------------------


@dataclass(frozen=True)
class SeasonResult:
    season: str
    status: Status
    explained: int = 0
    unexplained: int = 0
    stale: int = 0


@dataclass(frozen=True)
class Assessment:
    """A comparison judged against the register."""

    comparison: Comparison
    explained: tuple[tuple[Difference, str], ...]
    unexplained: tuple[Difference, ...]
    stale: tuple[StaleEntry, ...]
    not_comparable: tuple[tuple[str, str], ...]
    seasons: tuple[SeasonResult, ...]

    @property
    def passed(self) -> bool:
        return not self.unexplained and not self.stale and self.comparison.overflow == 0

    @property
    def compared_anything(self) -> bool:
        return self.comparison.keys_compared > 0


def assess(
    comparison: Comparison,
    register: Register,
    ctx: Context,
    *,
    only_a: Collection[str] = (),
    only_b: Collection[str] = (),
) -> Assessment:
    """Judge a comparison: every difference must be explained by a register
    entry, and every prediction of a register entry must actually appear.

    ``only_a`` / ``only_b`` are seasons one source covers alone; they are
    reported as *not comparable*, never as a pass.
    """
    explained: list[tuple[Difference, str]] = []
    unexplained: list[Difference] = []
    found_by_entry: dict[tuple[str, str, Key, str], Difference] = {}
    for diff in comparison.differences:
        entry = register.find(diff, ctx)
        if entry is None:
            unexplained.append(diff)
        else:
            explained.append((diff, entry.id))
            found_by_entry[(entry.id, diff.level, diff.key, diff.fact)] = diff

    stale: list[StaleEntry] = []
    difference_at = {(d.level, d.key, d.fact): d for d in comparison.differences}
    for entry in register.entries:
        if not entry.applies_to(comparison.a_source, comparison.b_source):
            continue
        if comparison.level not in entry.levels:
            continue
        for expectation in entry.expects(comparison, ctx):
            if expectation.key[0] not in comparison.seasons:
                continue
            if expectation.level != comparison.level or expectation.fact not in comparison.facts:
                continue
            matched = found_by_entry.get(
                (entry.id, expectation.level, expectation.key, expectation.fact)
            )
            if matched is None:
                stale.append(
                    StaleEntry(
                        entry.id,
                        expectation,
                        difference_at.get((expectation.level, expectation.key, expectation.fact)),
                    )
                )

    not_comparable = tuple(
        [(season, comparison.a_source) for season in sorted(only_a)]
        + [(season, comparison.b_source) for season in sorted(only_b)]
    )
    return Assessment(
        comparison=comparison,
        explained=tuple(explained),
        unexplained=tuple(unexplained),
        stale=tuple(stale),
        not_comparable=not_comparable,
        seasons=_season_results(comparison, explained, unexplained, stale, only_a, only_b),
    )


def _season_results(
    comparison: Comparison,
    explained: Sequence[tuple[Difference, str]],
    unexplained: Sequence[Difference],
    stale: Sequence[StaleEntry],
    only_a: Collection[str],
    only_b: Collection[str],
) -> tuple[SeasonResult, ...]:
    explained_by_season: dict[str, int] = defaultdict(int)
    unexplained_by_season: dict[str, int] = defaultdict(int)
    stale_by_season: dict[str, int] = defaultdict(int)
    for diff, _entry in explained:
        explained_by_season[diff.key[0]] += 1
    for diff in unexplained:
        unexplained_by_season[diff.key[0]] += 1
    for item in stale:
        stale_by_season[item.expectation.key[0]] += 1

    results: list[SeasonResult] = []
    for season in sorted(comparison.seasons):
        if unexplained_by_season[season] or stale_by_season[season]:
            status: Status = "unexplained"
        elif explained_by_season[season]:
            status = "explained"
        else:
            status = "match"
        results.append(
            SeasonResult(
                season=season,
                status=status,
                explained=explained_by_season[season],
                unexplained=unexplained_by_season[season],
                stale=stale_by_season[season],
            )
        )
    for season in sorted(set(only_a) | set(only_b)):
        results.append(SeasonResult(season=season, status="not_comparable"))
    return tuple(results)


# --- Report -----------------------------------------------------------------


@dataclass
class Report:
    """All assessments of one run, and the overall verdict."""

    assessments: list[Assessment] = field(default_factory=list)
    problems: list[str] = field(default_factory=list)
    # Findings that are listed but are not a comparison between two sources
    # (for example unresolved player identifiers). They never pass or fail the
    # gate by themselves and are printed so they can be triaged.
    notes: list[str] = field(default_factory=list)

    def add(self, assessment: Assessment) -> None:
        self.assessments.append(assessment)

    @property
    def passed(self) -> bool:
        """True only if every comparison passed, nothing failed outside the
        comparisons (``problems``), and at least one comparison actually
        compared something. A run that compared nothing cannot pass."""
        if self.problems:
            return False
        if not any(a.compared_anything for a in self.assessments):
            return False
        return all(a.passed for a in self.assessments)

    def lines(self, *, sample: int = 15) -> list[str]:
        out: list[str] = []
        for a in self.assessments:
            c = a.comparison
            head = (
                f"{c.level:>11} {c.a_source} vs {c.b_source}: "
                f"{c.keys_compared} keys, facts {','.join(c.facts) or 'none'}"
            )
            out.append(head)
            counts = {"match": 0, "explained": 0, "unexplained": 0, "not_comparable": 0}
            for r in a.seasons:
                counts[r.status] += 1
            out.append(
                "            seasons: "
                f"{counts['match']} match, {counts['explained']} explained, "
                f"{counts['unexplained']} unexplained, "
                f"{counts['not_comparable']} not comparable"
            )
            for diff, entry_id in a.explained[:sample]:
                out.append(f"            explained by {entry_id}: {diff.describe()}")
            if len(a.explained) > sample:
                out.append(f"            ... {len(a.explained) - sample} more explained")
            for diff in a.unexplained[:sample]:
                out.append(f"  <-- FAIL  {diff.describe()}")
            if len(a.unexplained) > sample:
                out.append(f"  <-- FAIL  ... {len(a.unexplained) - sample} more unexplained")
            for item in a.stale[:sample]:
                out.append(f"  <-- FAIL  stale register entry: {item.describe()}")
            if c.overflow:
                out.append(
                    f"  <-- FAIL  {c.overflow} further differences were counted but not kept"
                )
            for season, source in a.not_comparable:
                out.append(f"            not comparable: {season} covered only by {source}")
        for note in self.notes:
            out.append(f"  note: {note}")
        for problem in self.problems:
            out.append(f"  <-- FAIL  {problem}")
        if not any(a.compared_anything for a in self.assessments):
            out.append("  <-- FAIL  no comparison compared anything; the gate cannot pass")
        return out


# --- Initial register (passmarks.md section 2) -------------------------------


_E1_FACTS = frozenset({"hr", "k", "bb", "r", "g"})


def _is_regular_gamelog(_a_source: str, b_source: str) -> bool:
    return b_source == "gamelog"


def _e1_explains(diff: Difference, ctx: Context) -> bool:
    """E1: the regular-season game log leaves out postseason and all-star games.

    Per key, ``other source - regular game log == post-season game log``. The
    post-season value is read from the same level and key, so the rule holds at
    season and at game level with one definition.
    """
    post = ctx.get(("gamelog_post", diff.level))
    if post is None:
        return False
    post_value = post.counts.get(diff.key, {}).get(diff.fact, 0)
    return post_value != 0 and diff.a_number - diff.b_number == post_value


def _e1_expects(comparison: Comparison, ctx: Context) -> Iterable[Expectation]:
    post = ctx.get(("gamelog_post", comparison.level))
    if post is None:
        return
    for key, row in post.counts.items():
        for fact, value in row.items():
            if value != 0 and fact in _E1_FACTS:
                yield Expectation(comparison.level, key, fact)


E1 = Entry(
    id="E1",
    summary="Regular-season game logs exclude postseason and all-star games",
    cause=(
        "retrosheet_gamelog holds regular-season games only; postseason and all-star "
        "games are in retrosheet_gamelog_post, and the other sources contain them."
    ),
    evidence=(
        "Session handoff 2026-09-27: game-log home runs were lower than event home runs "
        "by exactly the retrosheet_gamelog_post home runs (94, 97, 159, 116 checked). "
        "Evidence covers home runs only; the rule is checked for every fact."
    ),
    facts=_E1_FACTS,
    levels=frozenset({"season", "game"}),
    applies_to=_is_regular_gamelog,
    explains=_e1_explains,
    expects=_e1_expects,
)

INITIAL_REGISTER = Register(entries=(E1,))


def check_columns(
    actual: Mapping[str, frozenset[str]], contract: Mapping[str, frozenset[str]]
) -> list[str]:
    """Compare pinned column sets against what a table actually has (task 2.6,
    design D6). ``contract`` maps a table name to the columns it must have
    exactly; ``actual`` maps the same table names to what a live
    ``information_schema`` read found.

    A table absent from ``actual`` entirely, a pinned column the table no
    longer has, and a column the table now has that is not pinned are all
    reported -- an unpinned new column is exactly the case this check exists
    to catch, not something to pass through silently.
    """
    problems: list[str] = []
    for table in sorted(contract):
        expected = contract[table]
        found = actual.get(table)
        if found is None:
            problems.append(f"schema contract: {table} does not exist in this database")
            continue
        missing = sorted(expected - found)
        extra = sorted(found - expected)
        if missing:
            problems.append(f"schema contract: {table} is missing column(s) {', '.join(missing)}")
        if extra:
            problems.append(f"schema contract: {table} has unexpected column(s) {', '.join(extra)}")
    return problems


# --- Read-only database access ------------------------------------------------


def open_readonly(
    url: str, *, expect_db: str, statement_timeout_ms: int = 900_000
) -> psycopg.Connection:
    """Open a connection that cannot write, and refuse any other database.

    ``expect_db`` is the database the caller means to read. It must be given
    (never inferred from an environment name) and must equal the connected
    database, so a wrong ``DATABASE_URL`` fails before any query runs.
    """
    if not expect_db:
        raise TieOutError("an explicit database name is required (expect_db)")
    if not url:
        raise TieOutError("a database URL is required")
    conn = psycopg.connect(url)
    try:
        conn.read_only = True
        with conn.cursor() as cur:
            cur.execute("SELECT current_database()")
            row = cur.fetchone()
            actual = row[0] if row else None
            if actual != expect_db:
                raise TieOutError(
                    f"connected to database {actual!r}, expected {expect_db!r}; refusing to run"
                )
            cur.execute("SHOW transaction_read_only")
            row = cur.fetchone()
            if not row or row[0] != "on":
                raise TieOutError("connection is not read-only; refusing to run")
            # SET takes no bind parameters; the value is an int we validate here.
            cur.execute(f"SET statement_timeout = {int(statement_timeout_ms)}")
        conn.commit()
    except BaseException:
        conn.close()
        raise
    return conn


def fetch_series(
    conn: psycopg.Connection,
    source: str,
    level: str,
    facts: Iterable[str],
    sql: str,
    params: Mapping[str, Any] | Sequence[Any] | None = None,
) -> Series:
    """Run one read-only query and build its ``Series`` (see ``series_from_rows``
    for the column contract). The connection should come from ``open_readonly``."""
    with conn.cursor() as cur:
        cur.execute(sql, params)  # type: ignore[arg-type]  # resource text, not user input
        columns = [column.name for column in cur.description or ()]
        rows = cur.fetchall()
    conn.rollback()  # end the read-only transaction; nothing to commit
    return series_from_rows(source, level, facts, columns, rows)


def series_from_rows(
    source: str,
    level: str,
    facts: Iterable[str],
    columns: Sequence[str],
    rows: Iterable[Sequence[Any]],
) -> Series:
    """Build a ``Series`` from query output.

    The leading columns must be the level's key columns (``season``,
    ``game_id``, ``player_id`` as applicable, in that order); every column after
    them must be a declared fact. A NULL fact is a broken query, not a zero.
    """
    key_columns = KEY_COLUMNS[level]
    fact_set = frozenset(facts)
    if tuple(columns[: len(key_columns)]) != key_columns:
        raise TieOutError(
            f"{source} {level}: expected leading columns {key_columns}, got {tuple(columns)}"
        )
    fact_columns = tuple(columns[len(key_columns) :])
    unknown = set(fact_columns) - fact_set
    if unknown:
        raise TieOutError(f"{source} {level}: query returned undeclared facts {sorted(unknown)}")
    counts: dict[Key, dict[str, int]] = {}
    width = len(key_columns)
    for row in rows:
        key = tuple(str(part) for part in row[:width])
        if key in counts:
            raise TieOutError(f"{source} {level}: duplicate key {key!r}; the query must group")
        values: dict[str, int] = {}
        for name, value in zip(fact_columns, row[width:], strict=True):
            if value is None:
                raise TieOutError(f"{source} {level}: NULL {name} at {key!r}")
            values[name] = int(value)
        counts[key] = values
    return Series(source=source, level=level, facts=fact_set, counts=counts)
