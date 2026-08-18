"""log5 -- the simplest defensible win-probability baseline (see
docs/RESEARCH.md). No training step: two win percentages in, one
probability out. First model in the build order (ADR-032) specifically
because it proves gold.game_feature -> gold.prediction end to end before
anything more complex.
"""

from decimal import Decimal

import psycopg

from mlb_baseball.health import Check, check_table_has_rows
from mlb_baseball.model import provenance

MODEL_VERSION = "log5-v2"


def probability(home_win_pct: Decimal, away_win_pct: Decimal) -> Decimal:
    """P(home wins) = home(1-away) / [home(1-away) + away(1-home)] --
    Bill James's log5, independently re-derived by a SABR paper and
    validated at 97.9% efficiency across 204,858 MLB games, 1871-2013
    (see docs/RESEARCH.md). The defining property the SABR article
    requires of this function is P(x, .500) == x -- a team with winning
    percentage x must get win probability x against a .500 team. This
    odds-ratio form satisfies that identically; the previously shipped
    home^2/(home^2+away^2) form does not (e.g. it returns .5902, not
    .600, for a .600 team against a .500 team) and was never actually
    the cited formula -- log5-v1's predictions are known-invalid, kept
    as historical record rather than silently relabeled.

    Undefined (0/0) when both inputs are equal AND at one of the two
    extremes (both exactly 0, or both exactly 1) -- found both are real,
    not hypothetical: two genuine winless-so-far teams (2018/2020 samples,
    0-2 and 0-1) and two genuine still-undefeated teams (2019/2020/2023
    samples, up to 4-0) matched against each other, all in real production
    gold.game_feature data. Both explicitly return 0.5 -- the same answer
    the formula already gives for two *equal* teams at every other winning
    percentage (verified: probability(x, x) == 0.5 for every x strictly
    between 0 and 1), so this is the limiting value the formula is
    degenerate at in both cases, not an arbitrary guess."""
    if home_win_pct == away_win_pct and home_win_pct in (Decimal("0"), Decimal("1")):
        return Decimal("0.5")
    home_term = home_win_pct * (1 - away_win_pct)
    away_term = away_win_pct * (1 - home_win_pct)
    return home_term / (home_term + away_term)


def predict(conn: psycopg.Connection) -> int:
    # Scoped to home_win IS NULL -- games not yet decided. Without this,
    # every daily run would re-predict all 227K+ already-final historical
    # games forever, not just the handful of upcoming ones a daily cron
    # actually needs (see migration 0013's history-preserving design: this
    # scope is what makes "re-run as game day approaches" cheap instead of
    # unbounded). One-time backtesting against already-decided historical
    # games is deliberately separate, future work -- not this function.
    #
    # mlb_game_pk IS NOT NULL: gold.prediction.mlb_game_pk is NOT NULL (see
    # migration 0014) -- every still-undecided game came from raw.mlb_
    # schedule (see features.py) and so always has one, but this guards the
    # rare case of an old, incomplete historical game with a missing score
    # and no resolved game_pk (e.g. a suspended game never resumed).
    #
    # Also requires both teams to have at least one prior game this season
    # (home_win_pct/away_win_pct both non-NULL) -- log5 has no sensible
    # answer for a team's own season opener, see probability()'s docstring.
    #
    # This raw SQL formula (not probability() itself -- an INSERT ... SELECT
    # can't call back into Python per row) hits the same 0/0 degenerate case
    # probability() now guards: both teams equal at exactly 0 or exactly 1.
    # A found-in-production real bug: the original exclusion only handled
    # (0,0), never (1,1) -- an undefeated-vs-undefeated matchup would have
    # aborted this entire INSERT with a division error, silently blocking
    # every other still-undecided game's prediction in the same run. Both
    # degenerate rows are excluded here (not computed as 0.5 inline) to
    # match this function's pre-existing (0,0) design -- skip, not guess.
    model_id = provenance.register_model(
        conn,
        name="log5",
        target="home_win",
        model_version=MODEL_VERSION,
        feature_set_version="game-feature-v1",
        status="baseline",
        parameters={"formula": "home*(1-away)/(home*(1-away)+away*(1-home))"},
    )
    data_cutoff, feature_snapshot_id = provenance.feature_snapshot(
        conn, where="home_win IS NULL AND mlb_game_pk IS NOT NULL"
    )
    run_id = provenance.start_run(
        conn,
        run_type="predict",
        model_id=model_id,
        data_cutoff=data_cutoff,
        source_snapshot=feature_snapshot_id,
        feature_snapshot_id=feature_snapshot_id,
    )
    try:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO gold.prediction "
                "(mlb_game_pk, game_instance_key, model_version, home_win_prob, model_id, "
                "model_run_id, "
                "data_cutoff, feature_snapshot_id) "
                "SELECT mlb_game_pk, game_instance_key, %s, "
                "  (home_win_pct * (1 - away_win_pct)) "
                "  / (home_win_pct * (1 - away_win_pct) + away_win_pct * (1 - home_win_pct)) "
                ", %s, %s, %s, %s "
                "FROM gold.game_feature "
                "WHERE home_win IS NULL AND mlb_game_pk IS NOT NULL "
                "  AND home_win_pct IS NOT NULL AND away_win_pct IS NOT NULL "
                "  AND NOT (home_win_pct = away_win_pct AND home_win_pct IN (0, 1))",
                (MODEL_VERSION, model_id, run_id, data_cutoff, feature_snapshot_id),
            )
            inserted = cur.rowcount
        provenance.finish_run(conn, run_id)
        return inserted
    except Exception as error:
        provenance.finish_run(conn, run_id, error=error)
        raise


def health_check() -> list[Check]:
    return [check_table_has_rows("gold.prediction")]
