"""The doctor's backup check reads the host's own nightly dump (the one that exists and is
restore-tested) instead of demanding a second `mlb backup` that nobody schedules."""

import os
import time

from mlb_baseball import backup


def _make_backup(root, stamp, *, complete=True, dump=True, age_hours=1.0, db="mlb"):
    folder = root / "daily" / stamp
    folder.mkdir(parents=True)
    if dump:
        (folder / f"pg16_{db}.dump").write_bytes(b"x" * 2048)
    if complete:
        marker = folder / ".complete"
        marker.write_text("")
        past = time.time() - age_hours * 3600
        os.utime(marker, (past, past))
    return folder


def test_recent_complete_dump_passes_and_names_the_stamp(tmp_path):
    _make_backup(tmp_path, "20261005_020001", age_hours=3)
    check = backup.host_backup_check(tmp_path, database="mlb")
    assert check.ok
    assert "20261005_020001" in check.detail


def test_old_dump_fails_with_its_age(tmp_path):
    _make_backup(tmp_path, "20261001_020001", age_hours=80)
    check = backup.host_backup_check(tmp_path, database="mlb")
    assert not check.ok
    assert "80" in check.detail or "3 days" in check.detail


def test_newest_set_without_the_complete_marker_is_not_counted(tmp_path):
    _make_backup(tmp_path, "20261004_020001", age_hours=27 + 24)
    _make_backup(tmp_path, "20261005_020001", complete=False)  # still being written
    check = backup.host_backup_check(tmp_path, database="mlb")
    assert not check.ok  # the only complete set is old


def test_set_missing_this_databases_dump_fails(tmp_path):
    _make_backup(tmp_path, "20261005_020001", dump=False)
    check = backup.host_backup_check(tmp_path, database="mlb")
    assert not check.ok
    assert "pg16_mlb.dump" in check.detail


def test_empty_root_fails_with_the_path(tmp_path):
    check = backup.host_backup_check(tmp_path, database="mlb")
    assert not check.ok
    assert str(tmp_path) in check.detail
