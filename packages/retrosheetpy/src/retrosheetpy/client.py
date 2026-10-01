"""Cached, hash-verified download of official Retrosheet files and zip reading."""

import hashlib
import io
import os
import urllib.request
import zipfile
from collections.abc import Callable, Iterator
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import IO

from retrosheetpy.artifact import Artifact
from retrosheetpy.catalog import Resource
from retrosheetpy.errors import IntegrityError, InvalidArchiveError, UnsafeArchiveMemberError

USER_AGENT = "retrosheetpy (+https://github.com/cbwinslow/mlb-baseball)"

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
        data = (
            self.cache_dir
            / res.product.value
            / (f"{res.season}" if res.season is not None and res.group is None else "")
            / res.filename
        )
        return data, data.with_name(data.name + ".json")

    def _cached(self, res: Resource, refetch_on_mismatch: bool) -> Artifact | None:
        data, meta = self._paths(res)
        if not (data.is_file() and meta.is_file()):
            return None
        art = Artifact.from_json(meta.read_text())
        if art.source_url == res.url and _sha256_file(data) == art.sha256:
            return Artifact(**{**art.__dict__, "local_path": data})
        if not refetch_on_mismatch:
            raise IntegrityError(f"{data} does not match its recorded SHA-256")
        return None

    def download(
        self, res: Resource, *, force: bool = False, refetch_on_mismatch: bool = True
    ) -> Artifact:
        if not force:
            hit = self._cached(res, refetch_on_mismatch)
            if hit is not None:
                return hit
        payload = self._fetch(res.url)
        if res.is_zip and not _is_valid_zip(payload):
            raise InvalidArchiveError(f"{res.url} did not return a valid zip archive")
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


def _is_valid_zip(payload: bytes) -> bool:
    try:
        with zipfile.ZipFile(io.BytesIO(payload)) as zf:
            return zf.testzip() is None
    except zipfile.BadZipFile:
        return False


def _atomic_write(path: Path, payload: bytes) -> None:
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_bytes(payload)
    os.replace(tmp, path)


def _check_member(name: str) -> None:
    norm = name.replace("\\", "/")
    p = PurePosixPath(norm)
    if p.is_absolute() or ".." in p.parts or (len(norm) > 1 and norm[1] == ":"):
        raise UnsafeArchiveMemberError(f"unsafe zip member name: {name!r}")


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
                    yield info.filename, f
            except zipfile.BadZipFile as exc:
                raise InvalidArchiveError(f"{path}: corrupt member {info.filename}") from exc
