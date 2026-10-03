"""Port of Chadwick's ``src/cwlib/book.c`` (``cw_scorebook_read``) and ``cw_file_find_first_game``.

Chadwick is Copyright (c) 2002-2023 Dr T L Turocy and the Chadwick Baseball
Bureau, licensed GPL-2.0-or-later; this module is a derivative of it and keeps
that notice.
"""

from collections.abc import Callable, Iterator
from dataclasses import dataclass, field

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


def _strcmp(a: str | None, b: str | None) -> int:
    """``strcmp``, which crashes in C on a NULL argument"""
    if a is None or b is None:
        raise ValueError("NULL string passed to strcmp (Chadwick would crash)")
    return (a > b) - (a < b)


@dataclass
class Scorebook:
    """``CWScorebook``: the leading comments of an event file and its games"""

    comments: list[str] = field(default_factory=list)
    games: list[Game] = field(default_factory=list)

    def append_game(self, game: Game | None) -> bool:
        """``cw_scorebook_append_game``: False (nothing done) for NULL"""
        if game is None:
            return False
        self.games.append(game)
        return True

    def insert_game(self, game: Game | None) -> bool:
        """``cw_scorebook_insert_game``: before the first game not earlier by date, then number"""
        if game is None:
            return False
        if not self.games:
            self.games.append(game)
            return True
        i = 0
        while i < len(self.games):
            g = self.games[i]
            if _strcmp(g.info_lookup("date"), game.info_lookup("date")) < 0 or (
                _strcmp(g.info_lookup("date"), game.info_lookup("date")) == 0
                and _strcmp(g.info_lookup("number"), game.info_lookup("number")) < 0
            ):
                i += 1
            else:
                break
        self.games.insert(i, game)
        return True

    def remove_game(self, game_id: str) -> Game | None:
        """``cw_scorebook_remove_game``: the first game with this id, or ``None``"""
        for i, game in enumerate(self.games):
            if game.game_id == game_id:
                return self.games.pop(i)
        return None

    def iterate(self, f: Callable[[Game], bool] | None = None) -> Iterator[Game]:
        """``cw_scorebook_iterate`` / ``_iterator_next``: games for which ``f`` is true"""
        for game in self.games:
            if f is None or f(game):
                yield game

    def read(self, data: bytes) -> int:
        """``cw_scorebook_read``: the number of games read, or -1 for an empty file"""
        file = CFile(data)
        ok, comments = _read_comments(file)
        self.comments.extend(comments)
        if not ok:
            return -1
        find_first_game(file)
        count = 0
        while not file.eof:
            if not self.append_game(read_game(file)):
                break
            count += 1
        return count


def scorebook_read(data: bytes) -> list[Game] | None:
    """``cw_scorebook_read``: every game of an event file, or ``None`` where C returns -1.

    ``None`` is the "could not open file" case of ``cwtools_process_scorebook``: an
    empty file.
    """
    book = Scorebook()
    if book.read(data) < 0:
        return None
    return book.games
