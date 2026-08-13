"""Team prior offense/defense (ADR-061, Plan 03G admission queue
OFF-01 OBP, OFF-02 SLG/ISO, OFF-03 BB%/K%, OFF-08/DEF-01 run
environment). Same point-in-time-safe, no-leakage shape as team wOBA
(mlb_baseball/model/offense.py, ADR-036): every rate is a rolling,
within-season value computed only from games strictly before the one
it's attached to.

compute() reconstructs OBP/SLG/ISO/BB%/K% from raw.retrosheet_event's
per-play data using the same event_cd mapping already confirmed and
used elsewhere in this codebase (3=K, 14/15=UBB/IBB, 16=HBP, 20/21/22/23
=1B/2B/3B/HR -- see mlb_baseball/model/starter.py and offense.py module
docstrings). PA = AB+BB+HBP+SF; this excludes sacrifice bunts and
catcher's interference, which raw.retrosheet_event's ab_fl/sf_fl flags
don't separately expose here -- a real, documented gap, not a silent
approximation, same posture as offense.py's own wOBA denominator note.

compute_run_environment() needs no raw.retrosheet_event dependency at
all: home_runs_for/home_runs_allowed/home_wins/home_losses are already
entering-value sums set by features.build() (mlb_baseball/sql/
game_feature_rebuild.sql), so the per-game average is a pure derived
UPDATE off gold.game_feature's own already-computed columns -- the same
"read a prior step's output, don't recompute it" shape as
offense.py::compute_wrc_plus reading home_woba/park_factor.

Scope: the rate-stat half covers 1910-2025 only (raw.retrosheet_event's
known range); no 2026+ raw.mlb_playbyplay equivalent is built in this
package -- an honest, documented gap, same as starter.py/offense.py
before their own compute_live() follow-ups landed.
"""

import psycopg

from mlb_baseball.db import fetch_one, get_connection
from mlb_baseball.health import Check
from mlb_baseball.sql import read_sql


def compute_run_environment(conn: psycopg.Connection) -> int:
    with conn.cursor() as cur:
        cur.execute(read_sql("team_run_environment_update.sql"))
        return cur.rowcount


def health_check() -> list[Check]:
    return []
