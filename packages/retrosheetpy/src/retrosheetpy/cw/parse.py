"""Port of Chadwick's play-text parser (``src/cwlib/parse.c``).

Chadwick is Copyright (c) 2002-2023 Dr T L Turocy and the Chadwick Baseball
Bureau, licensed GPL-2.0-or-later. This module is a Python translation of its
parser, so it is a derivative work and keeps that notice. Function names map
one-to-one onto the C functions (``cw_parse_x`` -> ``_x``) so the two can be
read side by side. Where the C code has quirks (a shared token buffer, return
value 0 meaning both "batter out" and "invalid", fixed-size arrays) the quirk is
kept on purpose: the goal is byte-identical ``cwevent`` output.
"""

from dataclasses import dataclass, field
from enum import IntEnum

NUL = "\0"


class Ev(IntEnum):
    """``CWEventType``. Codes 0-24 are the Retrosheet event codes."""

    UNKNOWN = 0
    NONE = 1
    GENERICOUT = 2
    STRIKEOUT = 3
    STOLENBASE = 4
    INDIFFERENCE = 5
    CAUGHTSTEALING = 6
    PICKOFFERROR = 7
    PICKOFF = 8
    WILDPITCH = 9
    PASSEDBALL = 10
    BALK = 11
    OTHERADVANCE = 12
    FOULERROR = 13
    WALK = 14
    INTENTIONALWALK = 15
    HITBYPITCH = 16
    INTERFERENCE = 17
    ERROR = 18
    FIELDERSCHOICE = 19
    SINGLE = 20
    DOUBLE = 21
    TRIPLE = 22
    HOMERUN = 23
    MISSINGPLAY = 24


# Fixed C array sizes are 3/10/10/20; the C code overruns them (undefined
# behaviour) on absurd plays, so these are generous rather than exact.
_PUTOUTS, _ASSISTS, _ERRORS, _TOUCHES = 32, 32, 32, 64


@dataclass
class EventData:
    """``CWEventData``: everything the play text alone says about the play."""

    event_type: int = Ev.UNKNOWN
    advance: list[int] = field(default_factory=lambda: [0] * 4)
    rbi_flag: list[int] = field(default_factory=lambda: [0] * 4)
    fc_flag: list[int] = field(default_factory=lambda: [0] * 4)
    muff_flag: list[int] = field(default_factory=lambda: [0] * 4)
    play: list[str] = field(default_factory=lambda: [""] * 4)
    sh_flag: int = 0
    sf_flag: int = 0
    dp_flag: int = 0
    gdp_flag: int = 0
    tp_flag: int = 0
    wp_flag: int = 0
    pb_flag: int = 0
    foul_flag: int = 0
    bunt_flag: int = 0
    force_flag: int = 0
    sb_flag: list[int] = field(default_factory=lambda: [0] * 4)
    cs_flag: list[int] = field(default_factory=lambda: [0] * 4)
    po_flag: list[int] = field(default_factory=lambda: [0] * 4)
    fielded_by: int = 0
    num_putouts: int = 0
    num_assists: int = 0
    num_errors: int = 0
    num_touches: int = 0
    putouts: list[int] = field(default_factory=lambda: [0] * _PUTOUTS)
    assists: list[int] = field(default_factory=lambda: [0] * _ASSISTS)
    errors: list[int] = field(default_factory=lambda: [0] * _ERRORS)
    touches: list[int] = field(default_factory=lambda: [0] * _TOUCHES)
    error_types: list[str] = field(default_factory=lambda: ["N"] * _ERRORS)
    batted_ball_type: str = " "
    hit_location: str = ""


def is_batter(e: EventData) -> bool:
    """``cw_event_is_batter``"""
    return e.event_type in (Ev.GENERICOUT, Ev.STRIKEOUT) or Ev.WALK <= e.event_type <= Ev.HOMERUN


def is_official_ab(e: EventData) -> bool:
    """``cw_event_is_official_ab``"""
    if not is_batter(e):
        return False
    if e.sh_flag or e.sf_flag:
        return False
    return e.event_type not in (Ev.WALK, Ev.INTENTIONALWALK, Ev.HITBYPITCH, Ev.INTERFERENCE)


def runner_put_out(e: EventData, base: int) -> bool:
    """``cw_event_runner_put_out``"""
    return e.play[base] != "" and "E" not in e.play[base]


def outs_on_play(e: EventData) -> int:
    """``cw_event_outs_on_play``"""
    return sum(runner_put_out(e, b) for b in range(4))


def runs_on_play(e: EventData) -> int:
    """``cw_event_runs_on_play``"""
    return sum(e.advance[b] >= 4 for b in range(4))


def rbi_on_play(e: EventData) -> int:
    """``cw_event_rbi_on_play``"""
    return sum(e.rbi_flag[b] > 0 for b in range(4))


def _set_play(e: EventData, base: int, play: str) -> None:
    e.play[base] = play[:19]  # CW_STRLCPY into char[20]


