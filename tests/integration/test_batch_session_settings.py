"""`apply_batch_session_settings` is what makes `mlb conform` / `mlb predict`
run with the memory + durability profile a heavy run-alone rebuild needs
(spec 2026-08-28, Phase 1.2). It must use session-level `SET` (not `SET
LOCAL`) so the settings survive the intermediate commits those jobs do.

work_mem / maintenance_work_mem are configurable (issue #202): the default
must stay conservative (safe on a modest machine), and this project's own
production tuning (1GB / 4GB) must remain an explicit opt-in rather than the
default. See `mlb_baseball.db._batch_session_settings`.
"""

from __future__ import annotations

from mlb_baseball.db import _batch_session_settings, apply_batch_session_settings


def _show(conn, name: str) -> str:
    with conn.cursor() as cur:
        cur.execute(f"SHOW {name}")
        return cur.fetchone()[0]


def test_applies_every_declared_setting(db_conn, monkeypatch):
    monkeypatch.delenv("MLB_BATCH_WORK_MEM", raising=False)
    monkeypatch.delenv("MLB_BATCH_MAINTENANCE_WORK_MEM", raising=False)
    settings = _batch_session_settings()

    apply_batch_session_settings(db_conn)

    assert _show(db_conn, "synchronous_commit") == "off"
    # work_mem/maintenance_work_mem normalise in SHOW output (e.g. "4MB").
    assert _show(db_conn, "work_mem") == settings["work_mem"]
    assert _show(db_conn, "maintenance_work_mem") == settings["maintenance_work_mem"]


def test_settings_survive_a_commit(db_conn, monkeypatch):
    monkeypatch.delenv("MLB_BATCH_WORK_MEM", raising=False)
    monkeypatch.delenv("MLB_BATCH_MAINTENANCE_WORK_MEM", raising=False)
    settings = _batch_session_settings()

    # If this were `SET LOCAL`, the commit would reset it — and the real
    # jobs commit between stages, so every stage after the first would lose
    # the tuning.
    apply_batch_session_settings(db_conn)
    with db_conn.cursor() as cur:
        cur.execute("SELECT 1")
    db_conn.commit()

    assert _show(db_conn, "work_mem") == settings["work_mem"]
    assert _show(db_conn, "synchronous_commit") == "off"


def test_default_batch_memory_settings_are_conservative(monkeypatch):
    # The bug (issue #202): this used to hardcode 1GB/4GB, tuned for this
    # project's own 40-core/125GB production host, which is a real OOM risk
    # on the modest machines this code also ships to. Un-configured, the
    # default must match PostgreSQL's own conservative out-of-the-box
    # values, not this project's production tuning.
    monkeypatch.delenv("MLB_BATCH_WORK_MEM", raising=False)
    monkeypatch.delenv("MLB_BATCH_MAINTENANCE_WORK_MEM", raising=False)
    monkeypatch.delenv("MLB_CONFIG", raising=False)

    settings = _batch_session_settings()

    assert settings["work_mem"] == "4MB"
    assert settings["maintenance_work_mem"] == "64MB"


def test_batch_memory_settings_are_overridable_via_env_var(db_conn, monkeypatch):
    # This is how this project's own production host keeps its PR #86
    # tuning: set explicitly, not defaulted.
    monkeypatch.setenv("MLB_BATCH_WORK_MEM", "1GB")
    monkeypatch.setenv("MLB_BATCH_MAINTENANCE_WORK_MEM", "4GB")

    apply_batch_session_settings(db_conn)

    assert _show(db_conn, "work_mem") == "1GB"
    assert _show(db_conn, "maintenance_work_mem") == "4GB"
