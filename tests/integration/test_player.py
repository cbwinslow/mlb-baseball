"""Regression coverage for mlb_baseball.player -- the player-ID crosswalk
lookup. core.player already holds every known ID system for a player on one
row (built from the Chadwick Register during conform); this just wraps that
lookup so callers don't need to know the column names or write SQL by hand.
"""

import pytest

from mlb_baseball import player


def _reset(db_conn):
    db_conn.rollback()
    with db_conn.cursor() as cur:
        cur.execute("DELETE FROM core.player")
    db_conn.commit()


def _insert_degrom(db_conn):
    with db_conn.cursor() as cur:
        cur.execute(
            "INSERT INTO core.player "
            "(retro_id, mlbam_id, bbref_id, fangraphs_id, chadwick_uuid, "
            "first_name, last_name) VALUES "
            "('degrj001', '594798', 'degroja01', '10954', "
            "'aardo-degrom-uuid', 'Jacob', 'deGrom')"
        )
    db_conn.commit()


def test_crosswalk_resolves_every_id_system_from_any_one_of_them(db_conn):
    _reset(db_conn)
    _insert_degrom(db_conn)

    expected = {
        "retro": "degrj001",
        "mlbam": "594798",
        "bbref": "degroja01",
        "fangraphs": "10954",
        "chadwick": "aardo-degrom-uuid",
        "first_name": "Jacob",
        "last_name": "deGrom",
    }

    # Look the same player up starting from every single ID system in turn --
    # each one must resolve to the exact same full set of IDs.
    for id_type in ("retro", "mlbam", "bbref", "fangraphs", "chadwick"):
        result = player.crosswalk(db_conn, id_type, expected[id_type])
        assert result == expected, f"lookup by {id_type} did not resolve correctly"

    _reset(db_conn)


def test_crosswalk_returns_none_for_unknown_id_value(db_conn):
    _reset(db_conn)
    _insert_degrom(db_conn)

    assert player.crosswalk(db_conn, "mlbam", "000000-does-not-exist") is None

    _reset(db_conn)


def test_crosswalk_returns_none_for_null_id_column(db_conn):
    # A player conformed only from Retrosheet with no matched MLBAM ID yet --
    # mlbam_id is NULL on their own row, not a separate "not found" case.
    _reset(db_conn)
    with db_conn.cursor() as cur:
        cur.execute(
            "INSERT INTO core.player (retro_id, first_name, last_name) "
            "VALUES ('oldpp101', 'Old', 'Playpen')"
        )
    db_conn.commit()

    assert player.crosswalk(db_conn, "mlbam", "anything") is None
    result = player.crosswalk(db_conn, "retro", "oldpp101")
    assert result["mlbam"] is None
    assert result["retro"] == "oldpp101"

    _reset(db_conn)


def test_crosswalk_rejects_unknown_id_type(db_conn):
    with pytest.raises(ValueError, match="unknown id_type"):
        player.crosswalk(db_conn, "not_a_real_id_system", "594798")
