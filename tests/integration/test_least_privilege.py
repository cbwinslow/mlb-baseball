"""Integration test for Plan 01E least-privilege database role isolation.

Validates that a serving role granted USAGE on a disposable serve schema
and SELECT on a serve table/view can perform reads on serve objects, but
is explicitly denied access to raw, core, gold, and meta schemas, schema
creation, and write operations.
"""

import os
import uuid

import psycopg
import pytest
from psycopg import sql

TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL", "postgresql:///mlb_test")


def _assert_is_test_db(url: str) -> None:
    """Safety check to ensure test execution never targets a production database."""
    params = psycopg.conninfo.conninfo_to_dict(url)
    dbname = str(params.get("dbname") or "")
    assert "test" in dbname.lower() or "codex" in dbname.lower(), (
        f"Refusing to execute least-privilege test against non-test database: {dbname}"
    )


@pytest.fixture
def disposable_least_privilege_env():
    """Creates a disposable serve schema, serving object, and NOLOGIN role,

    configures least-privilege permissions, and yields context info.
    Guarantees clean teardown of all roles and schema objects.
    """
    _assert_is_test_db(TEST_DATABASE_URL)

    uid = uuid.uuid4().hex[:8]
    serve_role = f"test_role_serve_{uid}"
    serve_schema = f"test_serve_schema_{uid}"
    serve_table_name = "test_serve_table"
    serve_view_name = "test_serve_view"

    with psycopg.connect(TEST_DATABASE_URL, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT rolsuper OR rolcreaterole FROM pg_roles WHERE rolname = current_user"
            )
            if not cur.fetchone()[0]:
                pytest.skip(
                    "least-privilege isolation fixture requires a test-only CREATEROLE account; "
                    "the normal mlb_test application account correctly lacks it"
                )
            # Create disposable NOLOGIN serving role
            cur.execute(sql.SQL("CREATE ROLE {} NOLOGIN;").format(sql.Identifier(serve_role)))
            # Grant role to current session user so SET ROLE can be executed
            cur.execute(sql.SQL("GRANT {} TO CURRENT_USER;").format(sql.Identifier(serve_role)))

            # Create disposable serve schema and table/view
            cur.execute(sql.SQL("CREATE SCHEMA {};").format(sql.Identifier(serve_schema)))
            cur.execute(
                sql.SQL("CREATE TABLE {} (id INT PRIMARY KEY, name TEXT);").format(
                    sql.Identifier(serve_schema, serve_table_name)
                )
            )
            cur.execute(
                sql.SQL("INSERT INTO {} (id, name) VALUES (1, 'allowed_serve_record');").format(
                    sql.Identifier(serve_schema, serve_table_name)
                )
            )
            cur.execute(
                sql.SQL("CREATE VIEW {} AS SELECT id, name FROM {};").format(
                    sql.Identifier(serve_schema, serve_view_name),
                    sql.Identifier(serve_schema, serve_table_name),
                )
            )

            # Revoke PUBLIC access on disposable serve schema and objects
            cur.execute(
                sql.SQL("REVOKE ALL ON SCHEMA {} FROM PUBLIC;").format(sql.Identifier(serve_schema))
            )
            cur.execute(
                sql.SQL("REVOKE ALL ON ALL TABLES IN SCHEMA {} FROM PUBLIC;").format(
                    sql.Identifier(serve_schema)
                )
            )

            # Grant serving role only USAGE on schema and SELECT on serve objects
            cur.execute(
                sql.SQL("GRANT USAGE ON SCHEMA {} TO {};").format(
                    sql.Identifier(serve_schema), sql.Identifier(serve_role)
                )
            )
            cur.execute(
                sql.SQL("GRANT SELECT ON ALL TABLES IN SCHEMA {} TO {};").format(
                    sql.Identifier(serve_schema), sql.Identifier(serve_role)
                )
            )

    try:
        yield {
            "serve_role": serve_role,
            "serve_schema": serve_schema,
            "serve_table_name": serve_table_name,
            "serve_view_name": serve_view_name,
        }
    finally:
        with psycopg.connect(TEST_DATABASE_URL, autocommit=True) as conn:
            with conn.cursor() as cur:
                cur.execute("RESET ROLE;")
                cur.execute(
                    sql.SQL("DROP SCHEMA IF EXISTS {} CASCADE;").format(
                        sql.Identifier(serve_schema)
                    )
                )
                cur.execute(sql.SQL("DROP ROLE IF EXISTS {};").format(sql.Identifier(serve_role)))


