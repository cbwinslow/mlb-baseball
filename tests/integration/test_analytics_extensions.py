"""Migration 0099 makes pg_trgm, unaccent, btree_gist and tablefunc
available. These tests exercise each one's functionality against the real
migrated test database -- migration 0099 only runs CREATE EXTENSION, so a
functional check is the meaningful assertion, not `SELECT ... FROM
pg_extension` (which test_doctor covers)."""


def test_pg_trgm_similarity(db_conn):
    with db_conn.cursor() as cur:
        cur.execute("SELECT similarity(%s, %s)", ("Shohei Ohtani", "Shohei Otani"))
        (sim,) = cur.fetchone()
    assert sim > 0.6


def test_pg_trgm_functions_resolve(db_conn):
    # show_trgm + the % operator (with an explicit threshold so the assert
    # doesn't depend on the session default) both come from pg_trgm.
    with db_conn.cursor() as cur:
        cur.execute("SELECT show_trgm('judge')")
        (trigrams,) = cur.fetchone()
        assert "  j" in trigrams
        cur.execute("SET pg_trgm.similarity_threshold = 0.2")
        cur.execute("SELECT %s %% %s", ("Aaron Judge", "Aron Judge"))
        (matched,) = cur.fetchone()
    assert matched is True


def test_unaccent_strips_diacritics(db_conn):
    with db_conn.cursor() as cur:
        cur.execute("SELECT unaccent(%s)", ("José Abreu",))
        (plain,) = cur.fetchone()
    assert plain == "Jose Abreu"


def test_tablefunc_normal_rand(db_conn):
    with db_conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM normal_rand(100, 0, 1)")
        (count,) = cur.fetchone()
    assert count == 100


def test_btree_gist_supports_scalar_exclusion(db_conn):
    # btree_gist lets a plain scalar (int) sit in a GiST exclusion constraint
    # alongside a range -- the reason it's enabled. Build a throwaway table
    # to prove the operator class exists.
    with db_conn.cursor() as cur:
        cur.execute(
            """
            CREATE TEMP TABLE _bg_probe (
                grp integer,
                span int4range,
                EXCLUDE USING gist (grp WITH =, span WITH &&)
            )
            """
        )
        cur.execute("INSERT INTO _bg_probe VALUES (1, '[1,5)')")
        cur.execute("INSERT INTO _bg_probe VALUES (1, '[10,15)')")  # ok, disjoint
    db_conn.rollback()
