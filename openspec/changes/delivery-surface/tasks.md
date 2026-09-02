## 1. Rights check + `backbone` export preset

- [ ] 1.1 For each of the ten backbone tables, resolve its publish profile via `mlb_baseball/source_profiles.py` / `export.py`'s allow-list. Verify: a written note in the PR listing each table -> profile -> publishable (yes/no). `player_season` (Baseball-Reference) and `team_season` (Lahman) are the ones to scrutinize.
- [ ] 1.2 Add a `backbone` preset to `mlb_baseball/export.py` = the publishable subset of the ten tables (drop any 1.1 flagged ineligible, with its exclusion recorded in the manifest + log). Verify: `uv run pytest tests/integration/test_export*.py -q` plus a new test asserting `mlb export --preset backbone` emits one `data/<table>.parquet` per eligible table + `manifest.json`, and that an ineligible table appears in the manifest's `excluded` list with a reason.
- [ ] 1.3 Make the export query `ORDER BY` each table's primary key so row order is deterministic. Verify: a test that runs the export twice and asserts identical row counts and identical first/last row per table.
- [ ] 1.4 Add a `dataset_card.md` (as `README.md` in the bundle root) writer: source (Retrosheet event-derived), coverage (seasons present, regular season only), licence, schema version, links to the repo and `docs/RESEARCH.md`. Verify: a test asserting the card exists in the bundle and contains the schema version from the manifest.
- [ ] 1.5 Round-trip test: write the bundle with pyarrow, read every Parquet back with `duckdb`, assert each table's column names + types match its `manifest.json` entry. Verify: the test passes.

## 2. Hugging Face publish

- [ ] 2.1 Add `huggingface_hub` to the `export` extra. Verify: `uv sync --extra export` succeeds and `python -c "import huggingface_hub"` works.
- [ ] 2.2 Add a publish step (`mlb export --preset backbone --publish hf --tag <tag>` or a `publish.py`): `HfApi().upload_folder(<bundle dir>, repo_id=<owner>/mlb-research, repo_type=dataset, revision=<tag>)`, `HF_TOKEN` read from `os.environ` (never a flag, never logged). Verify: a unit test with `huggingface_hub` mocked asserting the folder path, repo_type=dataset, and revision are passed through and that the token is not present in any log record or the command's argv.
- [ ] 2.3 Document the manual publish (`HF_TOKEN=... mlb export --preset backbone --publish hf --tag v0.1.0`) in `docs/PUBLIC_API.md` or a delivery doc, with the "never `export HF_TOKEN`" note. Verify: the doc section exists and is linked from `openspec/project.md`.

## 3. `mlb-research` Python package

- [ ] 3.1 Create `packages/mlb-research/` with its own `pyproject.toml` (name `mlb-research`, import `mlb_research`, deps `duckdb` + `huggingface_hub` + `pandas`); add it as a `[tool.uv.workspace]` member. Verify: `uv sync` resolves the workspace and `uv run python -c "import mlb_research"` works.
- [ ] 3.2 Implement `mlb_research.load(table, *, season=None, version="latest")`: resolve `version` -> HF revision, `hf_hub_download` the table's Parquet (cached), read via `duckdb` with `season` filter pushdown, return a `DataFrame`. Verify: a test using a locally-produced bundle (task 1) served from a `tmp_path` / a mocked `hf_hub_download` -> `load("pitching_season", season=2023)` returns a DataFrame with only 2023 rows and the documented columns.
- [ ] 3.3 Error contract: unknown table -> `ValueError` naming it + listing valid names; unreachable version -> a clear wrapped error. Verify: tests for both.
- [ ] 3.4 Caching: second `load()` of the same table+version does no network I/O. Verify: a test that patches the downloader to raise on a second call and asserts `load()` still returns.
- [ ] 3.5 A `README.md` for the package with the `load()` API and a 5-line example. Verify: the file exists; the example matches the implemented signature.

## 4. DuckDB-WASM query page

- [ ] 4.1 `docs/site/query/index.html` + a small JS module: load `@duckdb/duckdb-wasm` from jsDelivr, register the backbone tables as views over their HF Parquet `resolve/<tag>/data/<table>.parquet` URLs, a SQL textarea + Run button + results table, inline error display. Verify: open the file in a browser (or a headless run), submit `SELECT * FROM batting_season WHERE season = 2023 LIMIT 5`, confirm 5 rows render and the network panel shows only HF (no project backend); submit a bad-column query, confirm the DB error text shows in the UI.
- [ ] 4.2 A GitHub Actions `pages` workflow that publishes `docs/site/`. Verify: a successful Pages deployment; the query page is reachable at the Pages URL.

## 5. First publish + wire-up + notebook

- [ ] 5.1 Owner runs the first real publish for tag `v0.1.0`. Verify: the HF dataset shows a `v0.1.0` revision with `data/*.parquet`, `manifest.json`, `README.md`, downloadable by tag.
- [ ] 5.2 Point the query page URLs and `mlb_research`'s `"latest"` at the published dataset. Verify: `mlb_research.load("batting_season", season=2023)` works from a clean venv with only `pip install mlb-research`; the query page works from its Pages URL.
- [ ] 5.3 `notebooks/01-<question>.py` (Marimo) answering one real analyst question using only `mlb_research.load(...)`, no DB connection. Verify: `uv run marimo export html notebooks/01-*.py` completes and the notebook makes no psycopg/Postgres call (grep the source).
- [ ] 5.4 Update `openspec/project.md` (delivery section + milestone progress) and `docs/PUBLIC_API.md`. Verify: links resolve; `openspec validate --all` passes.

## 6. Integration verification

- [ ] 6.1 End-to-end: fresh checkout -> `mlb export --preset backbone --out /tmp/b` -> `mlb_research` pointed at `/tmp/b` -> `load()` every backbone table successfully -> the query page (pointed at a local file server for the test) runs a query against each. Verify: a script or documented manual run that exercises all four surfaces against one bundle with no failures.
