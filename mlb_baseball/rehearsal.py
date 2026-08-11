"""Bounded, read-only production-to-test conformance rehearsal support."""

from collections.abc import Iterable
from dataclasses import dataclass

import psycopg
from psycopg import sql

SEASONS = (2008, 2015, 2024, 2025, 2026)
_DYNAMIC_SAMPLE_RELATIONS = (
    "raw.retrosheet_team",
    "raw.retrosheet_gameinfo",
    "raw.mlb_schedule",
    "raw.retrosheet_event",
    "raw.mlb_playbyplay",
    "raw.statcast_pitch",
)


@dataclass(frozen=True)
class SampleResult:
    """Exact landed-row counts for one bounded rehearsal sample."""

    rows: dict[str, int]


def _database_name(url: str) -> str:
    value = psycopg.conninfo.conninfo_to_dict(url).get("dbname", "")
    return value if isinstance(value, str) else ""


def assert_safe_urls(source_url: str, target_url: str) -> None:
    """Reject a same-database copy or a target that is not clearly disposable."""
    source_name = _database_name(source_url)
    target_name = _database_name(target_url)
    if not source_name or not target_name:
        raise ValueError("source and target URLs must include database names")
    if source_name == target_name:
        raise ValueError("source and target databases must differ")
    if "test" not in target_name.lower():
        raise ValueError("target database name must contain 'test'")


def clear_sample(target_url: str) -> None:
    """Remove the bounded sample and its derived core rows from ``mlb_test``.

    This is deliberately narrower than a database reset: migrations and
    stable metadata remain intact.  It makes an operator's next rehearsal or
    the normal test suite start from the same clean raw/core boundary.
    """
    target_name = _database_name(target_url)
    if not target_name or "test" not in target_name.lower():
        raise ValueError("target database name must contain 'test'")
    with psycopg.connect(target_url) as target, target.cursor() as cur:
        for relation in _DYNAMIC_SAMPLE_RELATIONS:
            cur.execute(
                sql.SQL("DROP TABLE IF EXISTS {}").format(sql.Identifier(*relation.split(".")))
            )
        cur.execute("TRUNCATE raw.register_people")
        for relation in (
            "core.play",
            "core.pitch",
            "core.market",
            "gold.game_feature",
            "gold.prediction",
            "core.game",
            "core.team_alias",
            "core.player_war",
            "core.standing",
            "core.player",
            "core.team",
            "core.venue",
        ):
            cur.execute(sql.SQL("DELETE FROM {}").format(sql.Identifier(*relation.split("."))))


def _columns(cur: psycopg.Cursor, relation: str) -> list[tuple[str, str]]:
    schema, table = relation.split(".", maxsplit=1)
    cur.execute(
        """
        SELECT a.attname, pg_catalog.format_type(a.atttypid, a.atttypmod)
        FROM pg_attribute a
        JOIN pg_class c ON c.oid = a.attrelid
        JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname = %s AND c.relname = %s
          AND a.attnum > 0 AND NOT a.attisdropped
        ORDER BY a.attnum
        """,
        (schema, table),
    )
    return list(cur.fetchall())


def _copy_query(
    source: psycopg.Connection,
    target: psycopg.Connection,
    relation: str,
    query: str,
    params: tuple[object, ...],
    *,
    recreate: bool,
) -> int:
    schema, table = relation.split(".", maxsplit=1)
    with source.cursor() as source_cur:
        columns = _columns(source_cur, relation)
    names = [name for name, _ in columns]
    with target.cursor() as target_cur:
        if recreate:
            target_cur.execute(
                sql.SQL("DROP TABLE IF EXISTS {}.{}").format(
                    sql.Identifier(schema), sql.Identifier(table)
                )
            )
            definitions = sql.SQL(", ").join(
                sql.SQL("{} {}").format(sql.Identifier(name), sql.SQL(type_name))
                for name, type_name in columns
            )
            target_cur.execute(
                sql.SQL("CREATE TABLE {}.{} ({})").format(
                    sql.Identifier(schema), sql.Identifier(table), definitions
                )
            )
        else:
            target_cur.execute(
                sql.SQL("TRUNCATE {}.{}").format(sql.Identifier(schema), sql.Identifier(table))
            )
        insert = sql.SQL("INSERT INTO {}.{} ({}) VALUES ({})").format(
            sql.Identifier(schema),
            sql.Identifier(table),
            sql.SQL(", ").join(map(sql.Identifier, names)),
            sql.SQL(", ").join(sql.Placeholder() for _ in names),
        )
        count = 0
        with source.cursor() as source_cur:
            source_cur.execute(query, params)
            while rows := source_cur.fetchmany(1000):
                target_cur.executemany(insert, rows)
                count += len(rows)
    target.commit()
    return count