def _isdigit(c: str) -> bool:
    return "0" <= c <= "9"


def _isfielder(c: str) -> bool:
    return "1" <= c <= "9" or c == "?"


def _isalpha(c: str) -> bool:
    return "A" <= c <= "Z" or "a" <= c <= "z"


_THROW = ("TH", "TH1", "TH2", "TH3", "THH")


class _Parser:
    """``CWParserState`` plus the cursor primitives."""

    def __init__(self, text: str) -> None:
        s = text.upper()
        # Preprocessing to turn SBH and CSH strings into SB4 and CS4
        i = s.find("SBH")
        if i >= 0:
            s = s[: i + 2] + "4" + s[i + 3 :]
        i = s.find("CSH")
        if i >= 0 and "FCSH" not in s:
            s = s[: i + 2] + "4" + s[i + 3 :]
        self.s = s
        self.sym = s[0] if s else NUL
        self.pos = 1
        # ``char token[20]`` of the C parser state: a buffer, not a string, because the C
        # leaves stale characters after a write that was never NUL-terminated (a failed parse)
        self._tok = bytearray(64)

    @property
    def token(self) -> str:
        end = self._tok.find(0)
        return self._tok[: end if end >= 0 else len(self._tok)].decode("latin-1")

    @token.setter
    def token(self, value: str) -> None:
        """Write ``value`` and a NUL at the start of the buffer, as ``*c = '\\0'`` does."""
        self._tok[: len(value) + 1] = value.encode("latin-1") + b"\0"

    def put(self, at: int, ch: str) -> None:
        """``*(play++) = ch``"""
        self._tok[at] = ord(ch)

    def nextsym(self) -> str:
        if self.pos > len(self.s):
            self.sym = NUL
        else:
            # '#' and '!' (uncertain / great play) are ignored inside play text
            while True:
                self.sym = self.s[self.pos] if self.pos < len(self.s) else NUL
                self.pos += 1
                if self.sym not in "#!":
                    break
        return self.sym

    def peek(self) -> str:
        return " " if self.pos >= len(self.s) else self.s[self.pos]

    def primary_event(self) -> None:
        tok = []
        while "A" <= self.sym <= "Z":
            tok.append(self.sym)
            self.nextsym()
        self.token = "".join(tok)


def _hit_fielder(p: _Parser, e: EventData) -> None:
    if _isdigit(p.sym):
        e.fielded_by = ord(p.sym) - ord("0")
    while _isfielder(p.sym) or p.sym == "0":
        p.nextsym()


def _dedupe_assists(e: EventData, assists: list[int]) -> None:
    for i, a in enumerate(assists):
        if a in assists[:i]:
            continue
        e.assists[e.num_assists] = a
        e.num_assists += 1


def _touch(e: EventData, fielder: int) -> None:
    if e.num_touches == 0 or e.touches[e.num_touches - 1] != fielder:
        e.touches[e.num_touches] = fielder
        e.num_touches += 1


def _fielding_credit(p: _Parser, e: EventData, prev: str) -> int:
    """``cw_parse_fielding_credit``: 0 = batter out (or invalid), 1 = safe on error."""
    last = p.sym
    assists: list[int] = []
    n = 0  # ``play`` pointer into the token buffer

    if p.sym == "E":
        p.nextsym()
        if not _isfielder(p.sym):
            return 0
        if _isdigit(p.sym) and e.event_type != Ev.INTERFERENCE:
            # Special case: C.B-1(E2) shouldn't generate a second error.
            e.errors[e.num_errors] = ord(p.sym) - ord("0")
            e.error_types[e.num_errors] = "F"
            e.num_errors += 1
        p.put(0, "E")
        p.put(1, p.sym)
        p.put(2, "\0")
        p.nextsym()
        return 1

    if prev != " " and prev != p.sym:
        assists.append(ord(prev) - ord("0"))
        p.put(n, prev)
        n += 1
    p.put(n, p.sym)
    n += 1

    while True:
        p.nextsym()
        if "1" <= p.sym <= "9" or p.sym == "?":
            if _isdigit(last):
                assists.append(ord(last) - ord("0"))
                _touch(e, ord(last) - ord("0"))
            if p.sym != "?":
                p.put(n, p.sym)
                n += 1
            last = p.sym
        elif p.sym == "E":
            if _isdigit(last):
                assists.append(ord(last) - ord("0"))
            p.put(n, "E")
            n += 1
            p.nextsym()
            if not _isdigit(p.sym):
                return 0  # the token is left without its NUL, as in C
            e.errors[e.num_errors] = ord(p.sym) - ord("0")
            e.error_types[e.num_errors] = "D"
            e.num_errors += 1
            p.put(n, p.sym)
            n += 1
            p.put(n, "\0")
            p.nextsym()
            _dedupe_assists(e, assists)
            return 1
        else:
            if _isdigit(last):
                e.putouts[e.num_putouts] = ord(last) - ord("0")
                e.num_putouts += 1
                _touch(e, ord(last) - ord("0"))
            p.put(n, "\0")
            _dedupe_assists(e, assists)
            return 0


