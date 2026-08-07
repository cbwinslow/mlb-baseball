"""Safe, bounded extraction for untrusted ZIP downloads.

Connectors retain downloaded archives for resumability, but unpack only into
temporary working directories.  This module validates every member before any
write so a remote archive cannot escape that directory or consume unbounded
disk while being parsed.
"""

import stat
import zipfile
from pathlib import Path, PurePosixPath

MAX_ARCHIVE_MEMBERS = 10_000
MAX_MEMBER_UNCOMPRESSED_BYTES = 512 * 1024 * 1024
MAX_ARCHIVE_UNCOMPRESSED_BYTES = 2 * 1024 * 1024 * 1024
MAX_COMPRESSION_RATIO = 100
_COPY_CHUNK_BYTES = 1024 * 1024


class UnsafeArchiveError(ValueError):
    """An archive member exceeds safety limits or has an unsafe path/type."""


def _member_destination(destination: Path, info: zipfile.ZipInfo) -> Path:
    name = PurePosixPath(info.filename)
    if not info.filename or name.is_absolute() or ".." in name.parts or "\\" in info.filename:
        raise UnsafeArchiveError(f"unsafe archive member path: {info.filename!r}")
    target = destination / Path(*name.parts)
    if not target.resolve().is_relative_to(destination.resolve()):
        raise UnsafeArchiveError(f"archive member escapes destination: {info.filename!r}")
    return target


def _validate_members(infos: list[zipfile.ZipInfo], destination: Path) -> None:
    if len(infos) > MAX_ARCHIVE_MEMBERS:
        raise UnsafeArchiveError(
            f"archive has {len(infos)} members; limit is {MAX_ARCHIVE_MEMBERS}"
        )

    total = 0
    for info in infos:
        _member_destination(destination, info)
        mode = info.external_attr >> 16
        file_type = stat.S_IFMT(mode)
        if file_type not in (0, stat.S_IFREG, stat.S_IFDIR):
            raise UnsafeArchiveError(f"archive member has unsafe file type: {info.filename!r}")
        if info.file_size > MAX_MEMBER_UNCOMPRESSED_BYTES:
            raise UnsafeArchiveError(f"archive member is too large: {info.filename!r}")
        if info.file_size and not info.compress_size:
            raise UnsafeArchiveError(
                f"archive member has invalid compressed size: {info.filename!r}"
            )
        if info.compress_size and info.file_size / info.compress_size > MAX_COMPRESSION_RATIO:
            raise UnsafeArchiveError(
                f"archive member compression ratio is too high: {info.filename!r}"
            )
        total += info.file_size
        if total > MAX_ARCHIVE_UNCOMPRESSED_BYTES:
            raise UnsafeArchiveError("archive uncompressed size exceeds limit")


def extract_zip(archive_path: Path, destination: Path) -> None:
    """Validate and extract a ZIP into an existing temporary destination.

    The caller owns the temporary directory, so no partially extracted output
    is ever promoted into the durable downloads tree.
    """
    destination.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive_path) as archive:
        infos = archive.infolist()
        _validate_members(infos, destination)
        extracted_total = 0
        for info in infos:
            target = _member_destination(destination, info)
            if info.is_dir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(info) as source, target.open("wb") as output:
                while chunk := source.read(_COPY_CHUNK_BYTES):
                    extracted_total += len(chunk)
                    if extracted_total > MAX_ARCHIVE_UNCOMPRESSED_BYTES:
                        raise UnsafeArchiveError("archive uncompressed size exceeds limit")
                    output.write(chunk)
            if target.stat().st_size != info.file_size:
                raise UnsafeArchiveError(
                    f"archive member size changed while extracting: {info.filename!r}"
                )


def read_zip_member(archive: zipfile.ZipFile, info: zipfile.ZipInfo) -> bytes:
    """Read one validated regular ZIP member without extracting its path."""
    _validate_members([info], Path.cwd())
    if info.is_dir():
        raise UnsafeArchiveError(f"archive member is a directory: {info.filename!r}")
    chunks = []
    size = 0
    with archive.open(info) as source:
        while chunk := source.read(_COPY_CHUNK_BYTES):
            size += len(chunk)
            if size > MAX_MEMBER_UNCOMPRESSED_BYTES:
                raise UnsafeArchiveError(f"archive member is too large: {info.filename!r}")
            chunks.append(chunk)
    if size != info.file_size:
        raise UnsafeArchiveError(f"archive member size changed while reading: {info.filename!r}")
    return b"".join(chunks)
