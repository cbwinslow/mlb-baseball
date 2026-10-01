"""Pure-Python Retrosheet client and parser."""

from retrosheetpy.artifact import Artifact
from retrosheetpy.catalog import Product, Resource, resolve
from retrosheetpy.client import Client, iter_zip_members
from retrosheetpy.errors import (
    IntegrityError,
    InvalidArchiveError,
    RetrosheetError,
    UnsafeArchiveMemberError,
)

__version__ = "0.0.1"

__all__ = [
    "Artifact",
    "Client",
    "IntegrityError",
    "InvalidArchiveError",
    "Product",
    "Resource",
    "RetrosheetError",
    "UnsafeArchiveMemberError",
    "__version__",
    "iter_zip_members",
    "resolve",
]
