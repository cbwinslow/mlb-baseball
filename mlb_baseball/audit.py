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
from mlb_baseball.model import experiment

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


def _column_exists(cur: psycopg.Cursor, relation: str, column: str) -> bool:
    """Return whether an optional audit column exists without assuming raw shape."""
    schema, table = relation.split(".", maxsplit=1)
    cur.execute(
        """
        SELECT EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_schema = %s AND table_name = %s AND column_name = %s
        )
        """,
        (schema, table, column),
    )
    return fetch_one(cur)[0]


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
        (
            f"{total:,} schedule observations; {missing:,}/{total:,} "
            f"({missing / total:.1%}) missing game_id"
            if total
            else "0 schedule observations"
        ),
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
    findings = [
        Finding(
            "core.game MLB identity",
            "PASS" if duplicate_count == 0 else "FAIL",
            f"{populated:,}/{total:,} populated ({populated / total:.1%}); "
            f"{unresolved:,} unresolved cross-source mappings; "
            f"{duplicate_count:,} duplicate populated keys{_sample(duplicates)}",
        )
    ]
    cur.execute(
        """
        SELECT (season / 10) * 10 AS decade,
               CASE WHEN retro_game_id IS NULL THEN 'MLB-schedule-only'
                    ELSE 'Retrosheet-native' END AS source_group,
               count(*), count(*) FILTER (WHERE game_pk IS NOT NULL AND game_pk <> '')
        FROM core.game
        GROUP BY 1, 2 ORDER BY 1 DESC, 2
        """
    )
    for decade, source_group, rows, with_key in _all(cur):
        missing = rows - with_key
        status: Status = "PASS" if missing == 0 else "WARN"
        findings.append(
            Finding(
                f"core.game MLB-key coverage ({decade}s; {source_group})",
                status,
                f"{with_key:,}/{rows:,} populated ({with_key / rows:.1%}); "
                f"{missing:,} unresolved or provider-native rows",
            )
        )
    return findings


