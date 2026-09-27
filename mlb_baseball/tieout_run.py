"""Retrosheet tie-out runner: which sources are compared, at which levels, and how.

The pure comparison logic, the register and the read-only connection live in
``mlb_baseball.tieout``. This module owns the parts that know Retrosheet: the
list of sources (each a named, read-only SQL resource under
``mlb_baseball/sql/tieout_*.sql``), which pairs of sources are compared, and the
sequencing. ``scripts/verify_retrosheet_tie_out.py`` is a thin entry point over
``execute``.

Nothing here writes. Every query runs on a connection from
``tieout.open_readonly``.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass

import psycopg

from mlb_baseball import tieout
from mlb_baseball.sql import read_sql
from mlb_baseball.tieout import (
    INITIAL_REGISTER,
    LEVELS,
    Comparison,
    Register,
    Report,
    Series,
    TieOutError,
    assess,
    compare,
    coverage,
    fetch_series,
    merge_comparisons,
)

Log = Callable[[str], None]


def _print(line: str) -> None:
    print(line, flush=True)


FIRST_SEASON = 1871
LAST_SEASON = 2025  # Retrosheet's most recent published season (see passmarks.md section 3)

# "season", "game", "player_game" (tieout.LEVELS) select which Series
# comparisons run; "core" is a runner-level toggle for the core.play/core.game
# completeness check (task 2.5), which is not a Series comparison level.
RUN_LEVELS = (*LEVELS, "core")


@dataclass(frozen=True)
class SourceSpec:
    """One source at one level: the SQL resource and the facts it supplies."""

    name: str
    level: str
    resource: str
    facts: frozenset[str]
    context_only: bool = False  # loaded so a register rule can read it, never compared


def _facts(*names: str) -> frozenset[str]:
    return frozenset(names)


SOURCES: tuple[SourceSpec, ...] = (
    SourceSpec(
        "event", "season", "tieout_season_event.sql", _facts("pa", "k", "bb", "hr", "r", "g")
    ),
    SourceSpec(
        "csv_plays",
        "season",
        "tieout_season_csv_plays.sql",
        _facts("pa", "k", "bb", "hr", "r", "g"),
    ),
    SourceSpec(
        "csv_batting",
        "season",
        "tieout_season_csv_batting.sql",
        _facts("pa", "k", "bb", "hr", "r", "g"),
    ),
    SourceSpec("gameinfo", "season", "tieout_season_gameinfo.sql", _facts("r", "g")),
    SourceSpec("gamelog", "season", "tieout_season_gamelog.sql", _facts("hr", "k", "bb", "r", "g")),
    SourceSpec(
        "gamelog_post",
        "season",
        "tieout_season_gamelog_post.sql",
        _facts("hr", "k", "bb", "r", "g"),
        context_only=True,
    ),
    SourceSpec("box", "season", "tieout_season_box.sql", _facts("hr", "k", "bb", "r", "g")),
    SourceSpec("event", "game", "tieout_game_event.sql", _facts("pa", "k", "bb", "hr", "r", "g")),
    SourceSpec(
        "csv_plays", "game", "tieout_game_csv_plays.sql", _facts("pa", "k", "bb", "hr", "r", "g")
    ),
    SourceSpec(
        "csv_batting",
        "game",
        "tieout_game_csv_batting.sql",
        _facts("pa", "k", "bb", "hr", "r", "g"),
    ),
    SourceSpec("gameinfo", "game", "tieout_game_gameinfo.sql", _facts("r", "g")),
    SourceSpec("gamelog", "game", "tieout_game_gamelog.sql", _facts("hr", "k", "bb", "r", "g")),
    SourceSpec(
        "gamelog_post",
        "game",
        "tieout_game_gamelog_post.sql",
        _facts("hr", "k", "bb", "r", "g"),
        context_only=True,
    ),
    SourceSpec("box", "game", "tieout_game_box.sql", _facts("hr", "k", "bb", "r", "g")),
    # Runs scored are not attributed to a batter in the event table, and box
    # scores carry no plate-appearance count, so those facts are simply not
    # compared at player-game level (only facts both sides supply are).
    SourceSpec("event", "player_game", "tieout_player_event.sql", _facts("pa", "k", "bb", "hr")),
    SourceSpec(
        "csv_plays", "player_game", "tieout_player_csv_plays.sql", _facts("pa", "k", "bb", "hr")
    ),
    SourceSpec(
        "csv_batting",
        "player_game",
        "tieout_player_csv_batting.sql",
        _facts("pa", "k", "bb", "hr", "r"),
    ),
    SourceSpec("box", "player_game", "tieout_player_box.sql", _facts("hr", "k", "bb")),
)

# Upper bound on differences kept per pair and level (see tieout.compare). Reaching
# it fails the comparison; it exists only to bound memory if a source is broken.
DIFFERENCE_CAP = 100_000

# Pairs compared at every level a source exists for. The event files are the
# anchor; game info vs game log checks scores and game counts independently of
# the event parser.
PAIRS: tuple[tuple[str, str], ...] = (
    ("event", "csv_plays"),
    ("event", "csv_batting"),
    ("event", "gameinfo"),
    ("event", "gamelog"),
    ("event", "box"),
    ("gameinfo", "gamelog"),
    ("gameinfo", "box"),
)


def sources_for(level: str) -> dict[str, SourceSpec]:
    return {s.name: s for s in SOURCES if s.level == level}


def pairs_for(level: str) -> list[tuple[str, str]]:
    available = sources_for(level)
    return [
        (a, b)
        for a, b in PAIRS
        if a in available
        and b in available
        and not available[a].context_only
        and not available[b].context_only
    ]


def _params(lo: int, hi: int) -> dict[str, int]:
    return {"lo": lo, "hi": hi}


def load_source(conn: psycopg.Connection, spec: SourceSpec, lo: int, hi: int, log: Log) -> Series:
    started = time.monotonic()
    series = fetch_series(
        conn, spec.name, spec.level, spec.facts, read_sql(spec.resource), _params(lo, hi)
    )
    log(
        f"  loaded {spec.level} {spec.name}: {len(series.counts)} keys "
        f"in {time.monotonic() - started:.1f}s"
    )
    return series


def run_season_level(
    conn: psycopg.Connection,
    lo: int,
    hi: int,
    register: Register,
    report: Report,
    ctx: dict[tuple[str, str], Series],
    log: Log,
) -> dict[str, Series]:
    """Compare every configured pair of sources at season-total level and return
    the loaded series by source name (they decide which seasons are comparable)."""
    log(f"season totals, {lo}-{hi}")
    loaded = {
        name: load_source(conn, spec, lo, hi, log) for name, spec in sources_for("season").items()
    }
    for name, series in loaded.items():
        ctx[(name, "season")] = series
    for a_name, b_name in pairs_for("season"):
        a, b = loaded[a_name], loaded[b_name]
        cov = coverage(a, b)
        comparison = compare(a, b, seasons=cov.comparable)
        report.add(assess(comparison, register, ctx, only_a=cov.only_a, only_b=cov.only_b))
    return loaded


def run_detail_level(
    conn: psycopg.Connection,
    level: str,
    lo: int,
    hi: int,
    register: Register,
    report: Report,
    ctx: dict[tuple[str, str], Series],
    season_series: dict[str, Series],
    log: Log,
) -> None:
    """Compare every pair at ``game`` or ``player_game`` level, one season at a time.

    Which seasons a pair can be compared for comes from the season-total
    coverage, and a season total that matched (or was explained) never skips
    this level: two opposite errors can cancel inside one season total.
    """
    specs = sources_for(level)
    for name, spec in specs.items():
        if spec.context_only:
            ctx[(name, level)] = load_source(conn, spec, lo, hi, log)
    plans = {
        (a, b): coverage(season_series[a], season_series[b])
        for a, b in pairs_for(level)
        if a in season_series and b in season_series
    }
    seasons = sorted(set().union(*(cov.comparable for cov in plans.values())), key=int)
    log(f"{level} level: {len(seasons)} seasons, {len(plans)} pairs")
    parts: dict[tuple[str, str], list[Comparison]] = {pair: [] for pair in plans}
    for season in seasons:
        year = int(season)
        needed = sorted(
            {n for pair, cov in plans.items() if season in cov.comparable for n in pair}
        )
        loaded = {
            name: fetch_series(
                conn,
                name,
                level,
                specs[name].facts,
                read_sql(specs[name].resource),
                _params(year, year),
            )
            for name in needed
        }
        log(f"  {level} {season}: {', '.join(f'{n} {len(loaded[n].counts)}' for n in needed)}")
        for pair, cov in plans.items():
            if season in cov.comparable:
                parts[pair].append(
                    compare(
                        loaded[pair[0]],
                        loaded[pair[1]],
                        seasons=[season],
                        max_differences=DIFFERENCE_CAP,
                    )
                )
    for (a_name, b_name), cov in plans.items():
        if parts[(a_name, b_name)]:
            merged = merge_comparisons(parts[(a_name, b_name)], max_differences=DIFFERENCE_CAP)
        else:
            empty_a = Series(a_name, level, specs[a_name].facts, {})
            empty_b = Series(b_name, level, specs[b_name].facts, {})
            merged = compare(empty_a, empty_b, seasons=[])
        report.add(assess(merged, register, ctx, only_a=cov.only_a, only_b=cov.only_b))


def run_identity_check(
    conn: psycopg.Connection, lo: int, hi: int, report: Report, log: Log
) -> None:
    """List event batter and pitcher ids that resolve to no roster or all-players row.

    Unresolved identifiers are listed with season, count and an example game,
    never dropped. They are findings to triage (an issue), not a comparison
    between two sources, so they are notes and do not by themselves fail the gate.
    """
    log(f"identity check, {lo}-{hi}")
    started = time.monotonic()
    with conn.cursor() as cur:
        cur.execute(read_sql("tieout_identity_event.sql"), _params(lo, hi))
        rows = cur.fetchall()
    conn.rollback()
    for season, role, player_id, events, example_game in rows:
        report.notes.append(
            f"unresolved {role} id {player_id!r} in {season}: {events} events, "
            f"e.g. game {example_game}"
        )
    if not rows:
        report.notes.append(
            f"every event batter and pitcher id {lo}-{hi} resolves to a roster or all-players row"
        )
    log(f"  identity check: {len(rows)} unresolved ids in {time.monotonic() - started:.1f}s")


def run_core_check(
    conn: psycopg.Connection, lo: int, hi: int, register: Register, report: Report, log: Log
) -> None:
    """Compare core.play/core.game against the raw tables they are built from
    (task 2.5, audit findings G7/G8; see core-lineage.md for the exact mapping).

    Two ordinary comparisons (event games restricted to those in core.game vs
    core.play; game info vs core.game, both season-level) plus four diagnostics
    that ordinary key-by-key Series comparison cannot express: a full keyed
    comparison of every scoped event against core.play (catches a dropped or
    duplicated row even when the plate-appearance count is unchanged), sampled
    attribute equality for both tables, and a note (not a failure) for event
    games absent from core.game entirely.
    """
    log(f"core completeness check, {lo}-{hi}")
    event_core = SourceSpec(
        "event_core", "season", "tieout_season_event_core.sql", _facts("pa", "k", "bb", "hr", "g")
    )
    core_play = SourceSpec(
        "core_play", "season", "tieout_season_core_play.sql", _facts("pa", "k", "bb", "hr", "g")
    )
    core_game = SourceSpec("core_game", "season", "tieout_season_core_game.sql", _facts("r", "g"))
    gameinfo = sources_for("season")["gameinfo"]

    a, b = load_source(conn, event_core, lo, hi, log), load_source(conn, core_play, lo, hi, log)
    cov = coverage(a, b)
    report.add(
        assess(
            compare(a, b, seasons=cov.comparable, max_differences=DIFFERENCE_CAP),
            register,
            {},
            only_a=cov.only_a,
            only_b=cov.only_b,
        )
    )
    c, d = load_source(conn, gameinfo, lo, hi, log), load_source(conn, core_game, lo, hi, log)
    cov2 = coverage(c, d)
    report.add(
        assess(
            compare(c, d, seasons=cov2.comparable, max_differences=DIFFERENCE_CAP),
            register,
            {},
            only_a=cov2.only_a,
            only_b=cov2.only_b,
        )
    )

    _check_core_play_keys(conn, lo, hi, report, log)
    _check_core_play_attrs(conn, lo, hi, report, log)
    _check_core_game_attrs(conn, lo, hi, report, log)
    _check_core_game_duplicates(conn, lo, hi, report, log)
    _note_event_games_not_in_core(conn, lo, hi, report, log)


def _check_core_play_keys(
    conn: psycopg.Connection, lo: int, hi: int, report: Report, log: Log
) -> None:
    started = time.monotonic()
    with conn.cursor() as cur:
        cur.execute(read_sql("tieout_core_play_keys.sql"), _params(lo, hi))
        rows = cur.fetchall()
    conn.rollback()
    for season, _keys, missing, extra, dup, example_missing, example_extra in rows:
        if missing:
            report.problems.append(
                f"core.play season {season}: {missing} event rows are missing from core.play "
                f"(e.g. {example_missing})"
            )
        if extra:
            report.problems.append(
                f"core.play season {season}: {extra} core.play rows have no matching event row "
                f"(e.g. {example_extra})"
            )
        if dup:
            report.problems.append(
                f"core.play season {season}: {dup} duplicated (game, play_index) key(s) "
                f"in core.play"
            )
    log(f"  core.play key check: {len(rows)} season(s) in {time.monotonic() - started:.1f}s")


def _check_core_play_attrs(
    conn: psycopg.Connection, lo: int, hi: int, report: Report, log: Log
) -> None:
    started = time.monotonic()
    with conn.cursor() as cur:
        cur.execute(read_sql("tieout_core_play_attrs.sql"), _params(lo, hi))
        columns = [column.name for column in cur.description or ()]
        rows = cur.fetchall()
    conn.rollback()
    attrs = [c for c in columns if c not in ("season", "compared", "example")]
    for row in rows:
        values = dict(zip(columns, row, strict=True))
        for attr in attrs:
            if values[attr]:
                report.problems.append(
                    f"core.play season {values['season']}: {values[attr]} row(s) have a "
                    f"mismatched {attr} vs raw.retrosheet_event (e.g. {values['example']})"
                )
    log(f"  core.play attribute check: {len(rows)} season(s) in {time.monotonic() - started:.1f}s")


def _check_core_game_attrs(
    conn: psycopg.Connection, lo: int, hi: int, report: Report, log: Log
) -> None:
    started = time.monotonic()
    with conn.cursor() as cur:
        cur.execute(read_sql("tieout_core_game_attrs.sql"), _params(lo, hi))
        columns = [column.name for column in cur.description or ()]
        rows = cur.fetchall()
    conn.rollback()
    attrs = [
        c for c in columns if c not in ("season", "games", "missing_in_core", "example_missing")
    ]
    for row in rows:
        values = dict(zip(columns, row, strict=True))
        if values["missing_in_core"]:
            report.problems.append(
                f"core.game season {values['season']}: {values['missing_in_core']} "
                f"raw.retrosheet_gameinfo row(s) have no core.game row "
                f"(e.g. {values['example_missing']})"
            )
        for attr in attrs:
            if values[attr]:
                report.problems.append(
                    f"core.game season {values['season']}: {values[attr]} row(s) have a "
                    f"mismatched {attr} vs raw.retrosheet_gameinfo"
                )
    log(f"  core.game attribute check: {len(rows)} season(s) in {time.monotonic() - started:.1f}s")


def _check_core_game_duplicates(
    conn: psycopg.Connection, lo: int, hi: int, report: Report, log: Log
) -> None:
    started = time.monotonic()
    with conn.cursor() as cur:
        cur.execute(read_sql("tieout_core_game_duplicates.sql"), _params(lo, hi))
        rows = cur.fetchall()
    conn.rollback()
    for season, duplicated_rows, extra_in_core, example_extra in rows:
        if duplicated_rows:
            report.problems.append(
                f"core.game season {season}: {duplicated_rows} row(s) share a retro_game_id"
            )
        if extra_in_core:
            report.problems.append(
                f"core.game season {season}: {extra_in_core} row(s) have no matching "
                f"raw.retrosheet_gameinfo row (e.g. {example_extra})"
            )
    log(f"  core.game duplicate check: {len(rows)} season(s) in {time.monotonic() - started:.1f}s")


def _note_event_games_not_in_core(
    conn: psycopg.Connection, lo: int, hi: int, report: Report, log: Log
) -> None:
    started = time.monotonic()
    with conn.cursor() as cur:
        cur.execute(read_sql("tieout_event_games_not_in_core.sql"), _params(lo, hi))
        rows = cur.fetchall()
    conn.rollback()
    for season, games, example_game in rows:
        report.notes.append(
            f"season {season}: {games} event game(s) have no core.game row and are excluded "
            f"from core.play (e.g. {example_game}); see audit finding G7"
        )
    log(
        f"  event games not in core: {len(rows)} season(s) with a gap "
        f"in {time.monotonic() - started:.1f}s"
    )


def run_tieout(
    conn: psycopg.Connection,
    *,
    lo: int,
    hi: int,
    levels: Iterable[str] = ("season",),
    register: Register = INITIAL_REGISTER,
    log: Log = _print,
) -> Report:
    """Run seasons ``lo``..``hi`` and return the report.

    Season totals always run: they decide which seasons each pair can be
    compared for. ``game`` and ``player_game`` add the finer levels;
    ``player_game`` also runs the roster identity check.
    """
    wanted = tuple(levels)
    unknown = [level for level in wanted if level not in RUN_LEVELS]
    if unknown:
        raise TieOutError(f"unknown level(s) {unknown}; expected some of {RUN_LEVELS}")
    if lo > hi:
        raise TieOutError(f"season range is empty: {lo} > {hi}")
    report = Report()
    ctx: dict[tuple[str, str], Series] = {}
    season_series = run_season_level(conn, lo, hi, register, report, ctx, log)
    for level in ("game", "player_game"):
        if level in wanted:
            run_detail_level(conn, level, lo, hi, register, report, ctx, season_series, log)
    if "player_game" in wanted:
        run_identity_check(conn, lo, hi, report, log)
    if "core" in wanted:
        run_core_check(conn, lo, hi, register, report, log)
    return report


def describe_target(conn: psycopg.Connection) -> str:
    """Human-readable target (no password) for the line printed before running."""
    info = conn.info
    return f"database {info.dbname!r} on {info.host or 'local socket'} as {info.user!r}"


def execute(
    *,
    url: str,
    expect_db: str,
    lo: int,
    hi: int,
    levels: Iterable[str],
    dry_run: bool,
    statement_timeout_ms: int,
    out: Log = _print,
) -> int:
    """Entry point behind the script. Returns the process exit code:
    0 passed (or dry run ok), 1 the gate failed, 2 it could not run."""
    started = time.monotonic()
    levels = tuple(levels)
    try:
        conn = tieout.open_readonly(
            url, expect_db=expect_db, statement_timeout_ms=statement_timeout_ms
        )
    except (TieOutError, psycopg.Error) as exc:
        out(f"cannot run: {exc}")
        return 2
    try:
        out(f"target: {describe_target(conn)} (read-only)")
        out(f"seasons {lo}-{hi}, levels {', '.join(levels)}")
        if dry_run:
            out("dry run: connection verified read-only and on the expected database; no queries")
            return 0
        try:
            report = run_tieout(conn, lo=lo, hi=hi, levels=levels, log=out)
        except (TieOutError, psycopg.Error) as exc:
            out(f"cannot run: {exc}")
            return 2
    finally:
        conn.close()
    for line in report.lines():
        out(line)
    elapsed = time.monotonic() - started
    out(f"elapsed {elapsed:.1f}s")
    if report.passed:
        out("Retrosheet tie-out PASSED")
        return 0
    out("Retrosheet tie-out FAILED -- see above")
    return 1