def _flag(p: _Parser) -> None:
    """``cw_parse_flag``: read one flag (without the slash) into the token."""
    tok = []
    while True:
        p.nextsym()
        if p.sym not in "/.()#!+-" and p.sym != NUL:
            tok.append(p.sym)
        else:
            break
    p.token = "".join(tok)


def _drop_batter_putout(e: EventData) -> None:
    """Remove the implied catcher putout (always listed first)."""
    e.putouts[0] = e.putouts[1]
    e.putouts[1] = e.putouts[2]
    e.putouts[2] = 0
    e.num_putouts -= 1
    for i in range(e.num_touches - 1):
        e.touches[i] = e.touches[i + 1]
    e.num_touches -= 1
    e.touches[e.num_touches] = 0


def _advance_modifier(p: _Parser, e: EventData, safe: int, base_from: int, base_to: int) -> int:
    is_error = False

    if _isfielder(p.sym) or p.sym == "E":
        if p.sym == "E":
            is_error = True
        if _fielding_credit(p, e, " "):
            is_error = True
            if not safe:
                safe = 1
                e.muff_flag[base_from] = 1
                if e.advance[base_from] < 5:
                    # guards against things like 3XH(UR)(5E2)
                    e.advance[base_from] = base_to
                if base_from == 0 and e.event_type == Ev.STRIKEOUT:
                    # K.BX1(2E3): remove the implied putout for the catcher
                    _drop_batter_putout(e)
                for i in range(base_from, -1, -1):
                    e.rbi_flag[i] = -1
        elif base_from == 0 and e.event_type == Ev.STRIKEOUT:
            # batter put out listed explicitly in advancement
            _drop_batter_putout(e)

        if p.token[:1] != "E":
            _set_play(e, base_from, p.token)
        else:
            for i in range(base_from, -1, -1):
                e.rbi_flag[i] = -1

        if p.sym == "/":
            _flag(p)
            if p.token in _THROW:
                if is_error:
                    e.error_types[e.num_errors - 1] = "T"
            elif p.token in ("INT", "BINT", "OBS", "G", "U", "AP", "BR", "FO"):
                pass  # accepted modifiers on the putout
            else:
                return 0

        if p.sym == "(":
            p.nextsym()
            if not _advance_modifier(p, e, safe, base_from, base_to):
                return 0

        # tolerate weird things like 2XH(9S)
        while p.sym != ")" and p.sym != NUL:
            p.nextsym()
    else:
        p.primary_event()
        t = p.token
        if t in ("NR", "NORBI"):  # archaic
            e.rbi_flag[base_from] = 0
        elif t == "RBI" and e.advance[base_from] >= 4:
            e.rbi_flag[base_from] = 2  # (RBI) really present
        elif t == "UR":
            e.advance[base_from] = 5
        elif t == "TUR":
            e.advance[base_from] = 6
        elif t == "WP":
            e.wp_flag = 1
            e.rbi_flag[base_from] = 0
        elif t == "PB":
            e.pb_flag = 1
            e.rbi_flag[base_from] = 0
        elif t == "TH":
            if "1" <= p.sym <= "3":
                p.nextsym()
        elif t in ("THH", "INT"):
            pass
        else:
            return 0

    if p.sym == ")":
        p.nextsym()
        return 1
    return 0


_LOCATIONS = frozenset(
    (
        "1 13 15 1S 2 2F 23 23F 25 25F 3SF 3F 3DF 3S 3 3D 34S 34 34D "
        "4S 4 4D 4MS 4M 4MD 6MS 6M 6MD 6S 6 6D 56S 56 56D 5S 5 5D 5SF 5F 5DF "
        "7LSF 7LS 7S 78S 8S 89S 9S 9LS 9LSF 7LF 7L 7 78 8 89 9 9L 9LF "
        "7LDF 7LD 7D 78D 8D 89D 9D 9LD 9LDF 78XD 8XD 89XD "
        # nonstandard or archaic, but present in Retrosheet data
        "13S 15S 2LF 2RF 2L 2R 3L 46 5L 7LDW 7DW 78XDW 8XDW 89XDW 9DW 9LDW "
        "7LMF 7LM 7M 78M 8LM 8M 8RM 89M 9M 9LM 9LMF "
        "8LS 8RS 8LD 8RD 8LXD 8RXD 8LXDW 8RXDW"
    ).split()
)


def _location(e: EventData, loc: str, bunt: bool) -> bool:
    """Shared tail of the trajectory/location lookup; True if loc was known."""
    if loc not in _LOCATIONS:
        return False
    e.hit_location = loc
    if loc[-1] == "F":
        e.foul_flag = 1
    if bunt:
        e.bunt_flag = 1
    return True


