"""Pure-Python Retrosheet client and parser."""

from retrosheetpy.artifact import Artifact
from retrosheetpy.catalog import Product, Resource, resolve
from retrosheetpy.client import Client, iter_zip_members
from retrosheetpy.errors import (
    IntegrityError,
    InvalidArchiveError,
    ParseError,
    RetrosheetError,
    UnsafeArchiveMemberError,
)
from retrosheetpy.records import (
    AdjustmentRecord,
    CommentRecord,
    DataRecord,
    IdRecord,
    InfoRecord,
    LineupRecord,
    PlayRecord,
    Record,
    RecordStats,
    StartRecord,
    SubRecord,
    UnsupportedRecord,
    VersionRecord,
    is_event_filename,
    iter_event_zip,
    iter_records,
    read_event_file,
)

__version__ = "0.0.1"

__all__ = [
    "AdjustmentRecord",
    "CommentRecord",
    "DataRecord",
    "IdRecord",
    "InfoRecord",
    "LineupRecord",
    "ParseError",
    "PlayRecord",
    "Record",
    "RecordStats",
    "StartRecord",
    "SubRecord",
    "UnsupportedRecord",
    "VersionRecord",
    "is_event_filename",
    "iter_event_zip",
    "iter_records",
    "read_event_file",
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
