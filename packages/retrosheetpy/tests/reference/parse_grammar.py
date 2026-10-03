# ruff: noqa: E501
"""Grammar-based play generator for the parser differential (see ``parse_fuzz.py``).

Real corpora and character mutations rarely reach rare Chadwick syntax (TH/INT error
modifiers, bunt/foul flag combinations, backward advances, ...).  This builds plays from the
token vocabulary of ``cwlib/parse.c`` (every string literal the parser compares against), so
every modifier / advance / error branch is exercised in many combinations, valid and not.
"""

import random

PRIMARY = [
    "S",
    "D",
    "T",
    "H",
    "HR",
    "K",
    "W",
    "IW",
    "I",
    "HP",
    "NP",
    "BK",
    "FC",
    "DGR",
    "OA",
    "DI",
    "C",
    "WP",
    "PB",
    "SB2",
    "SB3",
    "SBH",
    "CS2",
    "CS3",
    "CSH",
    "PO1",
    "PO2",
    "PO3",
    "POCS2",
    "POCS3",
    "POCSH",
    "POSB2",
    "K+WP",
    "K+PB",
    "K+SB2",
    "K+CS2",
    "K+OA",
    "K+PO1",
    "K+POCS2",
    "W+WP",
    "W+PB",
    "IW+WP",
    "S8",
    "S7",
    "S9",
    "D7",
    "D8",
    "D9",
    "T9",
    "HR9",
    "H8",
    "FC5",
    "FC6",
    "FC3",
    "FC1",
    "E1",
    "E2",
    "E3",
    "E4",
    "E5",
    "E6",
    "E7",
    "E8",
    "E9",
    "FLE2",
    "FLE5",
    "FLE9",
    "1",
    "2",
    "3",
    "4",
    "5",
    "6",
    "7",
    "8",
    "9",
    "13",
    "34",
    "43",
    "54",
    "63",
    "64",
    "46",
    "36",
    "31",
    "15",
    "25",
    "23",
    "53",
    "83",
    "73",
    "93",
    "5(1)3",
    "64(1)3",
    "54(2)3",
    "6(1)3",
    "4(1)",
    "46(1)3",
    "63(B)",
    "8(1)",
    "1(B)",
    "3(B)",
    "4(B)3",
    "6(2)3",
    "5(3)",
    "64(1)3(2)",
    "54(1)(B)",
    "6(1)6(3)",
    "46(1)3(2)",
    "C/E4",
    "C/E6",
    "C/E1",
    "C/E2",
    "C/E3",
    "C/E2/BG5S",
    "C/E3/G",
    "C/E2/G",
    "C/E1/FL",
    "FLE",
    "FLE/F",
    "FLE.",
    "K+E",
    "K+E3",
    "K+E/F",
    "K+E3.B-1",
    "CS2(UR3)",
    "CSH(UR3)",
    "CS3(TUR)",
    "CS2(E4/TH).2-3;3-H(UR)",
    "SBH(UR)",
    "SBH(TUR)",
    "SBH(U)",
    "SBH(UX)",
    "SBH;CSH(UR/F)",
    "SBH;CSH(UR3)",
    "SB3;CSH(UR(",
    "SBH;CSH(TUR/",
    "SBH;CSH(UR)",
    "SBH+CSH(UR3)",
    "K23.BX1(2E3)",
    "K.BX1(2E3)",
    "K+SB2.BX1(2E3)",
    "K23.BX2(3E4)",
    "W+E",
    "W+E/F",
    "W+E5",
    "8/F",
    "7/F",
    "9/F",
    "2/F",
    "5/F",
    "3/F",
    "13/G",
    "E4/TH",
    "E5/TH1",
    "E6/TH2",
    "E3/TH3",
    "E2/THH",
    "E1/INT",
    "E1/FINT",
    "3E4",
    "3E4(B)",
    "5E3",
    "5E3/TH",
    "6E3(1)",
    "9E4",
    "8(2)E7",
    "FC5.1-2",
    "S.1-3",
    "9/L",
    "7/L",
    "8/P",
    "5/P",
    "6/G",
    "23/G",
    "2/L",
    "1/L",
    "4/L",
    "3/L",
]
MODIFIERS = [
    "TH",
    "TH1",
    "TH2",
    "TH3",
    "THH",
    "INT",
    "BINT",
    "UINT",
    "G",
    "L",
    "F",
    "P",
    "B",
    "BG",
    "BP",
    "BF",
    "BL",
    "BR",
    "BOOT",
    "COUR",
    "FO",
    "AP",
    "OBS",
    "U",
    "DP",
    "TP",
    "GDP",
    "GTP",
    "LDP",
    "LTP",
    "SH",
    "SF",
    "SH1",
    "SH2",
    "SH3",
    "SF1",
    "SH.1-2",
    "NDP",
    "FL",
    "FLE",
    "MREV",
    "UREV",
    "REV",
    "ND",
    "OA",
    "IF",
    "IFF",
    "FO",
    "TUR",
    "E1",
    "E2",
    "E3",
    "E4",
    "E5",
    "E6",
    "E7",
    "E8",
    "E9",
    "NR",
    "UR",
    "RBI",
    "NORBI",
    "PASS",
    "R",
    "R1",
    "R2",
    "R3",
    "HP",
    "SF8",
    "SH9",
    "SB",
    "CS",
    "WP",
    "PB",
    "F2",
    "F3",
    "F5",
    "F6",
    "F7",
    "F9",
    "FDP",
    "FINT",
    "BPDP",
    "BGDP",
    "BLDP",
    "BFDP",
    "BPTP",
]
LOCATIONS = [
    "1",
    "13",
    "13S",
    "15",
    "15S",
    "1S",
    "2",
    "23",
    "23F",
    "25",
    "25F",
    "2F",
    "2L",
    "2LF",
    "2R",
    "2RF",
    "3",
    "34",
    "34D",
    "34S",
    "3D",
    "3DF",
    "3F",
    "3L",
    "3S",
    "3SF",
    "4",
    "46",
    "4D",
    "4E1",
    "4M",
    "4MD",
    "4MS",
    "4S",
    "5",
    "56",
    "56D",
    "56S",
    "5D",
    "5DF",
    "5F",
    "5L",
    "5S",
    "5SF",
    "6",
    "6D",
    "6M",
    "6MD",
    "6MS",
    "6S",
    "7",
    "78",
    "78D",
    "78M",
    "78S",
    "78XD",
    "78XDW",
    "7D",
    "7DW",
    "7L",
    "7LD",
    "7LDF",
    "7LDW",
    "7LF",
    "7LM",
    "7LMF",
    "7LS",
    "7LSF",
    "7M",
    "7S",
    "8",
    "89",
    "89D",
    "89M",
    "89S",
    "89XD",
    "89XDW",
    "8D",
    "8LD",
    "8LM",
    "8LS",
    "8LXD",
    "8LXDW",
    "8M",
    "8RD",
    "8RM",
    "8RS",
    "8RXD",
    "8RXDW",
    "8S",
    "8XD",
    "8XDW",
    "9",
    "99",
    "9D",
    "9DW",
    "9L",
    "9LD",
    "9LDF",
    "9LDW",
    "9LF",
    "9LM",
    "9LMF",
    "9LS",
    "9LSF",
    "9M",
    "9S",
]
BASES = "B123H"
ADV_FLAGS = [
    "UR",
    "NR",
    "RBI",
    "NORBI",
    "TUR",
    "WP",
    "PB",
    "SB",
    "BK",
    "OA",
    "AP",
    "FO",
    "TH",
    "THH",
    "INT",
    "NP",
]
FIELD = [
    "1",
    "2",
    "3",
    "4",
    "5",
    "6",
    "7",
    "8",
    "9",
    "E1",
    "E2",
    "E3",
    "E4",
    "E5",
    "E6",
    "E7",
    "E8",
    "E9",
    "E",
    "TH",
    "T",
    "TH1",
    "TH3",
    "INT",
    "U",
    "UR",
    "NR",
]


