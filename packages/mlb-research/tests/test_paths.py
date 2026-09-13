"""Resolver precedence for the local DuckDB feature database
(feature-store-v1, task 2.1). Standalone: no mlb_baseball, no database.
"""

from pathlib import Path

from mlb_research.paths import DEFAULT_PATH, ENV_VAR, resolve_db_path


def test_explicit_path_wins_over_env_and_default(monkeypatch, tmp_path):
    monkeypatch.setenv(ENV_VAR, str(tmp_path / "from_env.duckdb"))
    explicit = tmp_path / "explicit" / "chosen.duckdb"
    assert resolve_db_path(explicit) == explicit.resolve()


def test_env_var_wins_over_default(monkeypatch, tmp_path):
    target = tmp_path / "env" / "mlb.duckdb"
    monkeypatch.setenv(ENV_VAR, str(target))
    assert resolve_db_path() == target.resolve()


def test_default_is_dot_mlb_when_nothing_set(monkeypatch, tmp_path):
    monkeypatch.delenv(ENV_VAR, raising=False)
    fake_home = tmp_path / "home"
    monkeypatch.setattr(Path, "home", staticmethod(lambda: fake_home))
    # DEFAULT_PATH was computed at import time from the real home; the resolver
    # must recompute against the patched home.
    import importlib

    import mlb_research.paths as paths_mod

    importlib.reload(paths_mod)
    try:
        assert paths_mod.resolve_db_path() == (fake_home / ".mlb" / "mlb.duckdb").resolve()
    finally:
        importlib.reload(paths_mod)


def test_parent_directory_is_created_on_first_use(tmp_path):
    target = tmp_path / "brand" / "new" / "dir" / "mlb.duckdb"
    assert not target.parent.exists()
    resolved = resolve_db_path(target)
    assert resolved.parent.is_dir()
    assert not resolved.exists()  # the file itself is the build's job


def test_tilde_in_explicit_path_is_expanded(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    assert resolve_db_path("~/x.duckdb") == (tmp_path / "x.duckdb").resolve()


def test_default_path_constant_points_at_dot_mlb():
    assert DEFAULT_PATH.name == "mlb.duckdb"
    assert DEFAULT_PATH.parent.name == ".mlb"
