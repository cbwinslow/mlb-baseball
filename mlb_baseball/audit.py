"""Read-only, bounded data-quality audits for the MLB research database.

``mlb doctor`` answers whether the installed system is operational. This module
answers whether the important game-level relations are safe for research and
model work. It deliberately targets declared contracts rather than scanning
every nullable raw-source column by default.
"""

from dataclasses import dataclass
from typing import Literal

import psycopg

from mlb_baseball.db import fetch_one, get_connection

Status = Literal["PASS", "WARN", "FAIL", "SKIP"]


@dataclass(frozen=True)
class Finding:
    """One exact, actionable result from a bounded audit rule."""

    name: str
    status: Status
    detail: str


def _relation_exists(cur: psycopg.Cursor, relation: str) -> bool:
    cur.execute("SELECT to_regclass(%s)", (relation,))
    return fetch_one(cur)[0] is not None


def _all(cur: psycopg.Cursor) -> list[tuple]:
    """Return query rows with the same explicit empty-result contract as fetch_one."""
    return cur.fetchall() or []


def _sample(values: list[object], *, limit: int = 5) -> str:
    shown = ", ".join(str(value) for value in values[:limit])
    return f"; sample: {shown}" if shown else ""


def _schedule_audit(cur: psycopg.Cursor) -> list[Finding]:
    if not _relation_exists(cur, "raw.mlb_schedule"):
        return [Finding("raw.mlb_schedule game ID", "SKIP", "table absent — ingest mlb_api first")]
    cur.execute(
        "SELECT count(*), count(*) FILTER (WHERE game_id IS NULL OR game_id = '') "
        "FROM raw.mlb_schedule"
    )
    total, missing = fetch_one(cur)
    required = Finding(
        "raw.mlb_schedule game ID",
        "PASS" if missing == 0 else "FAIL",
        f"{total:,} schedule observations; {missing:,} missing game_id",
    )
    cur.execute(
        """
        SELECT game_id FROM raw.mlb_schedule
        WHERE game_id IS NOT NULL AND game_id <> ''
        GROUP BY game_id HAVING count(*) > 1
        ORDER BY count(*) DESC, game_id LIMIT 5
        """
    )
    repeated = [row[0] for row in _all(cur)]
    cur.execute(
        """
        SELECT count(*) FROM (
            SELECT game_id FROM raw.mlb_schedule
            WHERE game_id IS NOT NULL AND game_id <> ''
            GROUP BY game_id HAVING count(*) > 1
        ) repeated
        """
    )
    repeated_count = fetch_one(cur)[0]
    history = Finding(
        "raw.mlb_schedule schedule history",
        "PASS",
        f"{repeated_count:,} repeated game IDs retained as schedule observations "
        f"(postponed/resumed history, not duplicate canonical games){_sample(repeated)}",
    )
    return [required, history]


def _core_game_audit(cur: psycopg.Cursor) -> list[Finding]:
    if not _relation_exists(cur, "core.game"):
        return [Finding("core.game MLB identity", "SKIP", "table absent — run mlb migrate")]
    cur.execute(
        """
        SELECT count(*), count(*) FILTER (WHERE game_pk IS NOT NULL AND game_pk <> ''),
               count(*) FILTER (WHERE game_pk IS NULL OR game_pk = '')
        FROM core.game
        """
    )
    total, populated, unresolved = fetch_one(cur)
    if total == 0:
        return [Finding("core.game MLB identity", "SKIP", "0 canonical games — run mlb conform")]
    cur.execute(
        """
        SELECT game_pk FROM core.game WHERE game_pk IS NOT NULL AND game_pk <> ''
        GROUP BY game_pk HAVING count(*) > 1 ORDER BY game_pk LIMIT 5
        """
    )
    duplicates = [row[0] for row in _all(cur)]
    cur.execute(
        """
        SELECT count(*) FROM (
            SELECT game_pk FROM core.game WHERE game_pk IS NOT NULL AND game_pk <> ''
            GROUP BY game_pk HAVING count(*) > 1
        ) duplicate_key
        """
    )
    duplicate_count = fetch_one(cur)[0]
    return [
        Finding(
            "core.game MLB identity",
            "PASS" if duplicate_count == 0 else "FAIL",
            f"{populated:,}/{total:,} populated ({populated / total:.1%}); "
            f"{unresolved:,} unresolved cross-source mappings; "
            f"{duplicate_count:,} duplicate populated keys{_sample(duplicates)}",
        )
    ]


