"""Persistent game-instance provenance for rebuilt feature rows."""

import psycopg

from mlb_baseball.db import fetch_one


def backfill_game_instance_keys(
    conn: psycopg.Connection, batch_size: int = 1_000
) -> dict[str, int]:
    """Backfill at most one deterministic batch per relation and commit it.

    Repeating the command until both ``remaining`` counts are zero is safe:
    only NULL keys are touched and ambiguous prediction lookup IDs receive a
    durable, explicit legacy key rather than a guessed match.
    """
    if batch_size < 1:
        raise ValueError("batch_size must be positive")
    with conn.cursor() as cur:
        cur.execute(
            """
            WITH batch AS (
                SELECT f.id FROM gold.game_feature f
                WHERE f.game_instance_key IS NULL ORDER BY f.id LIMIT %s
            )
            UPDATE gold.game_feature f SET game_instance_key = COALESCE(
                'mlb:' || f.mlb_game_pk,
                (SELECT 'retro:' || g.retro_game_id FROM core.game g WHERE g.id = f.game_id),
                'legacy-feature:' || f.id::text
            ) FROM batch WHERE f.id = batch.id
            """,
            (batch_size,),
        )
        features = cur.rowcount
    conn.commit()
    with conn.cursor() as cur:
        cur.execute(
            """
            WITH batch AS (
                SELECT p.ctid FROM gold.prediction p
                WHERE p.game_instance_key IS NULL ORDER BY p.generated_at, p.mlb_game_pk LIMIT %s
            )
            UPDATE gold.prediction p SET game_instance_key = 'mlb:' || p.mlb_game_pk
            FROM batch WHERE p.ctid = batch.ctid
            """,
            (batch_size,),
        )
        predictions = cur.rowcount
    conn.commit()
    sync_feature_instances(conn)
    conn.commit()
    with conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM gold.game_feature WHERE game_instance_key IS NULL")
        feature_remaining = fetch_one(cur)[0]
        cur.execute("SELECT count(*) FROM gold.prediction WHERE game_instance_key IS NULL")
        prediction_remaining = fetch_one(cur)[0]
    return {
        "features": features,
        "predictions": predictions,
        "feature_remaining": feature_remaining,
        "prediction_remaining": prediction_remaining,
    }


def sync_feature_instances(conn: psycopg.Connection) -> int:
    """Upsert the current feature population into ``meta.game_instance``.

    The registry is append/preserve oriented: a later feature rebuild may
    change its transient row id, but it must never erase a key referenced by a
    historical prediction.  A legacy key stays explicitly legacy rather than
    being silently reassigned to a plausible-looking MLB identity.
    """
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO meta.game_instance (
                game_instance_key, identity_kind, season, game_date, game_number,
                mlb_game_pk, retro_game_id, core_game_id
            )
            SELECT
                f.game_instance_key,
                CASE
                    WHEN f.game_instance_key LIKE 'mlb:%%' THEN 'mlb_game'
                    WHEN f.game_instance_key LIKE 'retro:%%' THEN 'retrosheet'
                    ELSE 'legacy'
                END,
                f.season,
                f.game_date,
                g.game_number,
                f.mlb_game_pk,
                g.retro_game_id,
                f.game_id
            FROM gold.game_feature f
            LEFT JOIN core.game g ON g.id = f.game_id
            ON CONFLICT (game_instance_key) DO UPDATE SET
                core_game_id = CASE
                    WHEN meta.game_instance.core_game_id IS NOT NULL
                        THEN meta.game_instance.core_game_id
                    WHEN NOT EXISTS (
                        SELECT 1 FROM meta.game_instance existing
                        WHERE existing.core_game_id = EXCLUDED.core_game_id
                          AND existing.game_instance_key <> EXCLUDED.game_instance_key
                    ) THEN EXCLUDED.core_game_id
                END,
                retro_game_id = COALESCE(EXCLUDED.retro_game_id, meta.game_instance.retro_game_id),
                last_seen_at = now()
            """
        )
        return cur.rowcount
