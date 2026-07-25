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
from datetime import UTC, datetime
from pathlib import Path

from mlb_baseball.net import get_with_retry

DOWNLOADS_ROOT = Path(__file__).resolve().parent.parent / "downloads"


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
    path.write_text(json.dumps(manifest, indent=2, sort_keys=True))


def mark_status(source: str, filename: str, status: str) -> None:
    """Always sets the file's status, creating a manifest entry if one
    doesn't exist yet (rather than silently doing nothing — the previous
    guard-on-existing-entry version made this a silent no-op whenever
    called without a prior download() call for that exact filename, e.g.
    whenever a connector's test mocks download() directly)."""
    manifest = load_manifest(source)
    manifest.setdefault(filename, {})["status"] = status
    save_manifest(source, manifest)


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
    dest.write_bytes(response.content)

    manifest[filename] = {
        "url": url,
        "sha256": _sha256(response.content),
        "bytes": len(response.content),
        "downloaded_at": datetime.now(UTC).isoformat(),
        "status": "downloaded",
    }
    save_manifest(source, manifest)
    return dest
