# Public Python API

`mlb-baseball` helps researchers bootstrap a **database they own**. It does
not host data, expose a public query API, or create a database automatically.

The supported import surface is deliberately small and exported from
`mlb_baseball`:

| API | Purpose |
|---|---|
| `configure()` | Set process-local `DATABASE_URL` and data-rights profile. No connection or write occurs. |
| `migrate_database()` | Apply package migrations to the configured local database. |
| `ingest_source()` | Run one registered connector after profile validation. |
| `conform_database()` | Build canonical `core` relations from landed `raw` data. |
| `build_features()` | Rebuild point-in-time `gold.game_feature` rows. |
| `run_predictions()` | Run the feature stage and append prediction snapshots. |
| `get_connection()` | Obtain a normal psycopg connection for researcher SQL. |
| `inventory_tables()` / `inventory_runs()` | Inspect landed relations and recent connector runs. |
| `health_checks()` | Run read-only operational health checks. |

Everything else is implementation detail, including connector modules, loaders,
advisory-lock functions, and individual conformance builders. Their imports
are not compatibility promises.

## Local bootstrap example

Create and operate your own PostgreSQL database outside this package, then:

```python
import mlb_baseball as mlb

mlb.configure(
    database_url="postgresql:///my_mlb_research",
    profile="public_safe",
)
mlb.migrate_database()

# The profile is fail-closed. Retrosheet-family sources are currently allowed
# in public_safe; local_research is for owner-controlled research only.
mlb.ingest_source("retrosheet_reference", mode="bootstrap")
mlb.ingest_source("retrosheet_gamelog", mode="bootstrap")
mlb.conform_database()
mlb.build_features()

with mlb.get_connection() as conn, conn.cursor() as cur:
    cur.execute("SELECT count(*) FROM core.game")
    print(cur.fetchone())
```

`migrate_database()`, `ingest_source()`, `conform_database()`, `build_features()`,
and `run_predictions()` write only
to the configured database. Test against a disposable database first. Never
point them at someone else's or a shared production database without an
approved run plan.

## Data rights and reproducibility

Choose a source profile deliberately:

- `public_safe` is conservative and currently Retrosheet-family only.
- `licensed_full` is no broader until a documented license exists.
- `local_research` is the default for owner-controlled research and is not a
  public-display permission.

See [SOURCE_RIGHTS.md](SOURCE_RIGHTS.md), [TABLE_CONTRACTS.md](TABLE_CONTRACTS.md),
and [SQL_OWNERSHIP.md](SQL_OWNERSHIP.md) before publishing derived work.

## Before a release: run the Baseball-Reference tie-out gate

`scripts/verify_baseball_reference_tie_out.py` is the backbone's tie-out gate.
Run it against a fully-built database (`mlb report` done) before publishing a
release:

```bash
DATABASE_URL=postgresql:///mlb uv run python scripts/verify_baseball_reference_tie_out.py
```

It checks the cited modern player-season cases exactly and cross-checks the
event-derived season tables against `gold.player_season` field-by-field for
2008–2019. Known limitations it does **not** gate on are in
`docs/DATA_DICTIONARY.md` § 3 (career / pre-2000 divergence; the ADR-282
postseason issue in `gold.player_season`).

## Publishing the backbone dataset to Hugging Face

`mlb export --preset backbone` writes the publishable subset of the
grain-complete statistic backbone (eight of ten candidate tables --
`gold.player_season`/`gold.team_season` are excluded on source-rights
grounds, see
[`openspec/changes/delivery-surface/rights-review.md`](../openspec/changes/delivery-surface/rights-review.md))
to `<out>/data/<table>.parquet` + `<out>/manifest.json` + `<out>/README.md`,
the layout a Hugging Face dataset repo expects at its root.

Publishing is **owner-run, not automated** (design.md D3 — a tag-triggered
CI job is a deliberate follow-up once the manual path is proven):

```bash
HF_TOKEN=hf_your_write_token mlb export --preset backbone --publish hf --tag v0.1.0
```

**Never `export HF_TOKEN=...`.** Exporting it into the shell environment
leaves it readable to every subsequent command in that shell and in shell
history; prefixing the single command as above scopes it to that one
process. The publish step reads the credential only from `HF_TOKEN` at
runtime -- never a CLI flag (would land in shell history and process argv)
and never logged (`mlb_baseball/publish.py`).

Pass `--repo-id <owner>/<name>` to publish somewhere other than the default
`cbwinslow/mlb-research` (e.g. once the namespace decision above lands on an
org account). The publish step refuses to upload a directory that isn't
shaped exactly like a backbone bundle (`data/`, `manifest.json`, `README.md`
and nothing else) -- `HfApi().upload_folder()` has no per-file filtering, so
this is what stops a wrong `--out` from publishing unrelated files.

## Consuming the published dataset (outside this repository)

Two surfaces need no local database or clone of this repository -- see
`openspec/changes/delivery-surface/` for the change that built them:

- **`mlb-research`** (`packages/mlb-research/`, `pip install mlb-research`) --
  a standalone Python loader: `mlb_research.load("batting_season",
  season=2023)` returns a `pandas.DataFrame`. It also exposes
  `mlb_research.get_historical_features(entity_df, ["player_form:obp_30d", ...])`
  for point-in-time training rows from a locally built DuckDB feature store
  (see [FEATURE_STORE.md](FEATURE_STORE.md)). Full API in that package's own
  [README.md](../packages/mlb-research/README.md).
- **The DuckDB-WASM query page** (`docs/site/query/`) -- runs visitor SQL
  against the published Parquet entirely in the browser, published via
  GitHub Pages (`.github/workflows/pages.yml`). No server, no account.

Both currently point at the dataset's `main` revision; a tagged release
(`v0.1.0` onward) is the version to pin for reproducible research.