def _doubleheader_audit(cur: psycopg.Cursor) -> Finding:
    if not _relation_exists(cur, "core.game"):
        return Finding("core.game doubleheader identity", "SKIP", "core.game absent")
    cur.execute("SELECT count(*) FROM core.game")
    if fetch_one(cur)[0] == 0:
        return Finding("core.game doubleheader identity", "SKIP", "0 canonical games")
    query = """
        WITH doubleheaders AS (
            SELECT game_date, away_team_id, home_team_id FROM core.game
            WHERE game_number IS NOT NULL
            GROUP BY game_date, away_team_id, home_team_id
            HAVING count(DISTINCT game_number) > 1
        ), collisions AS (
            SELECT g.game_date, g.away_team_id, g.home_team_id FROM core.game g
            JOIN doubleheaders d USING (game_date, away_team_id, home_team_id)
            WHERE g.game_pk IS NOT NULL AND g.game_pk <> ''
            GROUP BY g.game_date, g.away_team_id, g.home_team_id
            HAVING count(DISTINCT g.game_pk) < count(DISTINCT g.game_number)
        )
    """
    cur.execute(query + "SELECT count(*) FROM collisions")
    collisions = fetch_one(cur)[0]
    cur.execute(
        query
        + "SELECT game_date::text || ':' || away_team_id::text || ':' || home_team_id::text "
        "FROM collisions ORDER BY 1 LIMIT 5"
    )
    samples = [row[0] for row in _all(cur)]
    return Finding(
        "core.game doubleheader identity",
        "PASS" if collisions == 0 else "FAIL",
        f"{collisions:,} doubleheader groups with colliding populated game_pk values"
        f"{_sample(samples)}",
    )


def _foreign_key_audit(cur: psycopg.Cursor, table: str, column: str) -> Finding:
    if not _relation_exists(cur, table):
        return Finding(f"{table}.{column} referential integrity", "SKIP", "table absent")
    cur.execute(f"SELECT count(*) FROM {table}")
    total = fetch_one(cur)[0]
    if total == 0:
        return Finding(f"{table}.{column} referential integrity", "SKIP", f"0 {table} rows")
    cur.execute(
        f"""
        SELECT count(*), count(*) FILTER (WHERE child.{column} IS NULL),
               count(*) FILTER (WHERE child.{column} IS NOT NULL AND g.id IS NULL)
        FROM {table} child LEFT JOIN core.game g ON g.id = child.{column}
        """
    )
    rows, missing, orphans = fetch_one(cur)
    if table == "core.pitch":
        status: Status = "PASS" if orphans == 0 else "FAIL"
        null_text = f"{missing:,} unresolved ({missing / rows:.1%})"
    else:
        status = "PASS" if missing == 0 and orphans == 0 else "FAIL"
        null_text = f"{missing:,} missing"
    return Finding(
        f"{table}.{column} referential integrity",
        status,
        f"{rows:,} rows; {null_text}; {orphans:,} orphan references",
    )


def _pitch_resolution_audit(cur: psycopg.Cursor) -> Finding:
    """Show whether unresolved pitches still retain a repairable source key."""
    if not _relation_exists(cur, "core.pitch"):
        return Finding("core.pitch unresolved-key coverage", "SKIP", "table absent")
    cur.execute("SELECT count(*) FROM core.pitch")
    total = fetch_one(cur)[0]
    if total == 0:
        return Finding("core.pitch unresolved-key coverage", "SKIP", "0 core.pitch rows")
    cur.execute(
        """
        SELECT count(*) FILTER (WHERE game_id IS NULL),
               count(*) FILTER (WHERE game_id IS NULL AND source_game_pk IS NULL),
               array_agg(DISTINCT source_game_pk) FILTER (
                   WHERE game_id IS NULL AND source_game_pk IS NOT NULL
               )
        FROM core.pitch
        """
    )
    unresolved, missing_source_key, samples = fetch_one(cur)
    source_samples = list(samples or [])[:5]
    status: Status
    if missing_source_key > 0:
        status = "FAIL"
    elif unresolved > 0:
        status = "WARN"
    else:
        status = "PASS"
    return Finding(
        "core.pitch unresolved-key coverage",
        status,
        f"{unresolved:,}/{total:,} unresolved game links; "
        f"{missing_source_key:,} unresolved rows missing source_game_pk{_sample(source_samples)}",
    )