def load_sample(
    source_url: str,
    target_url: str,
    *,
    seasons: Iterable[int] = SEASONS,
    games_per_season: int = 10,
) -> SampleResult:
    """Copy a bounded multi-season raw sample without writing to the source."""
    assert_safe_urls(source_url, target_url)
    selected_seasons = tuple(sorted(set(seasons)))
    if not selected_seasons or games_per_season < 1:
        raise ValueError("at least one season and one game per season are required")
    params = (list(map(str, selected_seasons)), games_per_season)
    current_params = (str(max(selected_seasons)), games_per_season)
    game_cte = """
        WITH matched AS (
            SELECT DISTINCT gi.gid, gi._season
            FROM raw.retrosheet_gameinfo gi
            JOIN raw.retrosheet_team away ON away.team_id = gi.visteam
                AND gi._season::integer BETWEEN away.first_year::integer AND away.last_year::integer
            JOIN raw.retrosheet_team home ON home.team_id = gi.hometeam
                AND gi._season::integer BETWEEN home.first_year::integer AND home.last_year::integer
            JOIN raw.mlb_schedule ms ON ms.game_date::date = to_date(gi.date, 'YYYYMMDD')
                AND ms.away_name = away.city || ' ' || away.nickname
                AND ms.home_name = home.city || ' ' || home.nickname
                AND COALESCE(NULLIF(ms.game_num, '')::integer, 1)
                    = COALESCE(NULLIF(gi.number, '')::integer, 1)
            WHERE gi._season = ANY(%s) AND ms.status IN ('Final', 'Completed Early', 'Forfeit')
        ), ranked AS (
            SELECT gid, row_number() OVER (PARTITION BY _season ORDER BY gid) AS n FROM matched
        ) SELECT gid FROM ranked WHERE n <= %s
    """
    counts: dict[str, int] = {}
    with psycopg.connect(source_url) as source, psycopg.connect(target_url) as target:
        with source.cursor() as cur:
            cur.execute("SET TRANSACTION READ ONLY")
        counts["raw.retrosheet_team"] = _copy_query(
            source,
            target,
            "raw.retrosheet_team",
            "SELECT * FROM raw.retrosheet_team",
            (),
            recreate=True,
        )
        counts["raw.retrosheet_gameinfo"] = _copy_query(
            source,
            target,
            "raw.retrosheet_gameinfo",
            f"SELECT * FROM raw.retrosheet_gameinfo WHERE gid IN ({game_cte})",
            params,
            recreate=True,
        )
        counts["raw.mlb_schedule"] = _copy_query(
            source,
            target,
            "raw.mlb_schedule",
            "SELECT * FROM raw.mlb_schedule WHERE _season = ANY(%s)",
            (list(map(str, selected_seasons)),),
            recreate=True,
        )
        counts["raw.retrosheet_event"] = _copy_query(
            source,
            target,
            "raw.retrosheet_event",
            f"SELECT * FROM raw.retrosheet_event WHERE game_id IN ({game_cte})",
            params,
            recreate=True,
        )
        people = f"""
            SELECT * FROM raw.register_people WHERE key_retro IN (
                SELECT wp FROM raw.retrosheet_gameinfo WHERE gid IN ({game_cte})
                UNION SELECT lp FROM raw.retrosheet_gameinfo WHERE gid IN ({game_cte})
                UNION SELECT save FROM raw.retrosheet_gameinfo WHERE gid IN ({game_cte})
                UNION SELECT bat_id FROM raw.retrosheet_event WHERE game_id IN ({game_cte})
                UNION SELECT pit_id FROM raw.retrosheet_event WHERE game_id IN ({game_cte})
            )
        """
        counts["raw.register_people"] = _copy_query(
            source, target, "raw.register_people", people, params * 5, recreate=False
        )
        # Play/pitch rows are selected only for MLB keys that the sampled
        # Retrosheet games can actually resolve. This keeps a sample boundary
        # from masquerading as an upstream source coverage defect.
        matched = f"""
            WITH selected_games AS (
                SELECT gi.* FROM raw.retrosheet_gameinfo gi WHERE gid IN ({game_cte})
            )
            SELECT DISTINCT ms.game_id FROM raw.mlb_schedule ms
            JOIN selected_games gi ON ms.game_date::date = to_date(gi.date, 'YYYYMMDD')
            JOIN raw.retrosheet_team away ON away.team_id = gi.visteam
                AND gi._season::integer BETWEEN away.first_year::integer AND away.last_year::integer
            JOIN raw.retrosheet_team home ON home.team_id = gi.hometeam
                AND gi._season::integer BETWEEN home.first_year::integer AND home.last_year::integer
            WHERE ms.away_name = away.city || ' ' || away.nickname
              AND ms.home_name = home.city || ' ' || home.nickname
              AND COALESCE(NULLIF(ms.game_num, '')::integer, 1)
                  = COALESCE(NULLIF(gi.number, '')::integer, 1)
        """
        # A present-season slice explicitly exercises the MLB play-by-play
        # source even when Retrosheet has not yet published that season.
        # Joining to play-by-play first guarantees every selected key has an
        # MLB event payload; it does not infer a Retrosheet mapping.
        current_mlb = """
            SELECT DISTINCT ms.game_id
            FROM raw.mlb_schedule ms
            JOIN raw.mlb_playbyplay pbp ON pbp.game_pk = ms.game_id
            WHERE ms._season = %s
              AND ms.status IN ('Final', 'Completed Early', 'Forfeit')
            ORDER BY ms.game_id
            LIMIT %s
        """
        event_keys = f"({matched}) UNION ({current_mlb})"
        counts["raw.mlb_playbyplay"] = _copy_query(
            source,
            target,
            "raw.mlb_playbyplay",
            f"SELECT * FROM raw.mlb_playbyplay WHERE game_pk IN ({event_keys})",
            params + current_params,
            recreate=True,
        )
        counts["raw.statcast_pitch"] = _copy_query(
            source,
            target,
            "raw.statcast_pitch",
            f"SELECT * FROM raw.statcast_pitch WHERE game_pk IN ({event_keys})",
            params + current_params,
            recreate=True,
        )
    return SampleResult(counts)
