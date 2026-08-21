"""Pure filesystem-logic tests for backup.rotate_backups() -- no DB, no
network; timestamped fixture files stand in for real pg_dump output."""

import pytest

from mlb_baseball import backup

DATABASE_URL = "postgresql:///mlb_test"
DB = backup.dbname(DATABASE_URL)


def _full(tmp_path, ts):
    path = tmp_path / f"{DB}_{ts}.sql"
    path.write_text("-- fake dump")
    return path


def _schema_only(tmp_path, ts):
    path = tmp_path / f"{DB}_schema_{ts}.sql"
    path.write_text("-- fake schema dump")
    return path


def test_rotate_backups_keeps_newest_n_deletes_older(tmp_path):
    timestamps = [
        "20260101T000000Z",
        "20260102T000000Z",
        "20260103T000000Z",
        "20260104T000000Z",
        "20260105T000000Z",
    ]
    files = [_full(tmp_path, ts) for ts in timestamps]

    deleted = backup.rotate_backups(DATABASE_URL, tmp_path, keep=3)

    assert set(deleted) == {files[0], files[1]}
    assert not files[0].exists()
    assert not files[1].exists()
    for survivor in files[2:]:
        assert survivor.exists()


def test_rotate_backups_keeps_everything_when_under_the_limit(tmp_path):
    files = [_full(tmp_path, "20260101T000000Z"), _full(tmp_path, "20260102T000000Z")]

    deleted = backup.rotate_backups(DATABASE_URL, tmp_path, keep=5)

    assert deleted == []
    for f in files:
        assert f.exists()


def test_rotate_backups_never_touches_schema_only_dumps(tmp_path):
    # A schema-only backup could otherwise look like the oldest full backup
    # and get swept up in rotation -- it must never be a candidate at all.
    schema_file = _schema_only(tmp_path, "20260101T000000Z")
    full_files = [_full(tmp_path, ts) for ts in ["20260102T000000Z", "20260103T000000Z"]]

    deleted = backup.rotate_backups(DATABASE_URL, tmp_path, keep=1)

    assert schema_file not in deleted
    assert schema_file.exists()
    assert full_files[0] in deleted


def test_rotate_backups_never_touches_files_it_did_not_create(tmp_path):
    # The one small schema snapshot tracked in git predates this naming
    # convention entirely (no timestamp suffix) -- must never match.
    tracked = tmp_path / f"{DB}_schema_20260807.sql"
    tracked.write_text("-- tracked snapshot")
    _full(tmp_path, "20260101T000000Z")
    _full(tmp_path, "20260102T000000Z")

    deleted = backup.rotate_backups(DATABASE_URL, tmp_path, keep=1)

    assert tracked not in deleted
    assert tracked.exists()


def test_rotate_backups_rejects_keep_less_than_one(tmp_path):
    _full(tmp_path, "20260101T000000Z")
    with pytest.raises(ValueError, match="keep"):
        backup.rotate_backups(DATABASE_URL, tmp_path, keep=0)
