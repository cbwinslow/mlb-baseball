"""The one-time issue #107 repair (scripts/repair_market_prediction_times.sql)
must delete exactly the post-first-pitch market rows and nothing else."""

from datetime import UTC, datetime
from pathlib import Path

_REPAIR_SQL = Path(__file__).resolve().parents[2] / "scripts" / "repair_market_prediction_times.sql"

# The DELETE block from the script, verbatim. Kept here so this test exercises
# the real statement and fails loudly if the script's DELETE is edited.
_DELETE_BLOCK = """WITH schedule AS (
    SELECT game_id,
           min(NULLIF(game_datetime, '')::timestamptz) AS game_start
    FROM raw.mlb_schedule
    WHERE game_id IS NOT NULL AND NULLIF(game_datetime, '') IS NOT NULL
    GROUP BY game_id
    HAVING count(DISTINCT NULLIF(game_datetime, '')) = 1
)
DELETE FROM gold.prediction p
USING schedule s
WHERE s.game_id = p.mlb_game_pk
  AND p.model_version IN ('kalshi-v1', 'polymarket-v1')
  AND p.generated_at >= s.game_start;"""


def test_script_file_contains_the_delete_block_verbatim():
    assert _DELETE_BLOCK in _REPAIR_SQL.read_text()


# Set by _seed when it had to CREATE raw.mlb_schedule; _cleanup then DROPs it so
# no other test ever sees a skinny two-column raw.mlb_schedule. If the table
# already existed (the normal full-suite case — an earlier test made it), _seed
# leaves it alone and only touches its own rows.
_seed_made_schedule = False


def _seed(db_conn):
    global _seed_made_schedule
    db_conn.rollback()
    with db_conn.cursor() as cur:
        cur.execute("SELECT to_regclass('raw.mlb_schedule')")
        if cur.fetchone()[0] is None:
            cur.execute("CREATE TABLE raw.mlb_schedule (game_id text, game_datetime text)")
            _seed_made_schedule = True
        cur.execute(
            "DELETE FROM raw.mlb_schedule WHERE game_id IN ('700001', '700002', '700003', '700004')"
        )
        cur.execute(
            "INSERT INTO raw.mlb_schedule (game_id, game_datetime) VALUES "
            "('700001', '2026-05-01T23:00:00Z'), ('700002', '2026-05-02T23:00:00Z'), "
            # 700003: doubleheader — two rows, different game_datetime. The
            # HAVING count(DISTINCT ...) = 1 guard drops it from the CTE.
            "('700003', '2026-05-03T17:00:00Z'), ('700003', '2026-05-03T23:00:00Z')"
            # 700004: deliberately no raw.mlb_schedule row at all.
        )
        cur.execute(
            "DELETE FROM gold.prediction "
            "WHERE mlb_game_pk IN ('700001', '700002', '700003', '700004')"
        )
        cur.executemany(
            "INSERT INTO gold.prediction "
            "(mlb_game_pk, game_instance_key, model_version, home_win_prob, generated_at) "
            "VALUES (%s, %s, %s, 0.5, %s)",
            [
                # stale: generated after first pitch — must be deleted
                ("700001", "mlb:700001", "kalshi-v1", datetime(2026, 5, 2, 6, 0, tzinfo=UTC)),
                ("700001", "mlb:700001", "polymarket-v1", datetime(2026, 5, 2, 6, 0, tzinfo=UTC)),
                # good: generated before first pitch — must be kept
                ("700002", "mlb:700002", "kalshi-v1", datetime(2026, 5, 2, 12, 0, tzinfo=UTC)),
                # not a market model — must be kept
                ("700001", "mlb:700001", "elo-v1", datetime(2026, 5, 2, 6, 0, tzinfo=UTC)),
                # doubleheader: after both first pitches, but the game is
                # dropped from the CTE by the HAVING guard — must be kept
                ("700003", "mlb:700003", "kalshi-v1", datetime(2026, 5, 4, 6, 0, tzinfo=UTC)),
                # no schedule row at all: inner USING join never matches — must be kept
                ("700004", "mlb:700004", "polymarket-v1", datetime(2026, 5, 4, 6, 0, tzinfo=UTC)),
            ],
        )
    db_conn.commit()


def _cleanup(db_conn):
    global _seed_made_schedule
    db_conn.rollback()
    with db_conn.cursor() as cur:
        cur.execute(
            "DELETE FROM gold.prediction "
            "WHERE mlb_game_pk IN ('700001', '700002', '700003', '700004')"
        )
        if _seed_made_schedule:
            # This test created the table — remove it entirely rather than
            # leave a skinny raw.mlb_schedule for a later features.build() test.
            cur.execute("DROP TABLE IF EXISTS raw.mlb_schedule")
            _seed_made_schedule = False
        else:
            cur.execute(
                "DELETE FROM raw.mlb_schedule "
                "WHERE game_id IN ('700001', '700002', '700003', '700004')"
            )
    db_conn.commit()


def test_repair_deletes_only_post_first_pitch_market_rows(db_conn):
    _seed(db_conn)
    try:
        with db_conn.cursor() as cur:
            cur.execute(_DELETE_BLOCK)
        db_conn.commit()

        with db_conn.cursor() as cur:
            cur.execute(
                "SELECT mlb_game_pk, model_version FROM gold.prediction "
                "WHERE mlb_game_pk IN ('700001', '700002', '700003', '700004') "
                "ORDER BY mlb_game_pk, model_version"
            )
            remaining = cur.fetchall()
        assert remaining == [
            ("700001", "elo-v1"),
            ("700002", "kalshi-v1"),
            # doubleheader — dropped from the CTE by the HAVING guard
            ("700003", "kalshi-v1"),
            # no schedule row — inner USING join never matches
            ("700004", "polymarket-v1"),
        ]
    finally:
        _cleanup(db_conn)