def _trajectory_or_location(e: EventData, flag: str) -> None:
    """The ``strlen(flag) >= 3`` branch of ``cw_parse_flags`` (flag has its slash)."""
    bunt = flag[1] == "B"
    traj = flag[2] if bunt else flag[1]
    if traj in "GFPL":
        loc = flag[3:] if bunt else flag[2:]
        if _location(e, loc, bunt):
            e.batted_ball_type = traj
    else:
        _location(e, flag[2:] if bunt else flag[1:], bunt)


def _flags(p: _Parser, e: EventData) -> None:
    while True:
        flag = "/"
        while True:
            p.nextsym()
            if p.sym not in "/.#!+-" and p.sym != NUL:
                flag += p.sym
            if p.sym in "/.#!+-" or p.sym == NUL:
                break

        if flag in ("/SH", "/SAC"):
            e.sh_flag = 1
            e.bunt_flag = 1
        elif flag == "/SF":
            e.sf_flag = 1
            # a /SF is a fly ball unless E4/SF style plays say otherwise
            if e.batted_ball_type == " " or (
                e.event_type == Ev.ERROR and e.batted_ball_type == "G"
            ):
                e.batted_ball_type = "F"
        elif flag == "/DP":
            e.dp_flag = 1
        elif flag == "/GDP":
            e.dp_flag = 1
            e.gdp_flag = 1
            e.batted_ball_type = "G"
        elif flag == "/LDP":
            e.dp_flag = 1
            e.batted_ball_type = "L"
        elif flag == "/FDP":
            e.dp_flag = 1
            e.batted_ball_type = "F"
        elif flag == "/BGDP":
            e.bunt_flag = 1
            e.dp_flag = 1
            e.gdp_flag = 1
            e.batted_ball_type = "G"
        elif flag == "/BPDP":
            e.bunt_flag = 1
            e.dp_flag = 1
            e.batted_ball_type = "P"
        elif flag == "/BFDP":
            # interpreted as bunt-foul double play
            e.bunt_flag = 1
            e.dp_flag = 1
            e.batted_ball_type = "P"
            e.foul_flag = 1
        elif flag == "/TP":
            e.tp_flag = 1
        elif flag == "/GTP":
            e.tp_flag = 1
            e.batted_ball_type = "G"
        elif flag == "/LTP":
            e.tp_flag = 1
            e.batted_ball_type = "L"
        elif flag == "/FL":
            e.foul_flag = 1
        elif flag == "/FO":
            e.force_flag = 1
            if e.batted_ball_type == " ":
                e.batted_ball_type = "G"
        elif flag[1:] in _THROW and e.event_type in (Ev.ERROR, Ev.PICKOFFERROR):
            e.error_types[0] = "T"
        elif flag == "/B":
            e.bunt_flag = 1
        elif flag in ("/BG", "/BP", "/BF", "/BL"):
            e.bunt_flag = 1
            e.batted_ball_type = flag[2]
        elif flag in ("/F", "/G", "/L"):
            e.batted_ball_type = flag[1]
        elif flag in ("/P", "/IF"):
            e.batted_ball_type = "P"  # infield fly is assumed to be a popup
        elif len(flag) >= 3:
            _trajectory_or_location(e, flag)
        elif flag[1:] in _LOCATIONS:
            e.hit_location = flag[1:]

        if p.sym == "." or p.sym == NUL:
            break


def _balk(p: _Parser, e: EventData, flags: int) -> int:
    while flags and p.sym == "/":
        _flag(p)  # /OBS silently accepted
    return 1


def _stolen_base(p: _Parser, e: EventData, flags: int) -> int:
    if p.sym == "2":
        e.sb_flag[1] = 1
        e.advance[1] = 2
        p.nextsym()
    elif p.sym == "3":
        e.sb_flag[2] = 1
        e.advance[2] = 3
        p.nextsym()
    elif p.sym == "4":
        # SBH is converted to SB4 in initialization
        e.sb_flag[3] = 1
        e.advance[3] = 4
        p.nextsym()
        # accept archaic SBH(UR) or SBH(TUR)
        if p.sym == "(":
            e.advance[3] = 5
            p.nextsym()
            if p.sym == "T":
                e.advance[3] = 6
                p.nextsym()
            if p.sym != "U":
                return 0
            p.nextsym()
            if p.sym != "R":
                return 0
            p.nextsym()
            if p.sym != ")":
                return 0
            p.nextsym()
    else:
        return 0

    if p.sym == ";":
        p.nextsym()
        p.primary_event()
        if p.token == "SB":
            _stolen_base(p, e, 0)
        elif p.token == "CS":
            # Chadwick extension: early history has both SB and CS on one play
            _caught_stealing(p, e, 0)
        else:
            return 0

    while flags and p.sym == "/":
        _flag(p)  # flags accepted silently
    return 1


def _cs_error_credit(p: _Parser, e: EventData) -> int:
    """The trailing ``/TH`` / ``/INT`` handling shared by caught-stealing credits."""
    if p.sym == "/":
        _flag(p)
        if p.token in _THROW:
            e.error_types[e.num_errors - 1] = "T"
        elif p.token == "INT":
            pass
        else:
            return 0
    return 1