def _fielding(rnd: random.Random) -> str:
    return "".join(rnd.choice("123456789E") for _ in range(rnd.randint(1, 4)))


def _advance(rnd: random.Random) -> str:
    a = rnd.choice(BASES)
    sep = rnd.choice("-----X")
    b = rnd.choice(BASES + "4" + "5")
    s = f"{a}{sep}{b}"
    for _ in range(rnd.choice([0, 0, 1, 1, 2, 3])):
        k = rnd.randrange(5)
        if k == 0:
            s += f"({_fielding(rnd)})"
        elif k == 1:
            s += f"({rnd.choice(ADV_FLAGS)})"
        elif k == 2:
            s += f"({rnd.choice(FIELD)}{rnd.choice(FIELD)})"
        elif k == 3:
            s += f"({rnd.choice(ADV_FLAGS)})({rnd.choice(ADV_FLAGS)})"
        else:
            s += f"({rnd.choice('0123456789')}{rnd.choice('B123H')})"
    return s


def _running(rnd: random.Random) -> str:
    """SB/CS/PO/POCS/POSB/DI chains with parenthesised credits, ``;`` joins and archaic SBH(UR)."""
    kinds = ["SB", "CS", "PO", "POCS", "POSB", "DI", "SBH", "CSH"]

    def one() -> str:
        k = rnd.choice(kinds)
        base = "" if k in ("SBH", "CSH") and rnd.random() < 0.7 else rnd.choice("1234H")
        if k in ("SBH", "CSH"):
            base = rnd.choice(["", "", "4", "3"])
        s = k + base
        for _ in range(rnd.choice([0, 1, 1, 2])):
            inner = rnd.choice(
                [
                    _fielding(rnd),
                    "UR",
                    "TUR",
                    "NR",
                    "E" + rnd.choice("123456789"),
                    _fielding(rnd)
                    + "/"
                    + rnd.choice(["TH", "TH1", "TH2", "TH3", "THH", "INT", "G", "F"]),
                    "E"
                    + rnd.choice("123456789")
                    + "/"
                    + rnd.choice(["TH", "THH", "INT", "TH3", "XX"]),
                    rnd.choice("123456789") + "E" + rnd.choice("123456789"),
                ]
            )
            s += f"({inner})"
        return s

    s = one()
    for _ in range(rnd.choice([0, 0, 1, 2])):
        s += rnd.choice([";", ";", "+", "/", ","]) + one()
    return s


