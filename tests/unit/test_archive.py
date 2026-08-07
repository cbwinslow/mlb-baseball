import stat
import zipfile

import pytest

from mlb_baseball import archive


def _write_zip(path, members: dict[str, bytes]) -> None:
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for name, content in members.items():
            zf.writestr(name, content)


def test_extract_zip_extracts_regular_members_inside_destination(tmp_path):
    source = tmp_path / "source.zip"
    destination = tmp_path / "extract"
    _write_zip(source, {"2025/TEAM2025": b"team", "2025/ABC2025.ROS": b"roster"})

    archive.extract_zip(source, destination)

    assert (destination / "2025" / "TEAM2025").read_bytes() == b"team"
    assert (destination / "2025" / "ABC2025.ROS").read_bytes() == b"roster"


@pytest.mark.parametrize("member", ["../outside", "/absolute", "nested\\windows-path"])
def test_extract_zip_rejects_unsafe_member_paths(tmp_path, member):
    source = tmp_path / "unsafe.zip"
    destination = tmp_path / "extract"
    _write_zip(source, {member: b"bad"})

    with pytest.raises(archive.UnsafeArchiveError, match="unsafe archive member path"):
        archive.extract_zip(source, destination)

    assert not destination.exists() or not list(destination.rglob("*"))


def test_extract_zip_rejects_symbolic_link_member(tmp_path):
    source = tmp_path / "link.zip"
    destination = tmp_path / "extract"
    link = zipfile.ZipInfo("link")
    link.external_attr = (stat.S_IFLNK | 0o777) << 16
    with zipfile.ZipFile(source, "w") as zf:
        zf.writestr(link, "outside")

    with pytest.raises(archive.UnsafeArchiveError, match="unsafe file type"):
        archive.extract_zip(source, destination)


def test_extract_zip_enforces_compression_ratio_limit(tmp_path, monkeypatch):
    source = tmp_path / "compressed.zip"
    _write_zip(source, {"large.txt": b"a" * 4096})
    monkeypatch.setattr(archive, "MAX_COMPRESSION_RATIO", 1)

    with pytest.raises(archive.UnsafeArchiveError, match="compression ratio"):
        archive.extract_zip(source, tmp_path / "extract")


def test_read_zip_member_rejects_symbolic_link(tmp_path):
    source = tmp_path / "link.zip"
    link = zipfile.ZipInfo("roster.ROS")
    link.external_attr = (stat.S_IFLNK | 0o777) << 16
    with zipfile.ZipFile(source, "w") as zf:
        zf.writestr(link, "outside")

    with (
        zipfile.ZipFile(source) as zf,
        pytest.raises(archive.UnsafeArchiveError, match="unsafe file type"),
    ):
        archive.read_zip_member(zf, zf.infolist()[0])
