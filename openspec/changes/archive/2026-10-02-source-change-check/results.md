# Results: `mlb source-check` against the real manifests (read-only)

Run 2026-10-02, about 98 s, 319 HEAD requests, no downloads, no database, nothing written
under `downloads/`.

## Current manifests (all Retrosheet sources refreshed on 2026-10-01): exit 0

```
retrosheet: 128 archives - 0 changed, 128 unchanged, 0 unknown, 0 gone
retrosheet_box: 9 archives - 0 changed, 9 unchanged, 0 unknown, 0 gone
retrosheet_event: 15 archives - 0 changed, 15 unchanged, 0 unknown, 0 gone
retrosheet_gamelog: 160 archives - 0 changed, 160 unchanged, 0 unknown, 0 gone
retrosheet_reference: 4 archives - 0 changed, 4 unchanged, 0 unknown, 0 gone
retrosheet_roster: 1 archives - 0 changed, 1 unchanged, 0 unknown, 0 gone
retrosheet_schedule: 1 archives - 0 changed, 1 unchanged, 0 unknown, 0 gone
retrosheet_transaction: 1 archives - 0 changed, 1 unchanged, 0 unknown, 0 gone
No source changed.
```

## The pre-refresh manifests (the July 2026 loads): exit 1

Every source was refreshed on 2026-10-01, so there is no live source left to show the
2026-08-09 republish. The same code was run over the manifests set aside under
`downloads/<source>/_superseded/` (copied to a scratch directory; the real tree untouched):

```
retrosheet_gamelog: 5 archives - 5 changed   (Last-Modified 2026-08-09 15:56 UTC after downloaded 2026-07-25 19:29 UTC)
retrosheet_event: 15 archives - 11 changed, 4 unchanged   (Last-Modified 2026-08-09 15:58-16:01 UTC)
retrosheet_roster: 1 archives - 1 changed   (Last-Modified 2026-08-09 17:42 UTC after downloaded 2026-07-25 16:00 UTC)
  mlb ingest retrosheet_gamelog --refresh
  mlb ingest retrosheet_event --refresh
  mlb ingest retrosheet_roster --refresh
```

The command would have caught the republish within a minute, two months before it was found.
