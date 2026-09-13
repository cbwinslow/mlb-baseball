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
        # More strikeouts, fewer runs? Not really.

        League strikeout rate has roughly tripled since 1930. A natural guess is
        that all those strikeouts have suppressed scoring. This recipe checks
        that against the published
        [MLB Research Statistic Backbone](https://huggingface.co/datasets/cbwinslow/mlb-research).

        **Sources:** `batting_season` (`is_combined` rows) for strikeouts and
        plate appearances; `batting_team` for runs and team games. Regular
        season, Retrosheet event-derived, 1910-2025.

        **Method:** `k_pct = sum(so) / sum(pa)` per season; runs per game =
        `sum(team runs) / sum(team games)` per season (each game has two teams,
        so this is runs per team per game). Correlate the two series across
        seasons.
        """
    )
    return


@app.cell
def _(mlb_research):
    batting_season = mlb_research.load("batting_season")
    batting_team = mlb_research.load("batting_team")
    return batting_season, batting_team


@app.cell
def _(batting_season, batting_team):
    k = (
        batting_season[batting_season["is_combined"]]
        .groupby("season")
        .agg(so=("so", "sum"), pa=("pa", "sum"))
    )
    k["k_pct"] = k["so"] / k["pa"]

    runs = batting_team.groupby("season").agg(r=("r", "sum"), g=("g", "sum"))
    runs["runs_per_game"] = runs["r"] / runs["g"]

    trend = k.join(runs, how="inner")
    trend = trend[trend.index >= 1913]
    return (trend,)


@app.cell
def _(mo):
    mo.md("## Selected seasons")
    return


@app.cell
def _(trend):
    trend.loc[[1930, 1968, 1987, 2000, 2019, 2024], ["k_pct", "runs_per_game"]]
    return


@app.cell
def _(mo, trend):
    corr = trend["k_pct"].corr(trend["runs_per_game"])
    y1968 = trend.loc[1968]
    y2019 = trend.loc[2019]
    mo.md(
        f"""
        ## Finding

        Across seasons the correlation between strikeout rate and runs per game
        is only **{corr:+.2f}** -- weakly negative, not the strong link the
        premise assumes. 1968 (the "year of the pitcher") paired a low
        **{y1968.k_pct:.1%}** K rate with a *lower* **{y1968.runs_per_game:.2f}**
        runs per game, while 2019 paired a record **{y2019.k_pct:.1%}** K rate
        with **{y2019.runs_per_game:.2f}** runs per game. Strikeouts are up, but
        the home-run surge has kept scoring near its historical highs.
        """
    )
    return


if __name__ == "__main__":
    app.run()
