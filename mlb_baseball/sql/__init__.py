"""Named SQL resources used by Python orchestration.

Stable set-based transformations live as reviewable ``.sql`` files. Python
owns only parameters, transactions, and sequencing until a SQLMesh model has
passed its promotion gate.
"""

from importlib.resources import files


def read_sql(name: str) -> str:
    """Return one packaged SQL resource, rejecting traversal-like names."""
    if "/" in name or "\\" in name or name.startswith("."):
        raise ValueError(f"invalid SQL resource name: {name!r}")
    return files(__package__).joinpath(name).read_text(encoding="utf-8")
