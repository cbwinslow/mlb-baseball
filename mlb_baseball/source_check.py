"""Detect that a publisher changed an archive we already downloaded.

``mlb source-check`` reads each ``downloads/<source>/manifest.json``, sends one HEAD
request per recorded archive URL and compares the answer with what the manifest
recorded. It never downloads an archive into ``downloads/``, never writes there and never
opens a database. ``--hash`` is the one exception: it fetches each archive to a temporary
file outside ``downloads/``, compares SHA-256 and deletes the file.

Retrosheet regenerated every file on 2026-08-09 and nothing noticed, because the download
cache trusts a closed archive forever. This is the cheap way to notice.
"""

import hashlib
import tempfile
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from pathlib import Path

import requests

from mlb_baseball import manifest
from mlb_baseball.net import get_with_retry, head_with_retry

CHANGED = "changed"
UNCHANGED = "unchanged"
UNKNOWN = "unknown"
GONE = "gone"

EXIT_OK = 0
EXIT_CHANGED = 1
EXIT_UNCHECKED = 2


@dataclass(frozen=True)
class Head:
    """What a HEAD request told us. ``error`` is set when no response arrived."""

    status: int | None = None
    last_modified: datetime | None = None
    content_length: int | None = None
    error: str | None = None


@dataclass(frozen=True)
class Verdict:
    status: str
    detail: str = ""


@dataclass(frozen=True)
class Result:
    source: str
    archive: str
    verdict: Verdict