def _statcast_coverage_audit(cur: psycopg.Cursor) -> list[Finding]:
    if not _relation_exists(cur, "raw.statcast_pitch"):
        return [Finding("raw.statcast.pitch to core.game coverage", "SKIP", "table absent")]
    if not _relation_exists(cur, "core.game"):
        return [Finding("raw.statcast.pitch to core.game coverage", "SKIP", "core.game absent")]
    cur.execute("SELECT count(*) FROM core.game")
    if fetch_one(cur)[0] == 0:
        return [
            Finding(
                "raw.statcast.pitch to core.game coverage",
                "SKIP",
                "0 canonical games — run mlb conform before measuring coverage",
            )
        ]
    cur.execute(
        """
        SELECT COALESCE(NULLIF(s.game_year, ''), '<missing>'), count(*),
               count(*) FILTER (WHERE s.game_pk IS NULL OR s.game_pk = ''),
               count(*) FILTER (
                   WHERE s.game_pk IS NOT NULL AND s.game_pk <> '' AND g.id IS NULL
               )
        FROM raw.statcast_pitch s LEFT JOIN core.game g ON g.game_pk = s.game_pk
        GROUP BY COALESCE(NULLIF(s.game_year, ''), '<missing>') ORDER BY 1 DESC
        """
    )
    findings: list[Finding] = []
    for season, pitches, missing_source_key, no_canonical_game in _all(cur):
        unresolved = missing_source_key + no_canonical_game
        findings.append(
            Finding(
                f"raw.statcast.pitch to core.game coverage ({season})",
                "PASS" if unresolved == 0 else "WARN",
                f"{pitches:,} pitches; {pitches - unresolved:,} resolved; "
                f"{missing_source_key:,} missing source game_pk; "
                f"{no_canonical_game:,} have no matching canonical game",
            )
        )
    return findings


def _statcast_schedule_audit(cur: psycopg.Cursor) -> list[Finding]:
    """Measure the upstream side of the Statcast-to-game reconciliation.

    This intentionally scans the pitch-level raw table, so it is opt-in via
    ``mlb audit --scope statcast``.  It distinguishes a missing source key or
    schedule record from a later core-conformance gap.
    """
    if not _relation_exists(cur, "raw.statcast_pitch"):
        return [Finding("raw.statcast.pitch to raw.schedule coverage", "SKIP", "table absent")]
    if not _relation_exists(cur, "raw.mlb_schedule"):
        return [
            Finding(
                "raw.statcast.pitch to raw.schedule coverage",
                "SKIP",
                "raw.mlb_schedule is absent",
            )
        ]
    cur.execute(
        """
        WITH schedule_keys AS (
            SELECT DISTINCT game_id FROM raw.mlb_schedule
            WHERE game_id IS NOT NULL AND game_id <> ''
        )
        SELECT COALESCE(NULLIF(s.game_year, ''), '<missing>'), count(*),
               count(*) FILTER (WHERE s.game_pk IS NULL OR s.game_pk = ''),
               count(*) FILTER (
                   WHERE s.game_pk IS NOT NULL AND s.game_pk <> '' AND k.game_id IS NULL
               )
        FROM raw.statcast_pitch s LEFT JOIN schedule_keys k ON k.game_id = s.game_pk
        GROUP BY COALESCE(NULLIF(s.game_year, ''), '<missing>') ORDER BY 1 DESC
        """
    )
    findings: list[Finding] = []
    for season, pitches, missing_source_key, no_schedule_record in _all(cur):
        unresolved = missing_source_key + no_schedule_record
        findings.append(
            Finding(
                f"raw.statcast.pitch to raw.schedule coverage ({season})",
                "PASS" if unresolved == 0 else "WARN",
                f"{pitches:,} pitches; {pitches - unresolved:,} schedule candidates; "
                f"{missing_source_key:,} missing source game_pk; "
                f"{no_schedule_record:,} have no matching schedule record",
            )
        )
    return findings