def _caught_stealing(p: _Parser, e: EventData, flags: int) -> int:
    if "2" <= p.sym <= "4":
        runner = ord(p.sym) - ord("1")
        e.cs_flag[runner] = 1
    else:
        return 0

    while p.nextsym() == "(":
        p.nextsym()
        if _isfielder(p.sym):
            if _fielding_credit(p, e, " "):
                e.advance[runner] = runner + 1
                e.muff_flag[runner] = 1
                _set_play(e, runner, p.token)
                if not _cs_error_credit(p, e):
                    return 0
            else:
                _set_play(e, runner, p.token)
        elif p.sym == "E":
            _fielding_credit(p, e, " ")
            e.advance[runner] = runner + 1
            e.muff_flag[runner] = 1
            _set_play(e, runner, p.token)
            if not _cs_error_credit(p, e):
                return 0
        elif _isalpha(p.sym):
            p.primary_event()
            if p.token == "UR" and e.advance[runner] == 4:
                e.advance[runner] = 5
            elif p.token == "TUR" and e.advance[runner] == 4:
                e.advance[runner] = 6
            else:
                return 0
            if p.sym != ")":
                return 0

    if p.sym == ";":
        # Two caught stealings can happen, though they're rare
        p.nextsym()
        p.primary_event()
        if p.token == "CS":
            _caught_stealing(p, e, 0)
        elif p.token == "SB":
            _stolen_base(p, e, 0)
        else:
            return 0

    while flags and p.sym == "/":
        _flag(p)
        if p.token == "DP":
            e.dp_flag = 1

    for _ in range(e.num_errors):
        if e.error_types[0] == "F":
            e.error_types[0] = "D"
    return 1


def _safe_on_error(p: _Parser, e: EventData, flags: int) -> int:
    e.advance[0] = 1
    # Chadwick extension: accept E0 for reached on error, unknown fielder
    if not _isdigit(p.sym):
        return 0
    n = ord(p.sym) - ord("0")
    e.errors[e.num_errors] = n
    e.error_types[e.num_errors] = "F"
    e.num_errors += 1
    e.fielded_by = n
    e.batted_ball_type = "G" if p.sym <= "6" else "F"
    p.nextsym()
    if p.sym == "?":  # "En?" for a really bad play
        p.nextsym()
    if flags and p.sym == "/":
        _flags(p, e)
    return 1


def _fielders_choice(p: _Parser, e: EventData, flags: int) -> int:
    e.advance[0] = 1
    e.batted_ball_type = "G"
    if "1" <= p.sym <= "9":
        e.fielded_by = ord(p.sym) - ord("0")
        p.nextsym()
    elif p.sym == "?":
        p.nextsym()
    if flags and p.sym == "/":
        _flags(p, e)
    return 1


def _foul_error(p: _Parser, e: EventData, flags: int) -> int:
    if "1" <= p.sym <= "9":
        n = ord(p.sym) - ord("0")
        e.errors[e.num_errors] = n
        e.error_types[e.num_errors] = "F"
        e.num_errors += 1
        e.fielded_by = n
        p.nextsym()
    else:
        return 0
    if flags and p.sym == "/":
        _flags(p, e)  # most likely a trajectory code
    return 1


def _out_base(p: _Parser) -> int:
    """Parse ``(n)`` after a putout: base (0 = batter) or -1 on error."""
    p.nextsym()
    if p.sym not in ("1", "2", "3", "B"):
        return -1
    base = 0 if p.sym == "B" else ord(p.sym) - ord("0")
    p.nextsym()
    if p.sym != ")":
        return -1
    p.nextsym()
    return base


def _generic_out(p: _Parser, e: EventData, flags: int) -> int:
    last = " "  # fielder of the previous putout, for 54(1)3/GDP
    force_play = -1

    if p.sym != "?" and (p.sym != "9" or p.peek() != "9"):
        # June 2020: generic outs starting with 99 give fielded_by = 0
        e.fielded_by = ord(p.sym) - ord("0")
    e.advance[0] = 1

    while _isfielder(p.sym):
        safe = _fielding_credit(p, e, last)

        if p.sym == "(":
            base = _out_base(p)
            if base < 0:
                return 0
            if force_play == -1:
                force_play = 1 if base > 0 else 0
            e.advance[base] = base + 1 if safe else 0
            if safe:
                e.muff_flag[base] = 1
            e.fc_flag[base] = 1
            if e.batted_ball_type == " ":
                if len(p.token) > 1 or base > 0:
                    # more than one fielder implies a ground ball; so does
                    # getting the first out on a non-batter
                    e.batted_ball_type = "G"
                elif len(p.token) == 1 and base == 0:
                    e.batted_ball_type = "F"
            _set_play(e, base, p.token)
            last = p.token[-1]
        else:
            e.batted_ball_type = "G" if len(p.token) > 1 or last != " " else "F"
            _set_play(e, 0, p.token)
            e.advance[0] = 1 if safe else 0
            if safe:
                e.muff_flag[0] = 1
            break

    if p.sym in "+-":  # hard/soft-hit ball modifiers are ignored
        p.nextsym()

    if flags and p.sym == "/":
        _flags(p, e)

    # 10.18(g): force notation whose first out is the batter means a caught
    # ball, so no responsibility hand-off, except for reverse-force GDPs.
    if force_play == 0 and "/GDP" not in p.s:
        for i in range(1, 4):
            e.fc_flag[i] = 0
    return 1


