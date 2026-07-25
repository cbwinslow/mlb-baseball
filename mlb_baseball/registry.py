"""Single source of truth for "what connectors exist" — used by both the CLI
and `mlb doctor`. Kept separate from cli.py so doctor.py can depend on it
without importing the CLI module (which itself imports doctor.py)."""

from mlb_baseball.connectors import chadwick_register, lahman, retrosheet

CONNECTORS = {
    "register": chadwick_register,
    "lahman": lahman,
    "retrosheet": retrosheet,
}
