"""Port of Chadwick's ``src/cwlib/book.c`` (``cw_scorebook_read``) and ``cw_file_find_first_game``.

Chadwick is Copyright (c) 2002-2023 Dr T L Turocy and the Chadwick Baseball
Bureau, licensed GPL-2.0-or-later; this module is a derivative of it and keeps
that notice.
"""

from retrosheetpy.cw.file import CFile, StrTok
from retrosheetpy.cw.game import Game, read_game

COMMENT_BUFSIZE = 256  # ``char buf[256]`` in ``cw_scorebook_read_comments`` and the finder


def _read_comments(file: CFile) -> tuple[bool, list[str]]:
    """``cw_scorebook_read_comments``: leading ``com`` lines. False if the file is empty."""
    tok = StrTok()
    comments: list[str] = []
    while True:
        buf = file.fgets(COMMENT_BUFSIZE)
        if buf is None:
            return False, comments
        kind = tok(buf)
        com = tok(None)
        if kind is not None and kind == "com" and com is not None:
            comments.append(com)
        else:
            return True, comments


def find_first_game(file: CFile) -> bool:
    """``cw_file_find_first_game``: rewind, then stop at the first line that begins ``id``"""
    tok = StrTok()
    file.setpos(0)
    while not file.eof:
        filepos = file.getpos()
        buf = file.fgets(COMMENT_BUFSIZE)
        if buf is None:
            return False
        kind = tok(buf)
        if kind is not None and kind == "id":
            file.setpos(filepos)
            return True
    return False


def scorebook_read(data: bytes) -> list[Game] | None:
    """``cw_scorebook_read``: every game of an event file, or ``None`` where C returns -1.

    ``None`` is the "could not open file" case of ``cwtools_process_scorebook``: an
    empty file.
    """
    file = CFile(data)
    ok, _comments = _read_comments(file)
    if not ok:
        return None
    find_first_game(file)
    games: list[Game] = []
    while not file.eof:
        game = read_game(file)
        if game is None:
            break
        games.append(game)
    return games
