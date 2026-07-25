from mlb_baseball.db import get_connection


def test_get_connection_returns_a_working_connection():
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT 1")
            assert cur.fetchone() == (1,)
