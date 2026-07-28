"""Single source of truth for "what connectors exist" — used by both the CLI
and `mlb doctor`. Kept separate from cli.py so doctor.py can depend on it
without importing the CLI module (which itself imports doctor.py)."""

from mlb_baseball.connectors import (
    bref,
    chadwick_register,
    lahman,
    mlb_api,
    retrosheet,
    retrosheet_box,
    retrosheet_event,
    retrosheet_gamelog,
    retrosheet_reference,
    retrosheet_roster,
    retrosheet_schedule,
    retrosheet_transaction,
    statcast,
    statcast_leaderboard,
)

CONNECTORS = {
    "register": chadwick_register,
    "lahman": lahman,
    "mlb_api": mlb_api,
    "retrosheet": retrosheet,
    "retrosheet_box": retrosheet_box,
    "retrosheet_event": retrosheet_event,
    "retrosheet_gamelog": retrosheet_gamelog,
    "retrosheet_reference": retrosheet_reference,
    "retrosheet_roster": retrosheet_roster,
    "retrosheet_schedule": retrosheet_schedule,
    "retrosheet_transaction": retrosheet_transaction,
    "statcast": statcast,
    "statcast_leaderboard": statcast_leaderboard,
    "bref": bref,
}
