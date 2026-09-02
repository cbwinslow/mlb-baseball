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
    """
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
    commit_info = HfApi(token=token).upload_folder(
        folder_path=str(bundle_dir),
        repo_id=repo_id,
        repo_type="dataset",
        revision=tag,
    )
    return str(commit_info)
