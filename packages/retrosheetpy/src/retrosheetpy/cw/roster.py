"""Port of Chadwick's ``src/cwlib/roster.c`` and ``league.c`` (reading side).

Chadwick is Copyright (c) 2002-2023 Dr T L Turocy and the Chadwick Baseball
Bureau, licensed GPL-2.0-or-later; this module is a derivative of it and keeps
that notice.

A ``TEAMyyyy`` file lists the teams of a season (``league.c``); each team has a
``<team><year>.ROS`` roster file (``roster.c``) giving the players' batting and
throwing hands, which ``cwevent`` prints for players without a ``badj``/``padj``.
"""

from dataclasses import dataclass, field

from retrosheetpy.cw.file import CFile, StrTok

ROSTER_BUFSIZE = 256  # ``char buf[256]`` in ``cw_roster_read`` and ``cw_league_read``


@dataclass
class Player:
    """``CWPlayer``"""

    player_id: str
    last_name: str
    first_name: str
    bats: str
    throws: str

    def set_first_name(self, name: str) -> None:
        """``cw_player_set_first_name``"""
        self.first_name = name

    def set_last_name(self, name: str) -> None:
        """``cw_player_set_last_name``"""
        self.last_name = name


@dataclass
class Roster:
    """``CWRoster``"""

    team_id: str
    league: str
    city: str
    nickname: str
    year: int = 0
    players: list[Player] = field(default_factory=list)

    def set_city(self, city: str) -> None:
        """``cw_roster_set_city``"""
        self.city = city

    def set_nickname(self, nickname: str) -> None:
        """``cw_roster_set_nickname``"""
        self.nickname = nickname

    def set_league(self, league: str) -> None:
        """``cw_roster_set_league``"""
        self.league = league

    def player_append(self, player: Player) -> None:
        """``cw_roster_player_append``"""
        self.players.append(player)

    def player_insert(self, player: Player) -> None:
        """``cw_roster_player_insert``: before the first player whose id is not smaller (strcmp)"""
        i = 0
        while i < len(self.players) and self.players[i].player_id < player.player_id:
            i += 1
        self.players.insert(i, player)

    def player_count(self) -> int:
        """``cw_roster_player_count``"""
        return len(self.players)

    def player_find(self, player_id: str | None) -> Player | None:
        """``cw_roster_player_find``"""
        if player_id is None:
            return None
        for player in self.players:
            if player.player_id == player_id:
                return player
        return None

    def read(self, data: bytes) -> None:
        """``cw_roster_read``: append the players of a ``.ROS`` file's contents"""
        file = CFile(data)
        tok = StrTok()
        while not file.eof:
            buf = file.fgets(ROSTER_BUFSIZE)
            if buf is None:
                return
            player_id = tok(buf)
            last_name = tok(None)
            first_name = tok(None)
            bats = tok(None)
            throws = tok(None)
            if player_id is None or last_name is None or first_name is None:
                continue
            if bats is None or throws is None:
                continue
            # ``bats[0]`` of an empty field is the terminating NUL
            self.players.append(
                Player(player_id, last_name, first_name, bats[:1] or "\0", throws[:1] or "\0")
            )


def roster_batting_hand(roster: Roster | None, player_id: str | None) -> str:
    """``cw_roster_batting_hand``: ``?`` when the roster or the player is unknown"""
    if roster is None:
        return "?"
    # the C compares with strcmp, which crashes on a NULL id; no player matches here
    for player in roster.players:
        if player.player_id == player_id:
            return player.bats if player.bats not in ("\0", " ") else "?"
    return "?"


def roster_throwing_hand(roster: Roster | None, player_id: str | None) -> str:
    """``cw_roster_throwing_hand``"""
    if roster is None:
        return "?"
    for player in roster.players:
        if player.player_id == player_id:
            return player.throws if player.throws not in ("\0", " ") else "?"
    return "?"


@dataclass
class League:
    """``CWLeague``: the rosters named in a team file"""

    rosters: list[Roster] = field(default_factory=list)

    def roster_append(self, roster: Roster) -> None:
        """``cw_league_roster_append``"""
        self.rosters.append(roster)

    def roster_find(self, team: str | None) -> Roster | None:
        """``cw_league_roster_find``"""
        for roster in self.rosters:
            if roster.team_id == team:
                return roster
        return None

    def read(self, data: bytes) -> None:
        """``cw_league_read``: append a roster per line of a ``TEAMyyyy`` file's contents"""
        file = CFile(data)
        tok = StrTok()
        while not file.eof:
            buf = file.fgets(ROSTER_BUFSIZE)
            if buf is None:
                return
            team_id = tok(buf)
            league = tok(None)
            city = tok(None)
            nickname = tok(None)
            if team_id is None or league is None or city is None or nickname is None:
                continue
            self.rosters.append(Roster(team_id, league, city, nickname))
