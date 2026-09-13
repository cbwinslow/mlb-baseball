# Example notebooks

Each notebook answers one concrete question using **only the published
`mlb-research` dataset** — no database, no cloned repository. They are
[marimo](https://marimo.io) notebooks (plain Python files).

```bash
pip install mlb-research marimo
marimo edit notebooks/02-home-run-era.py      # interactive
# or run it top to bottom:
python notebooks/02-home-run-era.py
```

| Notebook | Question | Source tables |
| --- | --- | --- |
| `01-strikeout-rate-by-decade.py` | How has league-wide K% trended by decade? | `batting_season` |
| `02-home-run-era.py` | How has HR-per-PA moved by season, and when did it peak? | `batting_season` |
| `03-three-true-outcomes.py` | What share of plate appearances end in a walk, strikeout, or homer? | `batting_season` |
| `04-babip-is-mostly-luck.py` | Which is more of a repeatable skill year to year — BABIP or K%? | `batting_season` |
| `05-strikeouts-and-scoring.py` | Have rising strikeouts actually suppressed run scoring? | `batting_season`, `batting_team` |

Every recipe recomputes rates from summed numerators and denominators rather
than averaging already-computed per-player rates, and works from the
`is_combined` season rows (one line per player per season, traded stints
merged). Coverage is the regular season, Retrosheet event-derived, 1910–2025.
The numbers move when the dataset is refreshed; the methods do not.
