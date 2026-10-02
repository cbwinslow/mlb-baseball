## 1. Comparison logic

- [x] 1.1 Add `mlb_baseball/source_check.py` with a pure `classify(entry, headers)` returning changed / unchanged / unknown / gone for an archive; verify with unit tests for each scenario in the spec (newer `Last-Modified`, different size, both agree, no usable headers, 404, equal hash overriding differing headers, missing manifest, empty manifest).
- [x] 1.2 Add `fetch_headers(url)` (HEAD with timeout and the project's retry style, 404 -> gone, other failure -> unknown with the error) and `run(sources, hash_check)` that reads manifests, never writes to `downloads/` and never opens a database; verify with a test that mocks the network and asserts the downloads tree is byte-identical before and after.

## 2. Command

- [x] 2.1 Register `mlb source-check [--source S ...] [--hash]` in `mlb_baseball/cli.py` with exit codes 0 / 1 / 2 and the `mlb ingest <source> --refresh` hint per changed source; verify with `tests/unit/test_cli_dispatch.py` cases for each exit code and for `--source` filtering.
- [x] 2.2 Implement `--hash` (download to a temporary file, compare SHA-256, delete the file); verify with a test that an equal hash reports unchanged and the temporary file is gone.

## 3. Ingest output

- [x] 3.1 Print rows loaded and table total after `mlb ingest`, with a 30 s per-table count timeout printing "not counted"; verify with a test using a fake connector and a stub counter (normal, timeout, scoped reload where loaded < total).

## 4. Docs and the real run

- [x] 4.1 Update `mlb_baseball/cli.py.dox.md` (new command, exit codes, `--refresh`, output) and run `scripts/check_dox.py`; verify it passes.
- [x] 4.2 Run `mlb source-check` against the real manifests (read-only); record the output in `results.md` in this change and confirm it reports the 2026-08-09 republish for the Retrosheet sources reloaded before it and "unchanged" for the ones refreshed on 2026-10-01; verify `openspec validate source-change-check` passes.
