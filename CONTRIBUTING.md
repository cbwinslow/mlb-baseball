# Contributing

Thank you for helping improve MLB Baseball. This project is a reproducible
baseball data and forecasting platform; correctness, source rights, and
point-in-time safety matter more than speed of change.

## Before you start

1. Read [README.md](README.md), [AGENTS.md](AGENTS.md), and [`openspec/project.md`](openspec/project.md).
   Historical execution plans are archived under [`docs/archive/plans/`](docs/archive/plans/).
2. Look for an existing issue, especially one labelled `good first issue` or
   `help wanted`. Open an issue or Discussion before beginning a large change.
3. Fork the repository and work on a branch. `main` accepts changes only by
   pull request; contributors receive no direct-write access.

## Local setup

```bash
uv sync --extra dev
uv run pre-commit install
cp .env.example .env
chmod 600 .env
```

Put your own local database URLs in `.env`; never commit that file. Tests must
use the existing disposable `mlb_test` database, never production `mlb`.

## Pull requests

Keep each pull request focused. Explain the problem, link its issue where one
exists, and state the data-rights and point-in-time implications of changes to
ingestion, transformations, features, or models.

Before requesting review, run the checks relevant to your change:

```bash
uv run pre-commit run --all-files
uv run ruff check .
uv run mypy
uv run sqlfluff lint mlb_baseball/sql/
TEST_DATABASE_URL=postgresql://.../mlb_test uv run pytest -q
```

Do not include secrets, production data dumps, copied third-party content, or
unlicensed source data. A maintainer must resolve review conversations and
merge passing pull requests.
