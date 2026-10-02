"""Port of Chadwick's game sanity checks (``src/cwlib/lint.c``).

Chadwick is Copyright (c) 2002-2023 Dr T L Turocy and the Chadwick Baseball
Bureau, licensed GPL-2.0-or-later; this module is a derivative of it and keeps
that notice. Names map onto the C functions (``cw_game_lint`` -> ``game_lint``).
The messages Chadwick prints to stderr go to ``logging`` ("retrosheetpy.cw"),
one record per ``fprintf`` line, text identical to the C.
"""

import logging

from retrosheetpy.cw.game import Game
from retrosheetpy.cw.gameiter import GameIter
from retrosheetpy.cw.parse import outs_on_play, runner_put_out

log = logging.getLogger("retrosheetpy.cw")


def _game_lint_starters(game: Game) -> bool:
    """``cw_game_lint_starters``"""
    ok = True
    for app in game.starters:
        if app.slot < 0 or app.slot > 9:
            log.error(
                "ERROR: In %s, invalid slot %d for player '%s'.",
                game.game_id,
                app.slot,
                app.player_id,
            )
            ok = False
        if app.team < 0 or app.team > 1:
            log.error(
                "ERROR: In %s, invalid team %d for player '%s'.",
                game.game_id,
                app.team,
                app.player_id,
            )
            ok = False
        if app.pos < 1 or app.pos > 10:
            log.error(
                "ERROR: In %s, invalid position %d for player '%s'.",
                game.game_id,
                app.pos,
                app.player_id,
            )
            ok = False
    return ok


def _play_error(gi: GameIter, what: str) -> None:
    """The two-line ``Play-by-play error`` header plus its detail line (the detail
    text ends with ``(event "...", ... batting)`` in every case)."""
    ev = gi.event
    assert ev is not None
    log.error(
        "Play-by-play error in game %s at event %d:", gi.game.game_id, gi.state.event_count + 1
    )
    log.error('%s (event "%s", %s batting)', what, ev.event_text, ev.batter)


def _game_lint_state(gi: GameIter) -> bool:
    """``cw_game_lint_state``"""
    ok = True
    ev = gi.event
    assert ev is not None
    d = gi.data
    state = gi.state

    if not gi.parse_ok:
        log.error("Parse error in game %s at event %d:", gi.game.game_id, state.event_count + 1)
        log.error('Invalid play string "%s" (%s batting)', ev.event_text, ev.batter)
        ok = False

    if d.dp_flag and outs_on_play(d) < 2:
        _play_error(gi, "Fewer than two outs on play marked DP")
        ok = False

    if d.tp_flag and outs_on_play(d) < 3:
        _play_error(gi, "Fewer than three outs on play marked TP")
        ok = False

    for src in range(1, 4):
        if not state.base_occupied(src) and (d.advance[src] != 0 or runner_put_out(d, src)):
            _play_error(gi, f"Advancement from empty base {src}")
            ok = False

    for dest in range(1, 4):
        if not state.base_occupied(dest):
            continue
        for src in range(dest):
            src_adv = d.advance[src]
            dest_adv = d.advance[dest]
            if (
                src_adv >= dest_adv
                and not runner_put_out(d, dest)
                and dest_adv < 4
                and state.outs + outs_on_play(d) < 3
            ):
                _play_error(gi, f"Runner on {dest} overtaken by runner on {src}")
                ok = False
    return ok


def game_lint(game: Game) -> bool:
    """``cw_game_lint``: examine a game for internal consistency."""
    gi = GameIter(game)
    ok = _game_lint_starters(game)
    while ok and gi.event is not None:
        if gi.event.event_text != "NP":
            ok = _game_lint_state(gi) and ok
        gi.next()
    return ok