def _game_feature_audit(cur: psycopg.Cursor) -> Finding:
    if not _relation_exists(cur, "gold.game_feature"):
        return Finding("gold.game_feature identity", "SKIP", "table absent")
    cur.execute("SELECT count(*) FROM gold.game_feature")
    total = fetch_one(cur)[0]
    if total == 0:
        return Finding("gold.game_feature identity", "SKIP", "0 feature rows")
    cur.execute(
        """
        SELECT count(*) FILTER (WHERE game_id IS NULL AND home_win IS NULL),
               count(*) FILTER (WHERE game_id IS NULL AND home_win IS NOT NULL),
               count(*) FILTER (WHERE game_id IS NOT NULL AND mlb_game_pk IS NULL)
        FROM gold.game_feature
        """
    )
    upcoming, invalid_completed, missing_completed_key = fetch_one(cur)
    failures = invalid_completed + missing_completed_key
    return Finding(
        "gold.game_feature identity",
        "PASS" if failures == 0 else "FAIL",
        f"{total:,} rows; {upcoming:,} expected upcoming rows without core game; "
        f"{invalid_completed:,} completed rows without core game; "
        f"{missing_completed_key:,} completed rows without MLB key",
    )


def _prediction_audit(cur: psycopg.Cursor) -> Finding:
    if not _relation_exists(cur, "gold.prediction"):
        return Finding("gold.prediction immutable identity", "SKIP", "table absent")
    cur.execute("SELECT count(*) FROM gold.prediction")
    total = fetch_one(cur)[0]
    if total == 0:
        return Finding("gold.prediction immutable identity", "SKIP", "0 prediction rows")
    cur.execute(
        """
        SELECT count(*) FROM (
            SELECT mlb_game_pk, model_version, generated_at FROM gold.prediction
            GROUP BY mlb_game_pk, model_version, generated_at HAVING count(*) > 1
        ) duplicates
        """
    )
    duplicates = fetch_one(cur)[0]
    return Finding(
        "gold.prediction immutable identity",
        "PASS" if duplicates == 0 else "FAIL",
        f"{total:,} rows; {duplicates:,} duplicate MLB-game/model/timestamp identities",
    )


def _database_health_audit(cur: psycopg.Cursor) -> list[Finding]:
    cur.execute(
        """
        SELECT relname, n_live_tup, n_dead_tup, last_analyze, last_autoanalyze
        FROM pg_stat_user_tables
        WHERE schemaname IN ('raw', 'core', 'gold')
          AND relname IN ('mlb_schedule', 'statcast_pitch', 'game', 'pitch', 'play', 'game_feature')
        ORDER BY relname
        """
    )
    findings = []
    for name, live, dead, manual, automatic in _all(cur):
        analyzed = manual or automatic
        findings.append(
            Finding(
                f"planner statistics {name}",
                "PASS" if analyzed is not None else "WARN",
                f"rows≈{live:,}; dead≈{dead:,}; last analyzed={analyzed or 'never'}",
            )
        )
    return findings


def run(scope: Literal["game", "database", "statcast"] = "game") -> list[Finding]:
    """Run the selected audit without changing database state."""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SET TRANSACTION READ ONLY")
            findings = _schedule_audit(cur)
            findings.extend(_core_game_audit(cur))
            findings.append(_doubleheader_audit(cur))
            findings.append(_foreign_key_audit(cur, "core.pitch", "game_id"))
            findings.append(_pitch_resolution_audit(cur))
            findings.append(_foreign_key_audit(cur, "core.play", "game_id"))
            findings.extend(_statcast_coverage_audit(cur))
            findings.append(_game_feature_audit(cur))
            findings.append(_prediction_audit(cur))
            if scope == "database":
                findings.extend(_database_health_audit(cur))
            if scope == "statcast":
                findings.extend(_statcast_schedule_audit(cur))
    return findings


def print_report(scope: Literal["game", "database", "statcast"] = "game") -> bool:
    """Print concise findings and return whether no audit rule failed."""
    findings = run(scope)
    for finding in findings:
        print(f"[{finding.status}] {finding.name}: {finding.detail}")
    failures = sum(finding.status == "FAIL" for finding in findings)
    warnings = sum(finding.status == "WARN" for finding in findings)
    skipped = sum(finding.status == "SKIP" for finding in findings)
    passed = len(findings) - failures - warnings - skipped
    print(
        f"\n{passed}/{len(findings)} passed; {warnings} warnings; "
        f"{failures} failures; {skipped} skipped"
    )
    return failures == 0
