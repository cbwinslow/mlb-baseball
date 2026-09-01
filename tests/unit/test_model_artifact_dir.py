"""``provenance.models_dir`` must resolve to the PRIMARY git checkout's
``models/`` directory, never a linked worktree's. Model artifacts are
referenced by absolute path in the shared ``meta.model`` table, so a
worktree that trained a model and was then removed would orphan the row
(issue #108)."""

import subprocess
from pathlib import Path

import pytest

from mlb_baseball.model import provenance

_PACKAGE_MODELS = Path(provenance.__file__).resolve().parent.parent.parent / "models"


@pytest.fixture(autouse=True)
def _clear_models_dir_cache():
    """models_dir is @functools.cache'd; each test starts from a cold cache."""
    provenance.models_dir.cache_clear()
    yield
    provenance.models_dir.cache_clear()


def test_models_dir_matches_the_primary_git_common_dir_even_from_a_worktree():
    """This suite itself runs from a linked worktree in development. The
    result must still be ``<primary checkout>/models`` -- the parent of the
    primary ``.git`` that ``--git-common-dir`` reports -- not
    ``<this worktree>/models``. That is the whole #108 fix.
    """
    common = subprocess.run(
        ["git", "rev-parse", "--path-format=absolute", "--git-common-dir"],
        capture_output=True,
        text=True,
        check=True,
        cwd=Path(provenance.__file__).resolve().parent,
    ).stdout.strip()
    resolved = provenance.models_dir()
    assert resolved == Path(common).resolve().parent / "models"
    assert resolved.name == "models"
    assert ".git" not in resolved.parts


def test_models_dir_falls_back_to_package_root_when_git_is_missing(monkeypatch):
    monkeypatch.setattr(
        provenance.subprocess,
        "run",
        lambda *a, **k: (_ for _ in ()).throw(FileNotFoundError("git")),
    )
    assert provenance.models_dir() == _PACKAGE_MODELS


def test_models_dir_falls_back_when_git_rev_parse_fails(monkeypatch):
    class _Result:
        returncode = 128
        stdout = ""

    monkeypatch.setattr(provenance.subprocess, "run", lambda *a, **k: _Result())
    assert provenance.models_dir() == _PACKAGE_MODELS


def test_models_dir_falls_back_when_git_call_times_out(monkeypatch):
    def _timeout(*a, **k):
        raise subprocess.TimeoutExpired(cmd="git", timeout=10)

    monkeypatch.setattr(provenance.subprocess, "run", _timeout)
    assert provenance.models_dir() == _PACKAGE_MODELS


def test_gbm_total_stack_all_use_the_shared_models_dir():
    from mlb_baseball.model import gbm, stack, total

    shared = provenance.models_dir()
    assert gbm.MODEL_DIR == shared
    assert total.MODEL_DIR == shared
    assert stack.MODEL_DIR == shared
