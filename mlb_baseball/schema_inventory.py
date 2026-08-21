"""Read-only catalogue of the database objects that support research contracts."""

from typing import Literal

from mlb_baseball.db import get_connection

Kind = Literal["table", "partitioned table", "view", "materialized view"]


def relations(*, partitions: bool = False) -> list[dict[str, str | int | None]]:
    """Return object/constraint/nullability facts for project schemas.

    Child partitions are omitted by default because their hundreds of repeated
    constraints obscure the parent-level schema someone normally needs to
    review. ``partitions=True`` provides the complete physical catalogue.
    """
    child_filter = "" if partitions else "AND parent.inhrelid IS NULL"
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute(
            f"""
            WITH relations AS (
                SELECT c.oid, n.nspname AS schema_name, c.relname,
                       CASE c.relkind
                           WHEN 'r' THEN 'table'
                           WHEN 'p' THEN 'partitioned table'
                           WHEN 'v' THEN 'view'
                           WHEN 'm' THEN 'materialized view'
                       END AS kind,
                       parent_name.relname AS partition_parent
                FROM pg_class c
                JOIN pg_namespace n ON n.oid = c.relnamespace
                LEFT JOIN pg_inherits parent ON parent.inhrelid = c.oid
                LEFT JOIN pg_class parent_name ON parent_name.oid = parent.inhparent
                WHERE n.nspname IN ('raw', 'core', 'gold', 'meta')
                  AND c.relkind IN ('r', 'p', 'v', 'm')
                  {child_filter}
            ), columns AS (
                SELECT attrelid, count(*) AS columns,
                       count(*) FILTER (WHERE NOT attnotnull) AS nullable_columns
                FROM pg_attribute
                WHERE attnum > 0 AND NOT attisdropped
                GROUP BY attrelid
            ), constraints AS (
                SELECT conrelid,
                       count(*) FILTER (WHERE contype = 'p') AS primary_keys,
                       count(*) FILTER (WHERE contype = 'u') AS unique_constraints,
                       count(*) FILTER (WHERE contype = 'f') AS foreign_keys,
                       count(*) FILTER (WHERE contype = 'c') AS check_constraints
                FROM pg_constraint GROUP BY conrelid
            ), indexes AS (
                SELECT indrelid, count(*) AS indexes
                FROM pg_index GROUP BY indrelid
            )
            SELECT r.schema_name, r.relname, r.kind, r.partition_parent,
                   coalesce(c.columns, 0) AS columns,
                   coalesce(c.nullable_columns, 0) AS nullable_columns,
                   coalesce(k.primary_keys, 0) AS primary_keys,
                   coalesce(k.unique_constraints, 0) AS unique_constraints,
                   coalesce(k.foreign_keys, 0) AS foreign_keys,
                   coalesce(k.check_constraints, 0) AS check_constraints,
                   coalesce(i.indexes, 0) AS indexes
            FROM relations r
            LEFT JOIN columns c ON c.attrelid = r.oid
            LEFT JOIN constraints k ON k.conrelid = r.oid
            LEFT JOIN indexes i ON i.indrelid = r.oid
            ORDER BY 1, 2
            """
        )
        fields = [column.name for column in cur.description or []]
        return [dict(zip(fields, row, strict=True)) for row in cur.fetchall()]


def print_report(*, partitions: bool = False) -> None:
    for relation in relations(partitions=partitions):
        parent = (
            f"; partition of {relation['partition_parent']}" if relation["partition_parent"] else ""
        )
        print(
            f"{relation['schema_name']}.{relation['relname']} ({relation['kind']}{parent}): "
            f"{relation['columns']} columns, {relation['nullable_columns']} nullable; "
            f"PK={relation['primary_keys']} unique={relation['unique_constraints']} "
            f"FK={relation['foreign_keys']} check={relation['check_constraints']} "
            f"indexes={relation['indexes']}"
        )
