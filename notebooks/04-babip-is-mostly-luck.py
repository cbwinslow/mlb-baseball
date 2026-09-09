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
        # BABIP is mostly luck; strikeout rate is mostly skill

        A batter's rate stats bounce around year to year. Some of that bounce is
        real change in the player; some is noise. One way to tell them apart:
        how well does this year's value predict next year's? A stat that a
        batter "owns" correlates strongly with itself across seasons; a
        noise-dominated stat does not.

        This recipe compares **BABIP** (batting average on balls in play) with
        **strikeout rate** using the published
        [MLB Research Statistic Backbone](https://huggingface.co/datasets/cbwinslow/mlb-research).

        **Source:** `batting_season`, `is_combined` rows, qualified seasons
        (`pa >= 400`). Regular season, Retrosheet event-derived, 1910-2025.

        **Method:** pair each qualified player-season with that same player's
        next qualified season, then take the Pearson correlation of the stat
        across the pair. Both `babip` and `k_pct` are already recomputed from
        summed components in the backbone.
        """
    )
    return


@app.cell
def _(mlb_research):
    batting_season = mlb_research.load("batting_season")
    return (batting_season,)


@app.cell
def _(batting_season, pd):
    qualified = batting_season[batting_season["is_combined"] & (batting_season["pa"] >= 400)][
        ["player_id", "season", "babip", "k_pct"]
    ].dropna()

    year0 = qualified.rename(columns={"season": "s0", "babip": "babip_y0", "k_pct": "k_pct_y0"})
    year0["s1"] = year0["s0"] + 1
    year1 = qualified.rename(columns={"season": "s1", "babip": "babip_y1", "k_pct": "k_pct_y1"})
    pairs = year0.merge(year1, on=["player_id", "s1"])
    return (pairs,)


@app.cell
def _(mo, pairs):
    mo.md(f"Paired **{len(pairs):,}** consecutive qualified player-seasons.")
    return


@app.cell
def _(pairs, pd):
    pd.DataFrame(
        {
            "stat": ["BABIP", "strikeout rate (K%)"],
            "year-to-year correlation": [
                pairs["babip_y0"].corr(pairs["babip_y1"]),
                pairs["k_pct_y0"].corr(pairs["k_pct_y1"]),
            ],
        }
    )
    return


@app.cell
def _(mo, pairs):
    babip_r = pairs["babip_y0"].corr(pairs["babip_y1"])
    k_r = pairs["k_pct_y0"].corr(pairs["k_pct_y1"])
    mo.md(
        f"""
        ## Finding

        A batter's strikeout rate predicts itself the next year with a
        correlation of **{k_r:.2f}** -- it is close to a fixed skill. BABIP
        predicts itself at only **{babip_r:.2f}**: roughly half of a single
        season's BABIP is noise that will not carry forward. This is why
        projection systems regress a hitter's BABIP hard toward league and
        batted-ball expectations, but take their strikeout rate almost at face
        value.
        """
    )
    return


if __name__ == "__main__":
    app.run()
