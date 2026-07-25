"""Single source of truth for "what connectors exist" — used by both the CLI
and `mlb doctor`. Kept separate from cli.py so doctor.py can depend on it
without importing the CLI module (which itself imports doctor.py)."""

from mlb_baseball.connectors import (
    chadwick_register,
    lahman,
    retrosheet,
    retrosheet_gamelog,
    retrosheet_reference,
)

CONNECTORS = {
    "register": chadwick_register,
    "lahman": lahman,
    "retrosheet": retrosheet,
    "retrosheet_gamelog": retrosheet_gamelog,
    "retrosheet_reference": retrosheet_reference,
}
