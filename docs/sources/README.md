# Data Sources

This directory contains source notes and raw schema guides for each external data source used in the MLB baseball analytics platform.

## Sources

| Source | Notes | Schema Guide |
|--------|-------|--------------|
| Retrosheet | [retrosheet-source-notes.md](./retrosheet-source-notes.md) | [retrosheet-raw-schema-guide.md](./retrosheet-raw-schema-guide.md) |
| MLB Stats API | [mlb-statsapi-source-notes.md](./mlb-statsapi-source-notes.md) | [mlb-statsapi-raw-schema-guide.md](./mlb-statsapi-raw-schema-guide.md) |
| Statcast / Baseball Savant | [statcast-source-notes.md](./statcast-source-notes.md) | [statcast-raw-schema-guide.md](./statcast-raw-schema-guide.md) |
| Lahman | [lahman-source-notes.md](./lahman-source-notes.md) | [lahman-raw-schema-guide.md](./lahman-raw-schema-guide.md) |
| FanGraphs | [fangraphs-source-notes.md](./fangraphs-source-notes.md) | [fangraphs-raw-schema-guide.md](./fangraphs-raw-schema-guide.md) |
| ESPN | [espn-source-notes.md](./espn-source-notes.md) | [espn-raw-schema-guide.md](./espn-raw-schema-guide.md) |

## Document conventions

Each source has two documents:

- **source-notes**: upstream documentation links, access patterns, stable identifiers, schema drift notes, open questions.
- **raw-schema-guide**: recommended raw table families, column definitions, batch metadata columns, and load strategy.

## Naming convention

All files in this directory use `kebab-case` with the pattern `{source}-{type}.md`.
