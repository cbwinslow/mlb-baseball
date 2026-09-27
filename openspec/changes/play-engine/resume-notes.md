# Resume notes — where the model conversation stopped (2026-09-27)

Written so the model plan is not lost while the pipeline fix
(`openspec/changes/pipeline-freshness/`) goes first. Not a spec: the spec is
`proposal.md`, `design.md`, `tasks.md` in this folder.

## Where we are

- The plan for the plate-appearance engine is merged (PR #251) and validated.
- Nothing is built yet. Next task is 1.1 (verify Retrosheet event codes).
- Task 1.2 (readiness gate) came back **not ready** on 2026-09-27: production
  `gold.batting_game`, `gold.pitching_game` and the roll-ups are empty, so
  `feat.player_form` / `feat.pitcher_form` built with 0 rows. Cause and fix are in
  `pipeline-freshness`. Resume here after its task 3.2.

## Decisions the owner made (keep)

- Start with the plate-appearance engine (option 2 of the earlier list).
- All three targets matter: game winner, plays and pitches, player performance.
- Ladder: league average, then ratings blend (log5 / odds-ratio), then gradient
  boosted multiclass. Neural and Bayesian engines come after that.
- Seasons: fit 2015–2021, choose on 2022–2023, score once on 2024–2025.
- Use hard values from our own database (`mlb` real data; tests use disposable
  fixtures) and read the primary papers for worked examples. Books that are
  paywalled (for example *The Book*) are marked "cited secondhand" unless the
  owner supplies the pages.
- Publishing (PyPI, Hugging Face) is tabled.

## Later list (wanted, not yet planned)

- Pitch-by-pitch prediction.
- Neural network and Bayesian engines.
- Monte Carlo and Markov chains down to plays and pitches (first version sits on
  top of the finished plate-appearance engine).
- Player-performance projections.
- Comparing game-winner probabilities against market odds.
- A separate "model library" spec listing every model and technique we make
  available (neural networks and others).
- A one-time full-codebase quality review (already in project.md LATER).

## Things to remember

- `markov-v1` (ADR-275) and bulk team features (ADR-086) already failed; the plan
  is built around those lessons (batter-versus-pitcher level, features one group
  at a time).
- Metric catalog real counts: 39 tracked model modules, 50 YAML files.
