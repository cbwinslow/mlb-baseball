"""
================================================================================
Checksum and Hashing Utilities
Date: 2026-05-09

File and data integrity verification.
================================================================================
"""

import hashlib
from pathlib import Path
from typing import Optional


def file_checksum(
    path: Path,
    algorithm: str = "sha256",
    chunk_size: int = 8192,
) -> str:
    """Calculate file checksum.

    Args:
        path: File path
        algorithm: Hash algorithm (default: sha256)
        chunk_size: Read chunk size in bytes

    Returns:
        Hex-encoded checksum
    """
    hasher = hashlib.new(algorithm)

    with open(path, "rb") as f:
        while chunk := f.read(chunk_size):
            hasher.update(chunk)

    return hasher.hexdigest()


def string_checksum(
    data: str,
    algorithm: str = "sha256",
) -> str:
    """Calculate string checksum.

    Args:
        data: String data
        algorithm: Hash algorithm (default: sha256)

    Returns:
        Hex-encoded checksum
    """
    return hashlib.new(algorithm, data.encode()).hexdigest()


def verify_checksum(
    path: Path,
    expected: str,
    algorithm: str = "sha256",
) -> bool:
    """Verify file checksum.

    Args:
        path: File path
        expected: Expected checksum
        algorithm: Hash algorithm

    Returns:
        True if checksum matches
    """
    return file_checksum(path, algorithm) == expected
