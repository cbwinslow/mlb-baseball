## Context

Every download-based connector fetches through `mlb_baseball/manifest.py`, which records, per
archive in `downloads/<source>/manifest.json`, the URL, `sha256`, `bytes`, `downloaded_at` and
a load `status`. Retrosheet sends `Last-Modified`, `ETag` and `Content-Length` on a HEAD
request (checked 2026-10-01 against `1910seve.zip`). The `mlb ingest <source> --refresh`
command exists (`d50b9c0`, `manifest.supersede`). `mlb status` takes about 3 minutes because
it exact-counts every table, so row counts after an ingest must not reuse that path blindly.
See `proposal.md` for the motivation.

## Goals / Non-Goals

**Goals:**
- Answer "did the publisher change anything we already downloaded?" in about a minute with no
  downloads and no database.
- Keep the comparison a pure function so it is tested without a network.
- Make ingest output unambiguous about rows loaded versus table size.

**Non-Goals:**
- Automatic refresh or scheduling. The command reports; a person (or a later change) decides.
- Sources without a download manifest (API connectors such as `mlb_api`, `statcast`).
- Diffing what changed inside an archive (the tie-out gate and a read-only diff do that).

## Decisions

**D1: `Last-Modified` after `downloaded_at` is the primary signal, `Content-Length` the
second, full SHA-256 only on request.** `Last-Modified` newer than our download is direct
evidence the file was republished and needs no stored publisher state. `Content-Length`
catches cases where the header is missing or clocks are odd. Equal size alone is not proof
(a regenerated archive can keep its size), so "unchanged" requires both present and agreeing,
and `--hash` is the proof when it matters. Rejected: storing the `ETag` in the manifest (the
manifest has none today, existing downloads would all read "unknown", and it needs a schema
change); rejected: always hashing (downloads hundreds of MB to answer a yes/no question).

**D2: One HEAD request per archive, sequential, with the existing retry helper style.** About
60 archives across the Retrosheet sources; sequential keeps load on the publisher polite and
the code simple. No threads (the project has a recorded Retrosheet concurrency hang).

**D3: Row totals use an exact `count(*)` under a 30 s statement timeout, per table, in a
read-only connection.** An estimate from `pg_class.reltuples` is stale right after a load,
exactly when this output is read. A timeout prints "not counted", never a guess. The load
itself is unaffected: counting runs after the connector returns.

**D4: Exit codes: 0 nothing changed, 1 something changed, 2 could not check.** Makes it usable
from the daily job later without parsing text.

**D5: Module `mlb_baseball/source_check.py`, command name `source-check`.** Short names, one
reason to change. Pure `classify(entry, headers)`; a thin `fetch_headers(url)`; `run(...)`
glues them and prints. The CLI only parses arguments and calls `run`.

## Risks / Trade-offs

- A publisher that does not send `Last-Modified` is reported "unknown" for those archives;
  `--hash` is then the only proof. Acceptable and visible.
- Clock skew between our `downloaded_at` and the publisher's `Last-Modified` could mislabel an
  archive modified within minutes of our download. The report prints both timestamps so it is
  checkable.
- Counting large tables adds up to 30 s each to an ingest. Opt-out is not added; the cost is
  bounded and the output is the point.