def _hit_by_pitch(p: _Parser, e: EventData, flags: int) -> int:
    e.advance[0] = 1
    while flags and p.sym == "/":
        _flag(p)  # /REV silently accepted
    return 1


def _interference(p: _Parser, e: EventData, flags: int) -> int:
    e.advance[0] = 1

    while p.sym == "/":
        _flag(p)
        t = p.token
        if t[:1] == "E" and e.num_errors > 0:
            return 0
        if t in ("E1", "E2", "E3", "E4", "E6"):
            e.errors[e.num_errors] = int(t[1])
            e.num_errors += 1
        elif t == "4E1":
            e.errors[e.num_errors] = 1
            e.num_errors += 1
            e.assists[e.num_assists] = 4
            e.num_assists += 1
        elif t == "INT":
            pass
        elif t == "G":
            e.batted_ball_type = "G"  # interference can also occur on a batted ball
        elif len(t) >= 2:
            bunt = t[0] == "B"
            traj = t[1] if bunt else t[0]
            if traj in "GFPL":
                if _location(e, t[2:] if bunt else t[1:], bunt):
                    e.batted_ball_type = traj
            else:
                _location(e, t[1:] if bunt else t, bunt)
        elif t in _LOCATIONS:
            e.hit_location = t

    if e.num_errors == 0:
        e.errors[e.num_errors] = 2
        e.num_errors += 1
    e.error_types[0] = "F"
    return 1


def _indifference(p: _Parser, e: EventData, flags: int) -> int:
    return 1


def _other_advance(p: _Parser, e: EventData, flags: int) -> int:
    while flags and p.sym == "/":
        _flag(p)
        t = p.token
        if t == "DP":
            e.dp_flag = 1
        elif t in ("BINT", "INT", "AP", "MREV", "UREV", "NDP", "OBS"):
            pass
        elif t == "TP":
            e.tp_flag = 1
        elif t[:1] == "R":
            pass  # relay notation
        else:
            return 0
    return 1


def _passed_ball(p: _Parser, e: EventData, flags: int) -> int:
    e.pb_flag = 1
    while flags and p.sym == "/":
        _flag(p)
        if p.token == "DP":
            e.dp_flag = 1
    return 1


def _pickoff_stolen_base(p: _Parser, e: EventData, flags: int) -> int:
    return _stolen_base(p, e, flags)


def _pickoff_caught_stealing(p: _Parser, e: EventData, flags: int) -> int:
    idx = ord(p.sym) - ord("1")
    if 0 <= idx <= 3:  # C indexes out of bounds here
        e.po_flag[idx] = 1
    return _caught_stealing(p, e, flags)


def _pickoff(p: _Parser, e: EventData, flags: int) -> int:
    if "1" <= p.sym <= "3":
        runner = ord(p.sym) - ord("0")
    else:
        return 0
    e.po_flag[runner] = 1

    if p.nextsym() != "(":
        return 0
    p.nextsym()
    if _isfielder(p.sym):
        _fielding_credit(p, e, " ")
        _set_play(e, runner, p.token)
    elif p.sym == "E":
        _fielding_credit(p, e, " ")
        _set_play(e, runner, p.token)
        n = e.num_errors - 1
        if p.sym == "/":
            _flag(p)
            if p.token in _THROW:
                e.error_types[n] = "T"
            else:
                return 0
        # By convention errors on pitcher or catcher are throwing errors;
        # others are assumed to be muffs, unless marked otherwise.
        elif e.errors[n] in (1, 2) and e.error_types[n] == "F":
            e.error_types[n] = "T"
        else:
            e.error_types[n] = "D"
    else:
        return 0

    if p.sym == ")":
        p.nextsym()
    else:
        return 0

    if flags and p.sym == "/":
        _flags(p, e)  # most likely /DP
    return 1


def _base_hit(p: _Parser, e: EventData, flags: int) -> int:
    if _isfielder(p.sym) or p.sym == "0":
        _hit_fielder(p, e)
    if flags and p.sym == "/":
        _flags(p, e)
    return 1


def _ground_rule_double(p: _Parser, e: EventData, flags: int) -> int:
    while "1" <= p.sym <= "9":
        p.nextsym()  # newer files list fielders after DGR; no fielded-by credit
    if flags and p.sym == "/":
        _flags(p, e)
    return 1


