"""Cached, hash-verified download of official Retrosheet files and zip reading."""

import hashlib
import io
import os
import tempfile
import urllib.request
import zipfile
import zlib
from collections.abc import Callable, Iterator
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import IO, Any

from retrosheetpy.artifact import Artifact
from retrosheetpy.catalog import Resource
from retrosheetpy.errors import IntegrityError, InvalidArchiveError, UnsafeArchiveMemberError

USER_AGENT = "retrosheetpy/0.0.1"

Fetch = Callable[[str], bytes]


def http_fetch(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=120) as resp:  # noqa: S310 - fixed https URLs
        data: bytes = resp.read()
        return data


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


class Client:
    """Downloads Resources into ``cache_dir`` and returns Artifact metadata.

    ``fetch`` is injectable so tests never touch the live site.
    """

    def __init__(self, cache_dir: str | Path, fetch: Fetch = http_fetch):
        self.cache_dir = Path(cache_dir)
        self._fetch = fetch

    def _paths(self, res: Resource) -> tuple[Path, Path]:
        if res.filename in ("", ".", "..") or res.filename != Path(res.filename).name:
            raise ValueError(f"unsafe resource filename: {res.filename!r}")
        # Per-season files get a season folder; shared archives (a decade zip
        # serves many seasons) sit directly under the product folder.
        folder = self.cache_dir / res.product.value
        if res.season is not None and res.group is None:
            folder = folder / str(res.season)
        data = folder / res.filename
        return data, data.with_name(data.name + ".json")

    def _cached(self, res: Resource, refetch_on_mismatch: bool) -> Artifact | None:
        data, meta = self._paths(res)
        if not (data.is_file() and meta.is_file()):
            return None
        try:
            art = Artifact.from_json(meta.read_text())
        except (ValueError, KeyError, TypeError):
            art = None  # unreadable metadata: the cached bytes cannot be trusted
        if art is not None and art.source_url == res.url and _sha256_file(data) == art.sha256:
            # One archive can serve several requested seasons: report the request's identity.
            return replace(
                art, local_path=data, product=res.product, season=res.season, group=res.group
            )
        if not refetch_on_mismatch:
            raise IntegrityError(f"{data} does not match its recorded metadata")
        return None

    def download(
        self, res: Resource, *, force: bool = False, refetch_on_mismatch: bool = True
    ) -> Artifact:
        if not force:
            hit = self._cached(res, refetch_on_mismatch)
            if hit is not None:
                return hit
        payload = self._fetch(res.url)
        if res.is_zip:
            _check_zip_payload(payload, res.url)
        data, meta = self._paths(res)
        data.parent.mkdir(parents=True, exist_ok=True)
        art = Artifact(
            source_url=res.url,
            product=res.product,
            season=res.season,
            group=res.group,
            local_path=data,
            sha256=hashlib.sha256(payload).hexdigest(),
            size=len(payload),
            retrieved_at=datetime.now(UTC),
        )
        _atomic_write(data, payload)
        _atomic_write(meta, art.to_json().encode())
        return art


_ZIP_READ_ERRORS = (zipfile.BadZipFile, zlib.error, EOFError, NotImplementedError)


def _check_zip_payload(payload: bytes, url: str) -> None:
    """Raise unless ``payload`` is a complete, readable, safely-named zip."""
    try:
        with zipfile.ZipFile(io.BytesIO(payload)) as zf:
            for info in zf.infolist():
                _check_member(info.filename)
            if zf.testzip() is not None:
                raise InvalidArchiveError(f"{url}: archive has a corrupt member")
    except _ZIP_READ_ERRORS as exc:
        raise InvalidArchiveError(f"{url} did not return a valid zip archive") from exc


def _atomic_write(path: Path, payload: bytes) -> None:
    # Unique temp name in the same folder, so concurrent writers never share a file.
    fd, tmp_name = tempfile.mkstemp(dir=path.parent, prefix=path.name + ".", suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(payload)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_name, path)
    except BaseException:
        Path(tmp_name).unlink(missing_ok=True)
        raise


def _check_member(name: str) -> None:
    norm = name.replace("\\", "/")
    p = PurePosixPath(norm)
    if p.is_absolute() or ".." in p.parts or (len(norm) > 1 and norm[1] == ":"):
        raise UnsafeArchiveMemberError(f"unsafe zip member name: {name!r}")


class _GuardedStream:
    """Wraps a zip member stream so read-time corruption surfaces as InvalidArchiveError."""

    def __init__(self, stream: IO[bytes], where: str):
        self._stream = stream
        self._where = where

    def _guard(self, fn: Callable[..., Any], *args: Any) -> Any:
        try:
            return fn(*args)
        except _ZIP_READ_ERRORS as exc:
            raise InvalidArchiveError(f"{self._where}: corrupt member data") from exc

    def read(self, size: int = -1) -> bytes:
        data: bytes = self._guard(self._stream.read, size)
        return data

    def readline(self, size: int = -1) -> bytes:
        line: bytes = self._guard(self._stream.readline, size)
        return line

    def __iter__(self) -> "_GuardedStream":
        return self

    def __next__(self) -> bytes:
        line: bytes = self._guard(self._stream.__next__)
        return line


def iter_zip_members(path: str | Path) -> Iterator[tuple[str, IO[bytes]]]:
    """Yield ``(member_name, binary_stream)`` for each file in the zip.

    Nothing is extracted to disk. Unsafe names and corrupt archives raise.
    """
    try:
        zf = zipfile.ZipFile(path)
    except zipfile.BadZipFile as exc:
        raise InvalidArchiveError(f"{path} is not a valid zip archive") from exc
    with zf:
        for info in zf.infolist():
            _check_member(info.filename)
        for info in zf.infolist():
            if info.is_dir():
                continue
            try:
                with zf.open(info) as f:
                    yield info.filename, _GuardedStream(f, f"{path}:{info.filename}")  # type: ignore[misc]
            except _ZIP_READ_ERRORS as exc:
                raise InvalidArchiveError(f"{path}: corrupt member {info.filename}") from exc
