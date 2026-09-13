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
        # The home run era: how has HR rate moved, by season?

        Home runs per plate appearance, league-wide, computed from the published
        [MLB Research Statistic Backbone](https://huggingface.co/datasets/cbwinslow/mlb-research)
        via `pip install mlb-research` -- no database, no cloned repository.

        **Source:** `batting_season`, the `is_combined` rows (one line per
        player per season, traded stints already merged). Regular season,
        Retrosheet event-derived, 1910-2025.

        **Method:** sum the raw `hr` and `pa` counts per season and divide -- a
        true rate over additive facts, never the mean of per-player HR rates
        (which would let a September call-up with 20 PA count as much as a
        700-PA regular).
        """
    )
    return


@app.cell
def _(mlb_research):
    batting_season = mlb_research.load("batting_season")
    return (batting_season,)


@app.cell
def _(batting_season):
    combined = batting_season[batting_season["is_combined"]]
    by_season = combined.groupby("season").agg(hr=("hr", "sum"), pa=("pa", "sum"))
    by_season["hr_per_pa"] = by_season["hr"] / by_season["pa"]
    by_season["hr_per_600_pa"] = by_season["hr_per_pa"] * 600
    return (by_season,)


@app.cell
def _(by_season, mo):
    mo.md("## The ten highest-HR seasons")
    return


@app.cell
def _(by_season):
    by_season.nlargest(10, "hr_per_pa")[["hr", "pa", "hr_per_pa", "hr_per_600_pa"]]
    return


@app.cell
def _(by_season, mo):
    low = by_season.loc[1981, "hr_per_pa"]
    high = by_season.loc[2019, "hr_per_pa"]
    mo.md(
        f"""
        ## Finding

        HR per PA more than doubled from **{low:.4f}** in 1981
        ({low * 600:.1f} per 600 PA) to a record **{high:.4f}** in 2019
        ({high * 600:.1f} per 600 PA). The top of the list is dominated by
        2017 and 2019-2021 -- the "juiced ball" seasons -- with the
        steroid-era 2000 the only pre-2016 season in the top ten.
        """
    )
    return


if __name__ == "__main__":
    app.run()