def _plus_event(p: _Parser, e: EventData, *, kind: int) -> int | None:
    """The ``K+xx`` / ``W+xx`` tail. Returns 0 to abort the parse, None to go on."""
    p.nextsym()
    p.primary_event()
    t = p.token
    if t == "WP":
        e.wp_flag = 1
    elif t == "PB":
        e.pb_flag = 1
    elif t == "PO":
        if not _pickoff(p, e, 0) and kind == Ev.WALK:
            return 0
    elif t == "POCS":
        if not _pickoff_caught_stealing(p, e, 0) and kind == Ev.WALK:
            return 0
    elif t == "POSB":
        if not _pickoff_stolen_base(p, e, 0) and kind == Ev.WALK:
            return 0
    elif t == "SB":
        if not _stolen_base(p, e, 0) and kind == Ev.WALK:
            return 0
    elif t == "CS":
        if not _caught_stealing(p, e, 0) and kind == Ev.WALK:
            return 0
    elif t == "DI":
        _indifference(p, e, 0)
    elif t == "OA" or (t == "OBA" and kind == Ev.STRIKEOUT):
        pass
    elif t == "E":
        if p.sym < "1" or p.sym > "9":
            return 0
        e.errors[e.num_errors] = ord(p.sym) - ord("0")
        e.error_types[e.num_errors] = "F"
        e.num_errors += 1
        p.nextsym()
    elif kind == Ev.STRIKEOUT:
        return 0
    return None


def _strikeout(p: _Parser, e: EventData, flags: int) -> int:
    if "1" <= p.sym <= "9":
        safe = _fielding_credit(p, e, " ")
        e.advance[0] = 1 if safe else 0
        e.muff_flag[0] = 1 if safe else 0
        _set_play(e, 0, p.token)
    else:
        # just a bare strikeout
        _set_play(e, 0, "2")
        e.putouts[e.num_putouts] = 2
        e.num_putouts += 1
        e.touches[e.num_touches] = 2
        e.num_touches += 1

    if p.sym == "+":
        if _plus_event(p, e, kind=Ev.STRIKEOUT) == 0:
            return 0

    while flags and p.sym == "/":
        _flag(p)
        t = p.token
        if t in _THROW and e.num_errors > 0:
            e.error_types[0] = "T"
        elif t == "DP":
            e.dp_flag = 1
        elif t == "TP":
            e.tp_flag = 1
        elif t in ("B", "BF", "BG", "BP"):
            e.bunt_flag = 1
        elif t == "FL":
            e.foul_flag = 1
        # /F and /L take no action (see Chadwick 0.6.2); other flags are
        # accepted silently because Retrosheet files contain many.
    return 1


def _walk(p: _Parser, e: EventData, flags: int) -> int:
    e.advance[0] = 1

    if p.sym == "+":
        if _plus_event(p, e, kind=Ev.WALK) == 0:
            return 0

    while flags and p.sym == "/":
        _flag(p)
        t = p.token
        if t in _THROW and e.num_errors > 0:
            e.error_types[0] = "T"
        elif t == "DP":
            e.dp_flag = 1
        elif t in ("BOOT", "MREV", "UREV", "UINT", "COUR") or t[:1] == "R":
            pass  # silently accepted
        else:
            return 0
    return 1


def _wild_pitch(p: _Parser, e: EventData, flags: int) -> int:
    e.wp_flag = 1
    while flags and p.sym == "/":
        _flag(p)
        if p.token == "DP":
            e.dp_flag = 1
    return 1


def _runner_advance(p: _Parser, e: EventData) -> int:
    if (p.sym < "1" or p.sym > "3") and p.sym != "B":
        return 0
    base_from = 0 if p.sym == "B" else ord(p.sym) - ord("0")

    p.nextsym()
    if p.sym not in ("-", "X"):
        return 0
    safe = 1 if p.sym == "-" else 0

    p.nextsym()
    if (p.sym < "1" or p.sym > "3") and p.sym != "H":
        return 0
    base_to = 4 if p.sym == "H" else ord(p.sym) - ord("0")

    if safe:
        # takes care of plays like CSH(1E2)(UR).3-H, where advancement is
        # already implied and marked unearned
        if base_to < 4 or e.advance[base_from] < 4:
            e.advance[base_from] = base_to
        if (
            base_to == 4
            and is_batter(e)
            and not e.gdp_flag
            and (e.event_type != Ev.ERROR or base_from == 3)
            and e.event_type != Ev.STRIKEOUT
            and e.rbi_flag[base_from] != -1
        ):
            e.rbi_flag[base_from] = 1
    else:
        e.advance[base_from] = 0
        if e.event_type == Ev.FIELDERSCHOICE:
            e.fc_flag[base_from] = 1

    p.nextsym()
    while p.sym == "(":
        p.nextsym()
        if not _advance_modifier(p, e, safe, base_from, base_to):
            return 0
    return 1


def _advancement(p: _Parser, e: EventData) -> int:
    while True:
        p.nextsym()
        if not _runner_advance(p, e):
            return 0
        if p.sym != ";":
            break
    return 1 if p.sym == NUL else 0


