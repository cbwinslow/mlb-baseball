"""``provenance.models_dir`` must resolve to the PRIMARY git checkout's
``models/`` directory, never a linked worktree's. Model artifacts are
referenced by absolute path in the shared ``meta.model`` table, so a
worktree that trained a model and was then removed would orphan the row
(issue #108)."""

from pathlib import Path

from mlb_baseball.model import provenance


def test_models_dir_resolves_outside_any_git_worktree():
    d = provenance.models_dir()
    assert d.name == "models"
    assert "worktrees" not in d.parts, d
    assert ".git" not in d.parts, d


def test_models_dir_falls_back_to_package_root_when_git_is_unavailable(monkeypatch):
    def _no_git(*args, **kwargs):
        raise FileNotFoundError("git")

    monkeypatch.setattr(provenance.subprocess, "run", _no_git)
    d = provenance.models_dir()
    assert d == Path(provenance.__file__).resolve().parent.parent.parent / "models"


def test_models_dir_falls_back_when_git_rev_parse_fails(monkeypatch):
    class _Result:
        returncode = 128
        stdout = ""

    monkeypatch.setattr(provenance.subprocess, "run", lambda *a, **k: _Result())
    d = provenance.models_dir()
    assert d == Path(provenance.__file__).resolve().parent.parent.parent / "models"


def test_gbm_total_stack_all_use_the_shared_models_dir():
    from mlb_baseball.model import gbm, stack, total

    shared = provenance.models_dir()
    assert gbm.MODEL_DIR == shared
    assert total.MODEL_DIR == shared
    assert stack.MODEL_DIR == shared
