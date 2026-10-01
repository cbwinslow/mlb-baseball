"""Structured errors raised by retrosheetpy."""


class RetrosheetError(Exception):
    """Base class for all retrosheetpy errors."""


class IntegrityError(RetrosheetError):
    """A cached file's bytes no longer match its recorded SHA-256."""


class InvalidArchiveError(RetrosheetError):
    """A download or file is not a valid zip archive."""


class UnsafeArchiveMemberError(RetrosheetError):
    """A zip member name would escape the archive (absolute path or '..')."""


class ParseError(RetrosheetError):
    """A source line could not be parsed. Carries enough to find it again."""

    def __init__(
        self,
        message: str,
        *,
        stage: str,
        source: str,
        line_no: int,
        game_id: str | None,
        record_type: str,
        raw: str,
        token: str | None = None,
        offset: int | None = None,
    ):
        where = f" at offset {offset} ({token!r})" if offset is not None else ""
        super().__init__(f"{source}:{line_no} [{stage}] {message}{where}: {raw!r}")
        self.message = message
        self.stage = stage
        self.source = source
        self.line_no = line_no
        self.game_id = game_id
        self.record_type = record_type
        self.raw = raw
        self.token = token  # the offending piece of ``raw``, when known
        self.offset = offset  # its character offset inside ``raw``, when known
