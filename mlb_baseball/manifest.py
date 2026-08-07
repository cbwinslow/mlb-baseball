"""Disk-persisted downloads with a per-source JSON manifest tracking file state.

Replaces the fetch-straight-into-memory pattern the Retrosheet connectors used
originally: a bootstrap pulling ~128 years of zips had nothing on disk to show
for it, so any crash or bug discovered partway through meant re-downloading
everything already fetched. Downloading to downloads/<source>/ first, and
recording each file's hash/status in a manifest, means a rerun only fetches
what's missing or changed — the parse/load stages can also be rerun
independently without re-hitting the network at all.

Kept intentionally lightweight (a JSON file per source, not a Postgres control
schema) — file-level tracking here, run-level tracking stays in
meta.ingestion_run via mlb_baseball.ingest.track_run. Two different concerns,
no overlap.
"""

import hashlib
import json
import shutil
from datetime import UTC, datetime
from pathlib import Path

from mlb_baseball.net import get_with_retry

DOWNLOADS_ROOT = Path(__file__).resolve().parent.parent / "downloads"

# Below this, warn — Retrosheet's full raw+CSV corpus is a few hundred MB,
# but a near-empty disk is worth flagging before a multi-hour bootstrap runs
# into it rather than discovering it from a mid-run write failure.
LOW_DISK_WARNING_BYTES = 2 * 1024 * 1024 * 1024  # 2GB


def check_downloads_directory() -> tuple[bool, str]:
    """Used by `mlb doctor` — not scoped to one connector, every download-
    based connector shares this same directory and disk. Returns (ok, detail)
    rather than a Check directly so it has no dependency on health.py/doctor.py,
    matching this module's existing "no dependency on connectors" shape."""
    try:
        DOWNLOADS_ROOT.mkdir(parents=True, exist_ok=True)
        probe = DOWNLOADS_ROOT / ".doctor_write_probe"
        probe.write_text("ok")
        probe.unlink()
    except OSError as exc:
        return False, f"{DOWNLOADS_ROOT} is not writable: {exc}"

    free_bytes = shutil.disk_usage(DOWNLOADS_ROOT).free
    free_gb = free_bytes / (1024**3)
    if free_bytes < LOW_DISK_WARNING_BYTES:
        return False, f"{DOWNLOADS_ROOT} writable, but only {free_gb:.1f}GB free on that disk"
    return True, f"{DOWNLOADS_ROOT} writable, {free_gb:.1f}GB free"


def _manifest_path(source: str) -> Path:
    return DOWNLOADS_ROOT / source / "manifest.json"


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def load_manifest(source: str) -> dict:
    path = _manifest_path(source)
    if not path.exists():
        return {}
    return json.loads(path.read_text())


def save_manifest(source: str, manifest: dict) -> None:
    path = _manifest_path(source)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(manifest, indent=2, sort_keys=True))
    temporary.replace(path)


def schema_fingerprint(columns: list[str]) -> str:
    return _sha256("\x1f".join(columns).encode())


def mark_status(
    source: str,
    filename: str,
    status: str,
    *,
    parser_version: str | None = None,
    schema_columns: list[str] | None = None,
) -> None:
    """Always sets the file's status, creating a manifest entry if one
    doesn't exist yet (rather than silently doing nothing — the previous
    guard-on-existing-entry version made this a silent no-op whenever
    called without a prior download() call for that exact filename, e.g.
    whenever a connector's test mocks download() directly)."""
    manifest = load_manifest(source)
    entry = manifest.setdefault(filename, {})
    entry["status"] = status
    if parser_version is not None:
        entry["parser_version"] = parser_version
    if schema_columns is not None:
        entry["schema_fingerprint"] = schema_fingerprint(schema_columns)
    save_manifest(source, manifest)


def download_required(source: str, filename: str, url: str, *, force: bool = False) -> Path:
    """download(), for files that must exist — whole-file products like
    rosters.zip or tranDB.zip where a 404 means the source moved or broke,
    never "not published yet". Raises with the URL in the message instead of
    returning None, so the failure reads as "retrosheet.org 404" rather than
    the TypeError a None path would produce inside ZipFile()/read_csv()
    several frames later. Per-year fetches where a missing year is a normal
    outcome (a future season's gamelog) should keep calling download() and
    handling None."""
    path = download(source, filename, url, force=force)
    if path is None:
        raise RuntimeError(f"{source}: required file {filename} returned 404 from {url}")
    return path


def download(source: str, filename: str, url: str, *, force: bool = False) -> Path | None:
    """Downloads `url` to downloads/<source>/<filename> unless a manifest entry
    already matches the file on disk (same content, skip the network entirely).

    Returns None on a 404 (e.g. a season not yet published) — same convention
    the connectors' fetch helpers used before. Records status="downloaded" in
    the manifest on success; parse/load stages advance status further via
    mark_status() so a crash mid-pipeline can resume without re-fetching.

    Pass force=True to always hit the network — needed for archives Retrosheet
    keeps appending to or correcting in place (e.g. the current decade's event
    file zip, or a still-in-progress season), where a same-name file on disk
    doesn't guarantee the remote copy hasn't changed. Bootstrap of historical,
    closed-out archives should leave this False.
    """
    manifest = load_manifest(source)
    dest = DOWNLOADS_ROOT / source / filename
    entry = manifest.get(filename)
    if not force and entry and dest.exists() and _sha256(dest.read_bytes()) == entry["sha256"]:
        return dest

    response = get_with_retry(url)
    if response.status_code == 404:
        return None
    response.raise_for_status()

    dest.parent.mkdir(parents=True, exist_ok=True)
    temporary = dest.with_name(f".{dest.name}.tmp")
    temporary.write_bytes(response.content)
    temporary.replace(dest)

    manifest[filename] = {
        "url": url,
        "sha256": _sha256(response.content),
        "bytes": len(response.content),
        "downloaded_at": datetime.now(UTC).isoformat(),
        "status": "downloaded",
    }
    save_manifest(source, manifest)
    return dest
