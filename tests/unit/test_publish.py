"""Unit tests for the Hugging Face Datasets publish step (delivery-surface)."""

import pytest

from mlb_baseball import publish


class _FakeHfApi:
    """Records __init__/upload_folder calls without touching the network."""

    calls: list[tuple[str, object]] = []

    def __init__(self, token=None):
        _FakeHfApi.calls.append(("__init__", token))

    def upload_folder(self, **kwargs):
        _FakeHfApi.calls.append(("upload_folder", kwargs))
        return "https://huggingface.co/datasets/cbwinslow/mlb-research/commit/abc123"


@pytest.fixture(autouse=True)
def _reset_fake_calls():
    _FakeHfApi.calls = []
    yield


def _make_valid_bundle(tmp_path):
    """A bundle directory shaped exactly like export_backbone_bundle()'s output."""
    bundle_dir = tmp_path / "backbone_bundle"
    (bundle_dir / "data").mkdir(parents=True)
    (bundle_dir / "manifest.json").write_text("{}", encoding="utf-8")
    (bundle_dir / "README.md").write_text("# card", encoding="utf-8")
    return bundle_dir


def test_publish_backbone_bundle_passes_folder_repo_type_and_revision(monkeypatch, tmp_path):
    """Verify upload_folder receives the bundle path, repo_type=dataset, and the
    given tag as revision (task 2.2)."""
    monkeypatch.setenv("HF_TOKEN", "hf_super_secret_token")
    monkeypatch.setattr("huggingface_hub.HfApi", _FakeHfApi, raising=False)

    bundle_dir = _make_valid_bundle(tmp_path)

    result = publish.publish_backbone_bundle(bundle_dir, tag="v0.1.0")

    assert result == "https://huggingface.co/datasets/cbwinslow/mlb-research/commit/abc123"
    init_call, upload_call = _FakeHfApi.calls
    assert init_call == ("__init__", "hf_super_secret_token")
    assert upload_call == (
        "upload_folder",
        {
            "folder_path": str(bundle_dir),
            "repo_id": "cbwinslow/mlb-research",
            "repo_type": "dataset",
            "revision": "v0.1.0",
        },
    )


def test_publish_backbone_bundle_accepts_custom_repo_id(monkeypatch, tmp_path):
    monkeypatch.setenv("HF_TOKEN", "hf_super_secret_token")
    monkeypatch.setattr("huggingface_hub.HfApi", _FakeHfApi, raising=False)

    bundle_dir = _make_valid_bundle(tmp_path)
    publish.publish_backbone_bundle(bundle_dir, tag="v0.1.0", repo_id="someorg/mlb-research")

    _, upload_call = _FakeHfApi.calls
    assert upload_call[1]["repo_id"] == "someorg/mlb-research"


def test_publish_backbone_bundle_requires_hf_token(monkeypatch, tmp_path):
    monkeypatch.delenv("HF_TOKEN", raising=False)

    bundle_dir = _make_valid_bundle(tmp_path)
    with pytest.raises(RuntimeError, match="HF_TOKEN is not set"):
        publish.publish_backbone_bundle(bundle_dir, tag="v0.1.0")


def test_publish_backbone_bundle_never_logs_the_token(monkeypatch, tmp_path, caplog):
    """The token must not appear in any log record emitted by the publish step."""
    monkeypatch.setenv("HF_TOKEN", "hf_super_secret_token")
    monkeypatch.setattr("huggingface_hub.HfApi", _FakeHfApi, raising=False)

    bundle_dir = _make_valid_bundle(tmp_path)
    with caplog.at_level("DEBUG"):
        publish.publish_backbone_bundle(bundle_dir, tag="v0.1.0")

    for record in caplog.records:
        assert "hf_super_secret_token" not in record.getMessage()


def test_publish_backbone_bundle_missing_huggingface_hub(monkeypatch, tmp_path):
    """Verify a clear error when huggingface_hub isn't installed."""
    monkeypatch.setenv("HF_TOKEN", "hf_super_secret_token")
    import builtins

    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "huggingface_hub":
            raise ImportError("No module named 'huggingface_hub'")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)

    bundle_dir = _make_valid_bundle(tmp_path)
    with pytest.raises(RuntimeError, match="Publishing requires huggingface_hub"):
        publish.publish_backbone_bundle(bundle_dir, tag="v0.1.0")


def test_publish_backbone_bundle_rejects_unexpected_files(monkeypatch, tmp_path):
    """upload_folder() uploads bundle_dir recursively with no filtering -- an
    --out pointed at the wrong directory (unrelated files, or a whole repo
    checkout) must be refused, not partially published."""
    monkeypatch.setenv("HF_TOKEN", "hf_super_secret_token")
    monkeypatch.setattr("huggingface_hub.HfApi", _FakeHfApi, raising=False)

    bundle_dir = _make_valid_bundle(tmp_path)
    (bundle_dir / "unrelated_secret.txt").write_text("oops", encoding="utf-8")

    with pytest.raises(RuntimeError, match="unexpected entries"):
        publish.publish_backbone_bundle(bundle_dir, tag="v0.1.0")
    assert _FakeHfApi.calls == []


def test_publish_backbone_bundle_does_not_inspect_data_dir_contents(monkeypatch, tmp_path):
    """publish_backbone_bundle only validates the bundle's top-level shape --
    it trusts export_backbone_bundle's own rmtree-before-write (export.py) to
    keep data/ free of stale excluded-table files. This documents that
    boundary rather than duplicating the check here."""
    monkeypatch.setenv("HF_TOKEN", "hf_super_secret_token")
    monkeypatch.setattr("huggingface_hub.HfApi", _FakeHfApi, raising=False)

    bundle_dir = _make_valid_bundle(tmp_path)
    (bundle_dir / "data" / "player_season.parquet").write_bytes(b"stale")

    publish.publish_backbone_bundle(bundle_dir, tag="v0.1.0")
    assert len(_FakeHfApi.calls) == 2


def test_publish_backbone_bundle_rejects_missing_manifest(monkeypatch, tmp_path):
    monkeypatch.setenv("HF_TOKEN", "hf_super_secret_token")
    monkeypatch.setattr("huggingface_hub.HfApi", _FakeHfApi, raising=False)

    bundle_dir = tmp_path / "empty_bundle"
    bundle_dir.mkdir()

    with pytest.raises(RuntimeError, match="no manifest.json found"):
        publish.publish_backbone_bundle(bundle_dir, tag="v0.1.0")
    assert _FakeHfApi.calls == []
