
"""
================================================================================
File Utilities
Date: 2026-05-09

Shared file handling for all sources.
================================================================================
"""

import json
import tempfile
from pathlib import Path
from typing import Any, Optional

import pandas as pd


def save_json(
    data: Any,
    path: Path,
    pretty: bool = True,
) -> None:
    """Save data to JSON file.

    Args:
        data: Data to save
        path: Output file path
        pretty: Pretty-print JSON (default: True)
    """
    path.parent.mkdir(parents=True, exist_ok=True)

    with open(path, 'w') as f:
        json.dump(
            data,
            f,
            indent=2 if pretty else None,
            default=str,
        )


def save_csv(
    df: pd.DataFrame,
    path: Path,
) -> None:
    """Save DataFrame to CSV file.

    Args:
        df: DataFrame to save
        path: Output file path
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False)


def load_json(path: Path) -> Any:
    """Load JSON file.

    Args:
        path: File path

    Returns:
        Parsed JSON data
    """
    with open(path) as f:
        return json.load(f)


def load_csv(path: Path) -> pd.DataFrame:
    """Load CSV file to DataFrame.

    Args:
        path: File path

    Returns:
        DataFrame
    """
    return pd.read_csv(path)


def get_temp_file(suffix: str = '.tmp') -> Path:
    """Get temporary file path.

    Args:
        suffix: File suffix

    Returns:
        Temporary file path
    """
    return Path(tempfile.gettempdir()) / f'baseball_{Path(tempfile.mktemp()).name}{suffix}'