def _core_game_validity_audit(cur: psycopg.Cursor) -> list[Finding]:
    """Check stable game facts without pretending historical optional fields are required."""
    if not _relation_exists(cur, "core.game"):
        return [Finding("core.game basic validity", "SKIP", "core.game absent")]
    cur.execute("SELECT count(*) FROM core.game")
    total = fetch_one(cur)[0]
    if total == 0:
        return [Finding("core.game basic validity", "SKIP", "0 canonical games")]
    cur.execute(
        """
        SELECT count(*) FILTER (
                   WHERE season < 1871 OR season > EXTRACT(YEAR FROM CURRENT_DATE)::integer + 1
               ),
               count(*) FILTER (
                   WHERE game_date < DATE '1871-01-01' OR game_date > CURRENT_DATE + 366
               ),
               count(*) FILTER (WHERE game_number IS NOT NULL AND game_number < 0),
               count(*) FILTER (WHERE away_score IS NOT NULL AND away_score < 0),
               count(*) FILTER (WHERE home_score IS NOT NULL AND home_score < 0)
        FROM core.game
        """
    )
    bad_season, bad_date, bad_number, bad_away_score, bad_home_score = fetch_one(cur)
    violations = bad_season + bad_date + bad_number + bad_away_score + bad_home_score
    return [
        Finding(
            "core.game basic validity",
            "PASS" if violations == 0 else "FAIL",
            f"{total:,} rows; {bad_season:,} invalid seasons; {bad_date:,} invalid dates; "
            f"{bad_number:,} invalid game numbers; "
            f"{bad_away_score + bad_home_score:,} negative scores",
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
        query + "SELECT game_date::text || ':' || away_team_id::text || ':' || home_team_id::text "
        "FROM collisions ORDER BY 1 LIMIT 5"
    )
    samples = [row[0] for row in _all(cur)]
    return Finding(
        "core.game doubleheader identity",
        "PASS" if collisions == 0 else "FAIL",
        f"{collisions:,} doubleheader groups with colliding populated game_pk values"
        f"{_sample(samples)}",
    )


def _foreign_key_audit(
    cur: psycopg.Cursor,
    table: str,
    column: str,
    *,
    parent_table: str = "core.game",
    parent_column: str = "id",
    nulls_are_expected: bool = False,
) -> Finding:
    if not _relation_exists(cur, table):
        return Finding(f"{table}.{column} referential integrity", "SKIP", "table absent")
    if not _relation_exists(cur, parent_table):
        return Finding(
            f"{table}.{column} referential integrity",
            "SKIP",
            f"parent table {parent_table} absent",
        )
    cur.execute(f"SELECT count(*) FROM {table}")
    total = fetch_one(cur)[0]
    if total == 0:
        return Finding(f"{table}.{column} referential integrity", "SKIP", f"0 {table} rows")
    cur.execute(
        f"""
        SELECT count(*), count(*) FILTER (WHERE child.{column} IS NULL),
               count(*) FILTER (WHERE child.{column} IS NOT NULL AND g.id IS NULL)
        FROM {table} child LEFT JOIN {parent_table} g ON g.{parent_column} = child.{column}
        """
    )
    rows, missing, orphans = fetch_one(cur)
    if nulls_are_expected:
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


def _play_value_audit(cur: psycopg.Cursor) -> Finding:
    """Check the few play fields whose domains are stable across providers."""
    if not _relation_exists(cur, "core.play"):
        return Finding("core.play controlled values", "SKIP", "core.play absent")
    cur.execute("SELECT count(*) FROM core.play")
    total = fetch_one(cur)[0]
    if total == 0:
        return Finding("core.play controlled values", "SKIP", "0 core.play rows")
    cur.execute(
        """
        SELECT count(*) FILTER (WHERE source NOT IN ('retrosheet', 'mlb_api')),
               count(*) FILTER (WHERE inning IS NOT NULL AND inning < 1),
               count(*) FILTER (
                   WHERE half_inning IS NOT NULL AND half_inning NOT IN ('top', 'bottom')
               ),
               -- The Stats API occasionally reports the terminal count
               -- after a walk/strikeout (5 balls or 4 strikes). Preserve
               -- that source convention instead of treating it as corrupt.
               count(*) FILTER (WHERE balls IS NOT NULL AND balls NOT BETWEEN 0 AND 5),
               count(*) FILTER (WHERE strikes IS NOT NULL AND strikes NOT BETWEEN 0 AND 4),
               count(*) FILTER (WHERE outs IS NOT NULL AND outs NOT BETWEEN 0 AND 3)
        FROM core.play
        """
    )
    bad_source, bad_inning, bad_half, bad_balls, bad_strikes, bad_outs = fetch_one(cur)
    violations = bad_source + bad_inning + bad_half + bad_balls + bad_strikes + bad_outs
    return Finding(
        "core.play controlled values",
        "PASS" if violations == 0 else "FAIL",
        f"{total:,} rows; {bad_source:,} invalid sources; {bad_inning:,} invalid innings; "
        f"{bad_half:,} invalid half-innings; {bad_balls + bad_strikes + bad_outs:,} invalid counts",
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


def _unresolved_statcast_key_classification_audit(cur: psycopg.Cursor) -> list[Finding]:
    """Classify unresolved provider keys without treating source history as corruption."""
    required_columns = ("game_id", "game_type", "status", "_season")
    if not _relation_exists(cur, "core.pitch") or not _relation_exists(cur, "raw.mlb_schedule"):
        return [
            Finding(
                "core.pitch unresolved provider-key classification",
                "SKIP",
                "required table absent",
            )
        ]
    if any(not _column_exists(cur, "raw.mlb_schedule", column) for column in required_columns):
        return [
            Finding(
                "core.pitch unresolved provider-key classification",
                "SKIP",
                "raw.mlb_schedule lacks game-type/status fields",
            )
        ]
    cur.execute(
        """
        WITH unresolved AS (
            SELECT DISTINCT source_game_pk AS game_pk
            FROM core.pitch
            WHERE game_id IS NULL AND source_game_pk IS NOT NULL AND source_game_pk <> ''
        ), schedule_rollup AS (
            SELECT
                u.game_pk,
                max(ms._season) AS season,
                count(ms.game_id) AS observations,
                count(*) FILTER (WHERE ms.status IN ('Final', 'Completed Early', 'Forfeit'))
                    AS terminal_observations,
                bool_or(ms.game_type = 'S' AND ms.status IN ('Final', 'Completed Early', 'Forfeit'))
                    AS completed_spring,
                bool_or(ms.game_type = 'R' AND ms.status IN ('Final', 'Completed Early', 'Forfeit'))
                    AS completed_regular,
                bool_or(ms.game_type IN ('F', 'D', 'L', 'W', 'A', 'E')) AS special_game,
                bool_or(ms.status IN ('Postponed', 'Suspended', 'Cancelled')) AS schedule_history
            FROM unresolved u
            LEFT JOIN raw.mlb_schedule ms ON ms.game_id = u.game_pk
            GROUP BY u.game_pk
        ), classified AS (
            SELECT *, CASE
                WHEN observations = 0 THEN 'missing schedule record'
                WHEN completed_spring THEN 'completed Spring Training'
                WHEN terminal_observations > 1 THEN 'ambiguous terminal schedule history'
                WHEN completed_regular THEN 'completed regular season'
                WHEN schedule_history THEN 'postponed/suspended schedule history'
                WHEN special_game THEN 'postseason/all-star/exhibition'
                ELSE 'other provider/source difference'
            END AS category
            FROM schedule_rollup
        )
        SELECT category, coalesce(season, '<missing>'), count(*),
               (array_agg(game_pk ORDER BY game_pk))[1:5]
        FROM classified
        GROUP BY category, season
        ORDER BY category, season DESC
        """
    )
    findings: list[Finding] = []
    for category, season, keys, samples in _all(cur):
        findings.append(
            Finding(
                f"core.pitch unresolved provider keys ({category}; {season})",
                "WARN",
                f"{keys:,} provider keys retained without a canonical link"
                f"{_sample(list(samples or []))}",
            )
        )
    return findings or [
        Finding(
            "core.pitch unresolved provider-key classification",
            "PASS",
            "no unresolved provider keys",
        )
    ]


def _team_link_coverage_audit(cur: psycopg.Cursor) -> list[Finding]:
    """Make historical team-link gaps visible by source code and era."""
    if (
        not _relation_exists(cur, "core.game")
        or not _relation_exists(cur, "raw.retrosheet_gameinfo")
        or not _column_exists(cur, "raw.retrosheet_gameinfo", "gid")
        or not _column_exists(cur, "raw.retrosheet_gameinfo", "visteam")
        or not _column_exists(cur, "raw.retrosheet_gameinfo", "hometeam")
        or not _column_exists(cur, "raw.retrosheet_gameinfo", "_season")
    ):
        return [Finding("core.game team-link coverage", "SKIP", "required table/column absent")]
    cur.execute(
        """
        WITH links AS (
            SELECT 'away' AS side, gi.visteam AS team_code, gi._season::integer AS season,
                   g.away_team_id AS team_id
            FROM raw.retrosheet_gameinfo gi JOIN core.game g ON g.retro_game_id = gi.gid
            UNION ALL
            SELECT 'home', gi.hometeam, gi._season::integer, g.home_team_id
            FROM raw.retrosheet_gameinfo gi JOIN core.game g ON g.retro_game_id = gi.gid
        ), missing AS (
            SELECT side, team_code, min(season) AS first_season,
                   max(season) AS last_season, count(*) AS games
            FROM links WHERE team_id IS NULL
            GROUP BY side, team_code
        )
        SELECT side, team_code, first_season, last_season, games
        FROM missing ORDER BY games DESC, side, team_code LIMIT 10
        """
    )
    samples = _all(cur)
    cur.execute(
        """
        WITH links AS (
            SELECT g.away_team_id AS team_id FROM raw.retrosheet_gameinfo gi
            JOIN core.game g ON g.retro_game_id = gi.gid
            UNION ALL
            SELECT g.home_team_id FROM raw.retrosheet_gameinfo gi
            JOIN core.game g ON g.retro_game_id = gi.gid
        )
        SELECT count(*), count(*) FILTER (WHERE team_id IS NULL) FROM links
        """
    )
    total, unresolved = fetch_one(cur)
    detail_samples = ", ".join(
        f"{side}:{code} {first}-{last} ({games:,})"
        for side, code, first, last, games in samples[:5]
    )
    return [
        Finding(
            "core.game team-link coverage",
            "PASS" if unresolved == 0 else "WARN",
            f"{total - unresolved:,}/{total:,} resolved; "
            f"{unresolved:,} unresolved Retrosheet side-links"
            + (f"; largest: {detail_samples}" if detail_samples else ""),
        )
    ]


def _game_feature_audit(cur: psycopg.Cursor) -> Finding:
    if not _relation_exists(cur, "gold.game_feature"):
        return Finding("gold.game_feature identity", "SKIP", "table absent")
    cur.execute("SELECT count(*) FROM gold.game_feature")
    total = fetch_one(cur)[0]
    if total == 0:
        return Finding("gold.game_feature identity", "SKIP", "0 feature rows")
    cur.execute(
        """
        SELECT count(*) FILTER (
                   WHERE f.game_id IS NULL AND f.home_win IS NULL AND f.mlb_game_pk IS NOT NULL
               ),
               count(*) FILTER (WHERE f.game_id IS NULL AND f.home_win IS NOT NULL),
               count(*) FILTER (WHERE f.game_id IS NULL AND f.mlb_game_pk IS NULL),
               count(*) FILTER (
                   WHERE f.game_id IS NOT NULL AND f.mlb_game_pk IS NULL AND g.game_pk IS NULL
               ),
               count(*) FILTER (
                   WHERE f.game_id IS NOT NULL AND f.mlb_game_pk IS NULL AND g.game_pk IS NOT NULL
               ),
               count(*) FILTER (
                   WHERE f.game_id IS NOT NULL AND f.mlb_game_pk IS NOT NULL
                     AND g.game_pk IS NOT NULL AND f.mlb_game_pk <> g.game_pk
               )
        FROM gold.game_feature f LEFT JOIN core.game g ON g.id = f.game_id
        """
    )
    (
        upcoming,
        invalid_completed,
        missing_identity,
        retrosheet_native,
        missing_mlb_key,
        mismatched_mlb_key,
    ) = fetch_one(cur)
    failures = invalid_completed + missing_identity + missing_mlb_key + mismatched_mlb_key
    return Finding(
        "gold.game_feature identity",
        "PASS" if failures == 0 else "FAIL",
        f"{total:,} rows; {upcoming:,} expected upcoming rows without core game; "
        f"{invalid_completed:,} completed rows without core game; "
        f"{retrosheet_native:,} Retrosheet-native completed rows without MLB key; "
        f"{missing_identity:,} rows without either identity; "
        f"{missing_mlb_key:,} missing MLB keys; {mismatched_mlb_key:,} mismatched MLB keys",
    )


def _game_feature_cutoff_audit(cur: psycopg.Cursor) -> Finding:
    """Bounded contract check for the first strict MLB feature family."""
    if not _relation_exists(cur, "gold.game_feature") or not _column_exists(
        cur, "gold.game_feature", "feature_cutoff_at"
    ):
        return Finding("gold.game_feature cutoff", "SKIP", "migration 0046 not applied")
    cur.execute(
        "SELECT count(*), count(*) FILTER (WHERE feature_cutoff_at IS NULL), "
        "count(*) FILTER (WHERE mlb_game_pk IS NULL) FROM gold.game_feature"
    )
    total, missing_cutoff, missing_key = fetch_one(cur)
    if total == 0:
        return Finding("gold.game_feature cutoff", "SKIP", "0 feature rows")
    failures = missing_cutoff + missing_key
    return Finding(
        "gold.game_feature cutoff",
        "PASS" if failures == 0 else "FAIL",
        f"{total:,} rows; {missing_cutoff:,} missing feature cutoff; "
        f"{missing_key:,} missing MLB key",
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


def _experiment_snapshot_audit(conn: psycopg.Connection, cur: psycopg.Cursor) -> Finding:
    """Verify preserved experiment inputs without trusting mutable gold rows."""
    if not _relation_exists(cur, "meta.experiment_snapshot") or not _relation_exists(
        cur, "gold.game_feature_snapshot"
    ):
        return Finding("experiment snapshots", "SKIP", "migration 0047 not applied")
    cur.execute("SELECT count(*) FROM meta.experiment_snapshot")
    snapshots = fetch_one(cur)[0]
    if snapshots == 0:
        return Finding(
            "experiment snapshots",
            "SKIP",
            "no immutable experiment snapshot yet — run mlb experiment snapshot",
        )
    cur.execute(
        """
        SELECT count(*) FILTER (WHERE actual_rows <> expected_rows),
               count(*)
        FROM (
            SELECT s.snapshot_id, s.row_count AS expected_rows, count(g.*) AS actual_rows
            FROM meta.experiment_snapshot s
            LEFT JOIN gold.game_feature_snapshot g USING (snapshot_id)
            GROUP BY s.snapshot_id, s.row_count
        ) coverage
        """
    )
    mismatches, _ = fetch_one(cur)
    cur.execute(
        """
        SELECT count(*) FROM (
            SELECT snapshot_id, game_instance_key
            FROM gold.game_feature_snapshot
            GROUP BY snapshot_id, game_instance_key HAVING count(*) > 1
        ) duplicates
        """
    )
    duplicates = fetch_one(cur)[0]
    integrity = experiment.snapshot_integrity(conn)
    checksum_mismatches = integrity["row_hash_mismatches"] + integrity["selection_hash_mismatches"]
    failures = mismatches + duplicates + checksum_mismatches
    return Finding(
        "experiment snapshots",
        "PASS" if failures == 0 else "FAIL",
        f"{snapshots:,} immutable snapshot(s); {mismatches:,} row-count mismatch(es); "
        f"{duplicates:,} duplicate snapshot keys; {checksum_mismatches:,} checksum mismatch(es). "
        "This checks preserved copies, not mutable gold.game_feature equivalence.",
    )


def _database_health_audit(cur: psycopg.Cursor) -> list[Finding]:
    cur.execute(
        """
        SELECT t.schemaname, t.relname, t.n_live_tup, t.n_dead_tup,
               t.last_analyze, t.last_autoanalyze,
               COALESCE(i.index_scans, 0)
        FROM pg_stat_user_tables t
        LEFT JOIN LATERAL (
            SELECT sum(idx_scan) AS index_scans
            FROM pg_stat_user_indexes i
            WHERE i.schemaname = t.schemaname AND i.relname = t.relname
        ) i ON TRUE
        WHERE t.schemaname IN ('raw', 'core', 'gold')
          AND t.relname IN (
              'mlb_schedule', 'statcast_pitch', 'game', 'pitch', 'play',
              'game_feature', 'prediction'
          )
        ORDER BY t.schemaname, t.relname
        """
    )
    findings = []
    for schema, name, live, dead, manual, automatic, index_scans in _all(cur):
        analyzed = manual or automatic
        if live == 0:
            status: Status = "SKIP"
        elif analyzed is None:
            status = "WARN"
        else:
            status = "PASS"
        findings.append(
            Finding(
                f"database health {schema}.{name}",
                status,
                f"rows≈{live:,}; dead≈{dead:,}; index scans≈{index_scans:,}; "
                f"last analyzed={analyzed or 'never'}",
            )
        )
    cur.execute(
        """
        WITH index_definition AS (
            SELECT n.nspname || '.' || t.relname AS relation,
                   i.relname AS index_name,
                   x.indisunique, x.indisprimary, x.indkey::text,
                   x.indclass::text, x.indcollation::text, x.indoption::text,
                   coalesce(pg_get_expr(x.indexprs, x.indrelid), '') AS expressions,
                   coalesce(pg_get_expr(x.indpred, x.indrelid), '') AS predicate
            FROM pg_index x
            JOIN pg_class t ON t.oid = x.indrelid
            JOIN pg_namespace n ON n.oid = t.relnamespace
            JOIN pg_class i ON i.oid = x.indexrelid
            WHERE n.nspname IN ('raw', 'core', 'gold') AND x.indisvalid
        ), duplicate_group AS (
            SELECT relation, string_agg(index_name, ', ' ORDER BY index_name) AS names
            FROM index_definition
            GROUP BY relation, indisunique, indisprimary, indkey, indclass,
                     indcollation, indoption, expressions, predicate
            HAVING count(*) > 1
        )
        SELECT relation, names FROM duplicate_group ORDER BY relation
        """
    )
    duplicates = _all(cur)
    if duplicates:
        details = "; ".join(f"{relation}: {names}" for relation, names in duplicates[:5])
        more = f" (+{len(duplicates) - 5} more)" if len(duplicates) > 5 else ""
        findings.append(
            Finding(
                "database duplicate indexes",
                "WARN",
                f"{len(duplicates)} exact duplicate index definition group(s): {details}{more}",
            )
        )
    else:
        findings.append(Finding("database duplicate indexes", "PASS", "none found"))
    for relation in ("raw.mlb_schedule", "raw.statcast_pitch"):
        if not _relation_exists(cur, relation) or not _column_exists(cur, relation, "_loaded_at"):
            continue
        cur.execute(f"SELECT count(*), max(_loaded_at) FROM {relation}")
        rows, last_loaded = fetch_one(cur)
        findings.append(
            Finding(
                f"table freshness {relation}",
                "PASS" if rows > 0 and last_loaded is not None else "WARN",
                f"{rows:,} rows; latest landed artifact at {last_loaded or 'unknown'}",
            )
        )
    return findings


def run(scope: Literal["game", "database", "statcast"] = "game") -> list[Finding]:
    """Run the selected audit without changing database state."""
    if scope not in {"game", "database", "statcast"}:
        raise ValueError(f"unknown audit scope: {scope}")
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SET TRANSACTION READ ONLY")
            findings = _schedule_audit(cur)
            findings.extend(_core_game_audit(cur))
            findings.extend(_core_game_validity_audit(cur))
            findings.append(_doubleheader_audit(cur))
            findings.append(
                _foreign_key_audit(
                    cur,
                    "core.game",
                    "away_team_id",
                    parent_table="core.team",
                    nulls_are_expected=True,
                )
            )
            findings.append(
                _foreign_key_audit(
                    cur,
                    "core.game",
                    "home_team_id",
                    parent_table="core.team",
                    nulls_are_expected=True,
                )
            )
            findings.append(
                _foreign_key_audit(cur, "core.pitch", "game_id", nulls_are_expected=True)
            )
            findings.append(_pitch_resolution_audit(cur))
            findings.append(_foreign_key_audit(cur, "core.play", "game_id"))
            findings.append(_play_value_audit(cur))
            findings.extend(_team_link_coverage_audit(cur))
            findings.extend(_statcast_coverage_audit(cur))
            findings.append(_game_feature_audit(cur))
            findings.append(_game_feature_cutoff_audit(cur))
            findings.append(_prediction_audit(cur))
            findings.append(_experiment_snapshot_audit(conn, cur))
            if scope == "database":
                findings.extend(_database_health_audit(cur))
            if scope == "statcast":
                findings.extend(_statcast_schedule_audit(cur))
                findings.extend(_unresolved_statcast_key_classification_audit(cur))
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
