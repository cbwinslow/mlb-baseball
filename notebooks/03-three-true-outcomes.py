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
        # Three True Outcomes: how much of the game happens without a ball in play?

        A "true outcome" -- a walk, a strikeout, or a home run -- is settled
        between the batter and the pitcher alone, with no fielder involved. This
        recipe tracks the share of plate appearances that end that way, by
        season, from the published
        [MLB Research Statistic Backbone](https://huggingface.co/datasets/cbwinslow/mlb-research).

        **Source:** `batting_season`, `is_combined` rows. Regular season,
        Retrosheet event-derived, 1910-2025.

        **Method:** `(sum(bb) + sum(so) + sum(hr)) / sum(pa)` per season -- a
        rate over summed components, not an average of per-player rates.
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
    tto = combined.groupby("season").agg(
        bb=("bb", "sum"), so=("so", "sum"), hr=("hr", "sum"), pa=("pa", "sum")
    )
    tto["tto_share"] = (tto["bb"] + tto["so"] + tto["hr"]) / tto["pa"]
    return (tto,)


@app.cell
def _(mo, tto):
    decade = tto.assign(decade=(tto.index // 10 * 10)).groupby("decade")
    mo.md("## TTO share, by decade (PA-weighted)")
    return (decade,)


@app.cell
def _(decade):
    d = decade.agg(bb=("bb", "sum"), so=("so", "sum"), hr=("hr", "sum"), pa=("pa", "sum"))
    d["tto_share"] = (d["bb"] + d["so"] + d["hr"]) / d["pa"]
    d[["tto_share"]]
    return


@app.cell
def _(mo, tto):
    mid_century = tto["tto_share"].loc[1946:1960].mean()
    last = tto["tto_share"].loc[2015:].mean()
    peak_year = int(tto["tto_share"].idxmax())
    peak = tto["tto_share"].max()
    mo.md(
        f"""
        ## Finding

        The TTO share held around **{mid_century:.1%}** from the late 1940s
        through 1960, then climbed steadily from the 1990s on to about
        **{last:.1%}** across the last decade, peaking at **{peak:.1%}** in
        {peak_year}. More than a third of modern plate appearances now end
        without the defense touching the ball.
        """
    )
    return


if __name__ == "__main__":
    app.run()