def _parse_time(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def classify(entry: dict, head: Head, *, remote_sha256: str | None = None) -> Verdict:
    """Compare one manifest entry with what the publisher says now.

    A full-file hash, when given, overrides the headers: equal means unchanged even if
    the headers differ. Otherwise ``changed`` needs a newer ``Last-Modified`` or a
    different ``Content-Length``; ``unchanged`` needs both present and agreeing.
    """
    if head.error is not None:
        return Verdict(UNKNOWN, head.error)
    if head.status == 404:
        return Verdict(GONE, "HTTP 404")
    if remote_sha256 is not None:
        if remote_sha256 == entry.get("sha256"):
            return Verdict(UNCHANGED, "sha256 equal")
        return Verdict(CHANGED, "sha256 differs")
    if head.status is None or head.status >= 400:
        return Verdict(UNKNOWN, f"HTTP {head.status}")

    downloaded_at = _parse_time(entry.get("downloaded_at"))
    recorded_bytes = entry.get("bytes")
    newer = (
        head.last_modified is not None
        and downloaded_at is not None
        and head.last_modified > downloaded_at
    )
    if newer:
        return Verdict(
            CHANGED,
            f"Last-Modified {head.last_modified:%Y-%m-%d %H:%M} UTC is after "
            f"downloaded {downloaded_at:%Y-%m-%d %H:%M} UTC",
        )
    size_differs = (
        head.content_length is not None
        and recorded_bytes is not None
        and head.content_length != recorded_bytes
    )
    if size_differs:
        return Verdict(CHANGED, f"size {recorded_bytes} -> {head.content_length} bytes")

    time_agrees = head.last_modified is not None and downloaded_at is not None
    size_agrees = head.content_length is not None and recorded_bytes is not None
    if time_agrees and size_agrees:
        return Verdict(UNCHANGED)
    return Verdict(UNKNOWN, "response gave no usable Last-Modified and Content-Length")


def fetch_headers(url: str) -> Head:
    """HEAD ``url`` with the project's retry helper. 404 is data; any other failure is
    returned as an ``error``, never raised."""
    try:
        response = head_with_retry(url, timeout=30)
    except requests.exceptions.RequestException as exc:
        return Head(error=f"{type(exc).__name__}: {exc}")
    last_modified = None
    raw_time = response.headers.get("Last-Modified")
    if raw_time:
        try:
            last_modified = parsedate_to_datetime(raw_time)
        except (TypeError, ValueError):
            last_modified = None
        if last_modified is not None and last_modified.tzinfo is None:
            last_modified = last_modified.replace(tzinfo=UTC)
    raw_length = response.headers.get("Content-Length")
    content_length = int(raw_length) if raw_length and raw_length.isdigit() else None
    return Head(
        status=response.status_code, last_modified=last_modified, content_length=content_length
    )


def fetch_sha256(url: str) -> str | None:
    """SHA-256 of the archive at ``url``, via a temporary file that is always removed.
    None on a 404."""
    response = get_with_retry(url)
    if response.status_code == 404:
        return None
    response.raise_for_status()
    with tempfile.NamedTemporaryFile(prefix="source-check-", suffix=".tmp", delete=False) as tmp:
        tmp_path = Path(tmp.name)
        tmp.write(response.content)
    try:
        return hashlib.sha256(tmp_path.read_bytes()).hexdigest()
    finally:
        tmp_path.unlink(missing_ok=True)


def discover_sources() -> list[str]:
    """Every source directory under ``downloads/`` (set-aside copies excluded)."""
    root = manifest.DOWNLOADS_ROOT
    if not root.is_dir():
        return []
    return sorted(p.name for p in root.iterdir() if p.is_dir() and not p.name.startswith("_"))


def check(
    sources: Iterable[str],
    *,
    hash_check: bool = False,
    head: Callable[[str], Head] = fetch_headers,
    sha256: Callable[[str], str | None] = fetch_sha256,
) -> tuple[list[Result], list[str]]:
    """Check every archive in each source's manifest. Returns the per-archive results
    and the sources that have no download record. Never writes to ``downloads/``."""
    results: list[Result] = []
    no_record: list[str] = []
    for source in sources:
        entries = manifest.load_manifest(source)
        if not entries:
            no_record.append(source)
            continue
        for archive, entry in sorted(entries.items()):
            url = entry.get("url")
            if not url:
                results.append(Result(source, archive, Verdict(UNKNOWN, "no url recorded")))
                continue
            remote_sha = None
            if hash_check:
                try:
                    remote_sha = sha256(url)
                except requests.exceptions.RequestException as exc:
                    verdict = Verdict(UNKNOWN, f"{type(exc).__name__}: {exc}")
                    results.append(Result(source, archive, verdict))
                    continue
                if remote_sha is None:
                    results.append(Result(source, archive, Verdict(GONE, "HTTP 404")))
                    continue
            seen = head(url) if remote_sha is None else Head(status=200)
            results.append(Result(source, archive, classify(entry, seen, remote_sha256=remote_sha)))
    return results, no_record


def exit_code(results: list[Result], no_record: list[str], *, requested: bool) -> int:
    """1 when anything changed, else 2 when anything could not be checked, else 0.

    A source with no download record only counts as unchecked when it was asked for by
    name; a stray empty directory should not fail a routine run."""
    statuses = {r.verdict.status for r in results}
    if CHANGED in statuses:
        return EXIT_CHANGED
    if statuses & {UNKNOWN, GONE} or (requested and no_record):
        return EXIT_UNCHECKED
    return EXIT_OK


def render(results: list[Result], no_record: list[str]) -> list[str]:
    lines: list[str] = []
    by_source: dict[str, list[Result]] = {}
    for result in results:
        by_source.setdefault(result.source, []).append(result)
    changed_sources: list[str] = []
    for source, items in by_source.items():
        counts = {s: sum(1 for r in items if r.verdict.status == s) for s in _ORDER}
        lines.append(
            f"{source}: {len(items)} archives - " + ", ".join(f"{counts[s]} {s}" for s in _ORDER)
        )
        for item in items:
            if item.verdict.status != UNCHANGED:
                detail = f" ({item.verdict.detail})" if item.verdict.detail else ""
                lines.append(f"  {item.verdict.status}: {item.archive}{detail}")
        if counts[CHANGED]:
            changed_sources.append(source)
    for source in no_record:
        lines.append(f"{source}: no download record")
    if changed_sources:
        lines.append("")
        lines.append("Publisher changed files we already downloaded. To reload:")
        lines.extend(f"  mlb ingest {source} --refresh" for source in changed_sources)
    elif results:
        lines.append("")
        lines.append("No source changed.")
    return lines


_ORDER = (CHANGED, UNCHANGED, UNKNOWN, GONE)


def run(sources: list[str] | None = None, *, hash_check: bool = False) -> int:
    """Check ``sources`` (default: every source with a download directory), print the
    report and return the process exit code."""
    chosen = sources or discover_sources()
    results, no_record = check(chosen, hash_check=hash_check)
    for line in render(results, no_record):
        print(line)
    return exit_code(results, no_record, requested=bool(sources))
