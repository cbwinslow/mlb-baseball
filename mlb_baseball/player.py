"""Player-ID crosswalk lookup.

core.player already holds every ID system for a player on one row (retro_id,
mlbam_id, bbref_id, fangraphs_id, chadwick_uuid) -- built from the Chadwick
Bureau Register during conform (see mlb_baseball/conform.py's
_build_players, migrations/0005_core_player_team_game.sql). This module adds
no new data or table; it wraps that existing single-row crosswalk so a
caller can supply any one ID and get every other ID back, without needing to
know which column holds which ID system or writing raw SQL by hand.

retro_id is NOT NULL/UNIQUE on core.player (every conformed player has one);
the other four columns are nullable -- a player who was only matched from
one source (e.g. Retrosheet-only, no confirmed MLBAM match yet) legitimately
has NULL in the columns that source doesn't supply. crosswalk() returns that
row's real NULLs as-is, not a "not found" signal -- "not found" is a bare
None return for the whole lookup, when no row matches at all.
"""

import psycopg
from psycopg import sql

from mlb_baseball.db import get_connection

# Public ID-system names -> the core.player column that holds them.
ID_COLUMNS = {
    "retro": "retro_id",
    "mlbam": "mlbam_id",
    "bbref": "bbref_id",
    "fangraphs": "fangraphs_id",
    "chadwick": "chadwick_uuid",
}


def crosswalk(conn: psycopg.Connection, id_type: str, id_value: str) -> dict[str, str] | None:
    """Look up a player by any one known ID system; return every ID system's
    value for that player (plus first/last name), or None if no player has
    that (id_type, id_value).

    Raises ValueError if id_type isn't one of ID_COLUMNS' keys.
    """
    if id_type not in ID_COLUMNS:
        raise ValueError(f"unknown id_type {id_type!r}; expected one of {sorted(ID_COLUMNS)}")
    column = ID_COLUMNS[id_type]
    with conn.cursor() as cur:
        cur.execute(
            sql.SQL(
                "SELECT retro_id, mlbam_id, bbref_id, fangraphs_id, chadwick_uuid, "
                "first_name, last_name FROM core.player WHERE {} = %s"
            ).format(sql.Identifier(column)),
            (id_value,),
        )
        row = cur.fetchone()
    if row is None:
        return None
    retro_id, mlbam_id, bbref_id, fangraphs_id, chadwick_uuid, first_name, last_name = row
    return {
        "retro": retro_id,
        "mlbam": mlbam_id,
        "bbref": bbref_id,
        "fangraphs": fangraphs_id,
        "chadwick": chadwick_uuid,
        "first_name": first_name,
        "last_name": last_name,
    }


def print_crosswalk(id_type: str, id_value: str) -> None:
    """`mlb player-id` CLI entry point: look up and print, or report not found."""
    with get_connection() as conn:
        result = crosswalk(conn, id_type, id_value)
    if result is None:
        print(f"No player found with {id_type}={id_value!r}")
        return
    name = f"{result['first_name'] or ''} {result['last_name'] or ''}".strip()
    print(name or "(name unknown)")
    for system in ID_COLUMNS:
        print(f"  {system}: {result[system] or '(none)'}")