def test_least_privilege_bounded_isolation(disposable_least_privilege_env):
    """Proves that a serving role can SELECT from serve objects, but is denied

    operations on raw/core/gold/meta schemas, schema creation, and write actions.
    """
    env = disposable_least_privilege_env
    serve_role = env["serve_role"]
    serve_schema = env["serve_schema"]
    serve_table_name = env["serve_table_name"]
    serve_view_name = env["serve_view_name"]

    with psycopg.connect(TEST_DATABASE_URL, autocommit=True) as conn:
        with conn.cursor() as cur:
            # Switch to disposable serving role
            cur.execute(sql.SQL("SET ROLE {};").format(sql.Identifier(serve_role)))

            # 1. ALLOWED: SELECT on serve table and serve view
            cur.execute(
                sql.SQL("SELECT id, name FROM {};").format(
                    sql.Identifier(serve_schema, serve_table_name)
                )
            )
            rows = cur.fetchall()
            assert len(rows) == 1
            assert rows[0] == (1, "allowed_serve_record")

            cur.execute(
                sql.SQL("SELECT id, name FROM {};").format(
                    sql.Identifier(serve_schema, serve_view_name)
                )
            )
            view_rows = cur.fetchall()
            assert len(view_rows) == 1
            assert view_rows[0] == (1, "allowed_serve_record")

            # 2. DENIED: raw, core, gold, meta operations (SELECT and DDL)
            for target_schema in ["raw", "core", "gold", "meta"]:
                # Denied DDL in restricted schema
                with pytest.raises(psycopg.errors.InsufficientPrivilege):
                    cur.execute(
                        sql.SQL("CREATE TABLE {} (id INT);").format(
                            sql.Identifier(target_schema, "test_denied_table")
                        )
                    )

                # Find any existing table in target_schema to test SELECT denial
                cur.execute(
                    "SELECT table_name FROM information_schema.tables "
                    "WHERE table_schema = %s LIMIT 1;",
                    (target_schema,),
                )
                existing_table = cur.fetchone()
                if existing_table:
                    with pytest.raises(psycopg.errors.InsufficientPrivilege):
                        cur.execute(
                            sql.SQL("SELECT 1 FROM {} LIMIT 1;").format(
                                sql.Identifier(target_schema, existing_table[0])
                            )
                        )

            # 3. DENIED: schema creation
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                cur.execute("CREATE SCHEMA test_unauthorized_schema;")

            # 4. DENIED: write operations on serve object
            # (INSERT, UPDATE, DELETE, DROP, CREATE TABLE in schema)
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                cur.execute(
                    sql.SQL("INSERT INTO {} (id, name) VALUES (2, 'denied');").format(
                        sql.Identifier(serve_schema, serve_table_name)
                    )
                )

            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                cur.execute(
                    sql.SQL("UPDATE {} SET name = 'tampered';").format(
                        sql.Identifier(serve_schema, serve_table_name)
                    )
                )

            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                cur.execute(
                    sql.SQL("DELETE FROM {};").format(
                        sql.Identifier(serve_schema, serve_table_name)
                    )
                )

            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                cur.execute(
                    sql.SQL("DROP TABLE {};").format(sql.Identifier(serve_schema, serve_table_name))
                )

            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                cur.execute(
                    sql.SQL("CREATE TABLE {} (id INT);").format(
                        sql.Identifier(serve_schema, "test_new_table")
                    )
                )

            # Reset role back to session user
            cur.execute("RESET ROLE;")