def _sanity_check(e: EventData) -> None:
    """``cw_parse_sanity_check``"""
    default_advance: dict[int, int] = {Ev.SINGLE: 1, Ev.DOUBLE: 2, Ev.TRIPLE: 3, Ev.HOMERUN: 4}
    if e.event_type in default_advance and e.advance[0] == 0 and e.play[0] == "":
        e.advance[0] = default_advance[e.event_type]
        if e.event_type == Ev.HOMERUN:
            e.rbi_flag[0] = 1

    if e.event_type == Ev.STRIKEOUT and e.play[0] == "2" and e.advance[0] > 0:
        e.play[0] = ""
        e.putouts[0] = e.putouts[1]
        e.putouts[1] = e.putouts[2]
        e.putouts[2] = 0
        e.num_putouts -= 1

    if e.event_type == Ev.WALK:
        e.rbi_flag[0] = e.rbi_flag[1] = e.rbi_flag[2] = 0

    if e.event_type == Ev.FOULERROR:
        e.foul_flag = 1
        if e.batted_ball_type == " ":
            e.batted_ball_type = "F" if e.errors[0] >= 7 else "P"
    elif not is_batter(e):
        for i in range(e.num_errors):
            if e.error_types[i] == "F":
                e.error_types[i] = "D"

    for base in range(4):
        if e.rbi_flag[base] == -1:
            e.rbi_flag[base] = 0
        if e.play[base] != "" and "E" not in e.play[base]:
            e.advance[base] = 0  # patches up instances like BXH(832)(E8)
        if "99" in e.play[base]:
            # unknown fielding credits: no fielding credits at all
            for i in range(e.num_putouts):
                e.putouts[i] = 0
            for i in range(e.num_assists):
                e.assists[i] = 0
            e.num_putouts = 0
            e.num_assists = 0

    # default batted ball types from the fielding credit
    if e.event_type == Ev.GENERICOUT:
        if (
            len(e.play[0]) == 1
            and not e.dp_flag
            and not e.tp_flag
            and not e.bunt_flag
            and e.batted_ball_type == " "
        ):
            e.batted_ball_type = "F"
        elif len(e.play[0]) >= 1 and e.batted_ball_type == " ":
            e.batted_ball_type = "G"

    if e.event_type == Ev.SINGLE and e.bunt_flag and e.batted_ball_type == " ":
        e.batted_ball_type = "G"

    if e.sh_flag:
        e.batted_ball_type = "G"


_PRIMARY = {
    "BK": (Ev.BALK, _balk),
    "C": (Ev.INTERFERENCE, _interference),
    "CS": (Ev.CAUGHTSTEALING, _caught_stealing),
    "D": (Ev.DOUBLE, _base_hit),
    "DGR": (Ev.DOUBLE, _ground_rule_double),
    "DI": (Ev.INDIFFERENCE, _indifference),
    "E": (Ev.ERROR, _safe_on_error),
    "FC": (Ev.FIELDERSCHOICE, _fielders_choice),
    "FLE": (Ev.FOULERROR, _foul_error),
    "H": (Ev.HOMERUN, _base_hit),
    "HP": (Ev.HITBYPITCH, _hit_by_pitch),
    "HR": (Ev.HOMERUN, _base_hit),
    "I": (Ev.INTENTIONALWALK, _walk),
    "IW": (Ev.INTENTIONALWALK, _walk),
    "K": (Ev.STRIKEOUT, _strikeout),
    "OA": (Ev.OTHERADVANCE, _other_advance),
    "PB": (Ev.PASSEDBALL, _passed_ball),
    "PO": (Ev.PICKOFF, _pickoff),
    "POCS": (Ev.PICKOFF, _pickoff_caught_stealing),
    "POSB": (Ev.STOLENBASE, _pickoff_stolen_base),
    "S": (Ev.SINGLE, _base_hit),
    "SB": (Ev.STOLENBASE, _stolen_base),
    "T": (Ev.TRIPLE, _base_hit),
    "W": (Ev.WALK, _walk),
    "WP": (Ev.WILDPITCH, _wild_pitch),
}


def parse_event(text: str) -> tuple[EventData, bool]:
    """``cw_parse_event``: parse play text into :class:`EventData`.

    Returns the (possibly half-filled, as in C) data and whether it parsed.
    """
    e = EventData()
    p = _Parser(text)
    p.primary_event()

    if p.token == "":
        e.event_type = Ev.GENERICOUT
        if not _generic_out(p, e, 1):
            return e, False
    else:
        entry = _PRIMARY.get(p.token)
        if entry is None:
            return e, False
        e.event_type, handler = entry
        if not handler(p, e, 1):
            return e, False

    if p.sym == ".":
        if not _advancement(p, e):
            return e, False

    if p.sym in ("+", "-", "#"):
        p.nextsym()

    if p.sym != NUL:
        return e, False

    _sanity_check(e)
    return e, True
