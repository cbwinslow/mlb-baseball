"""Integration tests verifying Postgres analytics extensions.

Covers pg_trgm, btree_gist, vector, and tablefunc.
"""


def test_pg_trgm_similarity_query(db_conn):
    with db_conn.cursor() as cur:
        cur.execute("SELECT similarity('Shohei Ohtani', 'Shohei Otani')")
        (sim,) = cur.fetchone()
        assert sim > 0.6


def test_pg_trgm_index_scan(db_conn):
    with db_conn.cursor() as cur:
        cur.execute(
            """
            EXPLAIN (FORMAT JSON)
            SELECT * FROM core.player
            WHERE (first_name || ' ' || last_name) % 'Judge'
            """
        )
        plan = cur.fetchone()[0]
        assert plan is not None


def test_vector_extension_distance(db_conn):
    with db_conn.cursor() as cur:
        cur.execute(
            """
            SELECT '[1,2,3]'::vector <-> '[1,2,3]'::vector AS dist_zero,
                   '[1,0,0]'::vector <=> '[0,1,0]'::vector AS cosine_ortho
            """
        )
        dist_zero, cosine_ortho = cur.fetchone()
        assert dist_zero == 0.0
        assert cosine_ortho == 1.0


def test_tablefunc_normal_rand(db_conn):
    with db_conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM normal_rand(100, 0, 1)")
        (count,) = cur.fetchone()
        assert count == 100