def generate(rnd: random.Random, n: int) -> list[str]:
    plays = []
    for _ in range(n):
        s = rnd.choice(PRIMARY) if rnd.random() < 0.6 else _running(rnd)
        if rnd.random() < 0.1:
            s = (
                rnd.choice(["K", "W", "IW", "NP", "WP", "PB", "BK", "HP", "I", "S", "D", "T", "H"])
                + "+"
                + _running(rnd)
            )
        if rnd.random() < 0.15:
            s += rnd.choice(["", "!", "?", "#", "+", "-", "+-"])
        for _ in range(rnd.choice([0, 1, 1, 2, 2, 3, 4])):
            r = rnd.random()
            if r < 0.25:
                m = rnd.choice(["G", "F", "L", "P", "BG", "BP", "BF", "BL", "B"]) + rnd.choice(
                    LOCATIONS
                )
            else:
                m = rnd.choice(MODIFIERS if r < 0.8 else LOCATIONS)
            if rnd.random() < 0.1:
                m += rnd.choice("123456789")
            s += "/" + m
        if rnd.random() < 0.15:
            s += rnd.choice([".", "."])
        if rnd.random() < 0.6:
            s += "." + ";".join(_advance(rnd) for _ in range(rnd.choice([1, 1, 2, 3, 4])))
        if rnd.random() < 0.05:
            s = s.replace("/", rnd.choice(["/", "//", "/ ", ".", ","]), 1)
        plays.append(s)
    return plays
