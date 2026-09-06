import marimo

__generated_with = "0.24.0"
app = marimo.App(width="medium")


@app.cell
def _():
    import marimo as mo
    import mlb_research
    import pandas as pd

    return mlb_research, mo, pd


@app.cell
def _(mo):
    mo.md(
        r"""
        # How has the league-wide strikeout rate trended, by decade?

        A classic "rise of the strikeout" question, answered from the
        published [MLB Research Statistic Backbone](https://huggingface.co/datasets/cbwinslow/mlb-research)
        via the `mlb-research` package -- no database connection, no cloned
        repository, just `pip install mlb-research`.

        Uses `batting_season`'s combined per-player-season rows (one row per
        player per season, traded stints already merged), summing the raw
        `so` (strikeouts) and `pa` (plate appearances) counts per decade and
        dividing -- a true rate over additive facts, not an average of
        already-computed per-player rates (which would over-weight players
        with few plate appearances).
        """
    )
    return


@app.cell
def _(mlb_research):
    batting_season = mlb_research.load("batting_season")
    return (batting_season,)


@app.cell
def _(batting_season, mo):
    mo.md(f"Loaded {len(batting_season):,} `batting_season` rows.")
    return


@app.cell
def _(batting_season, pd):
    combined = batting_season[batting_season["is_combined"]].copy()
    combined["decade"] = (combined["season"] // 10 * 10).astype(int)

    by_decade = combined.groupby("decade").agg(pa=("pa", "sum"), so=("so", "sum"))
    by_decade["k_pct"] = by_decade["so"] / by_decade["pa"]
    by_decade = by_decade.sort_index()
    return (by_decade,)


@app.cell
def _(by_decade, mo):
    mo.md("## League-wide K% by decade")
    return


@app.cell
def _(by_decade):
    by_decade[["pa", "so", "k_pct"]]
    return


@app.cell
def _(by_decade, mo):
    first_decade = by_decade.index.min()
    last_decade = by_decade.index.max()
    first_k = by_decade.loc[first_decade, "k_pct"]
    last_k = by_decade.loc[last_decade, "k_pct"]
    mo.md(
        f"K% moved from **{first_k:.1%}** in the {first_decade}s to "
        f"**{last_k:.1%}** in the {last_decade}s -- "
        f"a {(last_k - first_k) * 100:.1f} percentage-point rise, computed "
        f"entirely from Retrosheet-derived counting stats."
    )
    return


if __name__ == "__main__":
    app.run()
