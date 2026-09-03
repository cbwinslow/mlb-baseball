"""Hugging Face Datasets publish step for the backbone export bundle.

The bundle directory produced by ``mlb_baseball.export.export_backbone_bundle``
is already laid out as a Hugging Face dataset repo (``data/<table>.parquet``,
``manifest.json``, ``README.md``) -- this module only uploads it. First runs
are owner-run locally (see ``docs/PUBLIC_API.md``); an automated tag-triggered
workflow is a follow-up change, not built here (design.md D3).
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)

DEFAULT_REPO_ID = "cbwinslow/mlb-research"

# The exact top-level shape export_backbone_bundle() writes. upload_folder()
# uploads bundle_dir recursively with no filtering -- validating this shape
# first means an --out pointed at the wrong directory (one with unrelated
# files, or a whole repo checkout) is refused rather than partially published.
_EXPECTED_BUNDLE_ENTRIES = frozenset({"data", "manifest.json", "README.md"})


def _validate_bundle_shape(bundle_dir: Path) -> None:
    if not bundle_dir.is_dir():
        raise RuntimeError(f"Refusing to publish {bundle_dir}: not a directory")
    actual = {p.name for p in bundle_dir.iterdir()}
    unexpected = actual - _EXPECTED_BUNDLE_ENTRIES
    if unexpected:
        raise RuntimeError(
            f"Refusing to publish {bundle_dir}: unexpected entries {sorted(unexpected)} -- "
            "only data/, manifest.json, and README.md are expected in a backbone bundle. "
            "Use a dedicated --out directory produced by `mlb export --preset backbone`, "
            "not one containing other files."
        )
    if not (bundle_dir / "manifest.json").is_file():
        raise RuntimeError(f"Refusing to publish {bundle_dir}: no manifest.json found")


def publish_backbone_bundle(
    bundle_dir: Path | str,
    *,
    tag: str,
    repo_id: str = DEFAULT_REPO_ID,
) -> str:
    """Upload a backbone export bundle to a Hugging Face Datasets repo.

    The write credential is read from the ``HF_TOKEN`` environment variable
    only -- never a function parameter or CLI flag, so it can't end up in a
    process's argv or an argparse namespace repr. Never logged. Returns the
    commit URL huggingface_hub reports for the upload.

    Refuses to publish a directory that doesn't look like a backbone bundle
    (``_validate_bundle_shape``) -- ``upload_folder`` uploads everything under
    ``bundle_dir`` with no filtering, so a wrong ``--out`` could otherwise
    publish unrelated files.
    """
    bundle_path = Path(bundle_dir)
    _validate_bundle_shape(bundle_path)

    try:
        from huggingface_hub import HfApi
    except ImportError:
        raise RuntimeError(
            "Publishing requires huggingface_hub. "
            "Install with `pip install 'mlb-baseball[export]'` or `uv sync --extra export`."
        ) from None

    token = os.environ.get("HF_TOKEN")
    if not token:
        raise RuntimeError(
            "HF_TOKEN is not set. Run as `HF_TOKEN=... mlb export --preset backbone "
            "--publish hf --tag <tag>` (never `export HF_TOKEN=...`, which leaves it in "
            "shell history and every later command's environment)."
        )

    logger.info("Publishing %s to %s (revision=%s)", bundle_dir, repo_id, tag)
    api = HfApi(token=token)
    # upload_folder() assumes the repo already exists; create_repo(exist_ok=True)
    # is a no-op against an existing repo and creates a fresh public one
    # otherwise -- this is the first publish, so the repo doesn't exist yet.
    api.create_repo(repo_id=repo_id, repo_type="dataset", exist_ok=True, private=False)
    commit_info = api.upload_folder(
        folder_path=str(bundle_dir),
        repo_id=repo_id,
        repo_type="dataset",
        revision=tag,
    )
    return str(commit_info)
