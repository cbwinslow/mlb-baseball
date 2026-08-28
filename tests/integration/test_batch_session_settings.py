"""`apply_batch_session_settings` is what makes `mlb conform` / `mlb predict`
run with the memory + durability profile a heavy run-alone rebuild needs
(spec 2026-08-28, Phase 1.2). It must use session-level `SET` (not `SET
LOCAL`) so the settings survive the intermediate commits those jobs do.
"""

from __future__ import annotations

from mlb_baseball.db import _BATCH_SESSION_SETTINGS, apply_batch_session_settings


def _show(conn, name: str) -> str:
    with conn.cursor() as cur:
        cur.execute(f"SHOW {name}")
        return cur.fetchone()[0]


def test_applies_every_declared_setting(db_conn):
    apply_batch_session_settings(db_conn)

    assert _show(db_conn, "synchronous_commit") == "off"
    # work_mem/maintenance_work_mem normalise to "1GB"/"4GB" in SHOW output.
    assert _show(db_conn, "work_mem") == _BATCH_SESSION_SETTINGS["work_mem"]
    assert _show(db_conn, "maintenance_work_mem") == _BATCH_SESSION_SETTINGS["maintenance_work_mem"]


def test_settings_survive_a_commit(db_conn):
    # If this were `SET LOCAL`, the commit would reset it — and the real
    # jobs commit between stages, so every stage after the first would lose
    # the tuning.
    apply_batch_session_settings(db_conn)
    with db_conn.cursor() as cur:
        cur.execute("SELECT 1")
    db_conn.commit()

    assert _show(db_conn, "work_mem") == _BATCH_SESSION_SETTINGS["work_mem"]
    assert _show(db_conn, "synchronous_commit") == "off"
