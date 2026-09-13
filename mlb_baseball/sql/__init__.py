"""Named SQL resources used by Python orchestration.

Stable set-based transformations live as reviewable ``.sql`` files. Python
owns only parameters, transactions, and sequencing until a SQLMesh model has
passed its promotion gate.
"""

from importlib.resources import files


def read_sql(name: str) -> str:
    """Return one packaged SQL resource, rejecting traversal-like names.

    Accepts a bare filename (``park_factor_update.sql``) or exactly one
    leading subdirectory segment (``duckdb/feat_player_form.sql`` -- the
    DuckDB-dialect feature builds run by ``mlb_baseball.feat``). Rejects a
    second separator, ``..``, an absolute path, and any dot-prefixed segment.
    """
    parts = name.split("/")
    if (
        "\\" in name
        or name.startswith("/")
        or len(parts) > 2
        or any(part in ("", "..") or part.startswith(".") for part in parts)
    ):
        raise ValueError(f"invalid SQL resource name: {name!r}")
    resource = files(__package__)
    for part in parts:
        resource = resource.joinpath(part)
    return resource.read_text(encoding="utf-8")
