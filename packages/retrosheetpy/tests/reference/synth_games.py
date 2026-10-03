# ruff: noqa: E501
"""Synthetic Retrosheet event files for the differential checks (see ``synth_check.py``).

Real data never reaches some Chadwick code: ``padj``/``badj`` hand records, switch hitters against
pitchers of known / unknown hand, backward runner advances (``3-2``, ``3-1``, ``2-1``), pinch
hitters and runners, roster-less players, ``ladj``/``presadj``/``radj`` records, DH games, comments.
These games are random but well formed, built from the parser's own token vocabulary.
"""

import random

YEAR = 2020
# (event text, outs the play adds)
PLAYS = [
    ("K", 1),
    ("K23", 1),
    ("W", 0),
    ("IW", 0),
    ("HP", 0),
    ("S8", 0),
    ("S7", 0),
    ("D7", 0),
    ("D9", 0),
    ("T9", 0),
    ("HR", 0),
    ("HR/78XD", 0),
    ("8/F", 1),
    ("7/L", 1),
    ("63/G", 1),
    ("43/G", 1),
    ("3/G", 1),
    ("54(1)/FO/G", 1),
    ("5/P", 1),
    ("2/F/FL", 1),
    ("E6/TH", 0),
    ("E5", 0),
    ("FC5", 0),
    ("FC6.2-3", 0),
    ("64(1)3/GDP", 2),
    ("S8.1-3", 0),
    ("S7.2-H;1-3", 0),
    ("D8.1-H", 0),
    ("SB2", 0),
    ("SB3", 0),
    ("SBH", 0),
    ("CS2(26)", 1),
    ("CS3(25)", 1),
    ("WP.1-2", 0),
    ("PB.2-3", 0),
    ("BK.1-2;2-3", 0),
    ("NP", 0),
    ("DI.1-2", 0),
    ("OA.1-3", 0),
    ("PO1(13)", 1),
    ("POCS2(14)", 1),
    ("K+WP.B-1", 0),
    ("K+SB2", 0),
    ("W+WP.2-3", 0),
    ("BK", 0),
    ("C/E2.1-2", 0),
    ("S9/BG.3-H(NR)", 0),
    ("DGR", 0),
    ("S6/G.3-2", 0),
    ("S8.3-1", 0),
    ("D7.2-1", 0),
    ("NP.3-2", 0),
    ("8/F.3-H;1-3", 1),
    ("FC3.3-2", 0),
    ("S5.2-1;3-2", 0),
    ("46(1)3/GDP/SH.2-3", 2),
    ("1/BG.B-1", 0),
    ("FLE2", 0),
    ("99/F", 1),
    ("3(B)/BG/SH.1-2", 1),
    ("S.1-2(E5)", 0),
    ("S8.1-2(UR)(NR)", 0),
    ("54(1)/FO/G.B-1", 1),
    ("5(2)/FO.1-2", 1),
    ("64(1)/FO.2XH(E5)", 1),
    ("FC5.1X2(65);B-1", 1),
    ("FC5.3XH(25);B-1", 1),
    ("S8.2XH(84);1-3", 1),
    ("S8.1X3(85)", 1),
    ("S9.3XH(92);1-3;B-2", 1),
    ("K+WP.B-1;1-2", 0),
    ("K+PB.B-1;2-3", 0),
    ("K+SB2.B-1", 0),
    ("FC3/G.2XH(3E2);B-1", 0),
    ("S8.3-H(NORBI)", 0),
    ("HR.1-H(NORBI)", 0),
    ("S8.3-H(RBI)", 0),
    ("S8.3-H;2-H(NORBI)", 0),
    ("D9.2-H(RBI);1-H", 0),
    ("W.3-H(RBI)", 0),
    ("S8.3-H(UR)(NR)", 0),
    ("S7.3-H(TUR)", 0),
]
HANDS = "LRB?"


def _pid(team: str, n: int) -> str:
    return f"{team.lower()}plr{n:02d}"


def _simulate(
    rnd: random.Random, bases: dict[int, int], slot: int
) -> tuple[str, int, dict[int, int]]:
    """A valid play for the current runners and batter slot: (event text, outs added, new bases).
    Runner positions come from ``bases`` (base -> lineup slot)."""
    runners = sorted(bases, reverse=True)
    new: dict[int, int] = {}
    kind = rnd.choices(
        [
            "k",
            "go",
            "fo",
            "bb",
            "hit",
            "hr",
            "e",
            "dp",
            "fc",
            "sb",
            "cs",
            "po",
            "wp",
            "bk",
            "back",
            "np",
        ],
        [10, 10, 10, 8, 14, 2, 3, 3, 2, 3, 2, 1, 2, 1, 1, 1],
    )[0]
    if kind == "dp" and (1 not in bases):
        kind = "go"
    if kind == "fc" and (1 not in bases):
        kind = "go"
    if kind in ("sb", "cs") and not any(b + 1 not in bases and b < 3 for b in bases):
        kind = "hit"
    if kind == "po" and not bases:
        kind = "k"
    if kind in ("wp", "bk", "back") and not bases:
        kind = "k"
    if kind == "back":
        movable = [b for b in bases if b > 1 and (b - 1) not in bases]
        if not movable:
            kind = "wp"
    if kind in ("wp", "bk"):
        adv = []
        for b in runners:
            to = b + 1
            if to > 3:
                to = 4
            if to in new:
                to = b
            if to != b:
                adv.append(f"{b}-{'H' if to == 4 else to}")
                if to < 4:
                    new[to] = bases[b]
            else:
                new[b] = bases[b]
        text = ("WP" if kind == "wp" else "BK") + ("." + ";".join(adv) if adv else "")
        return text, 0, new
    if kind == "back":
        b = rnd.choice([b for b in bases if b > 1 and (b - 1) not in bases])
        for r in runners:
            new[b - 1 if r == b else r] = bases[r]
        return f"NP.{b}-{b - 1}" if rnd.random() < 0.5 else f"BK.{b}-{b - 1}", 0, new
    if kind == "np":
        return "NP", 0, dict(bases)
    if kind == "k":
        return rnd.choice(["K", "K23"]), 1, dict(bases)
    if kind == "go":
        return rnd.choice(["63/G", "43/G", "3/G", "54/G", "1/G"]), 1, dict(bases)
    if kind == "fo":
        text = rnd.choice(["8/F", "7/L", "9/F", "5/P", "2/F/FL"])
        if 3 in bases and rnd.random() < 0.5:
            n = dict(bases)
            n.pop(3)
            return text + ".3-H", 1, n
        return text, 1, dict(bases)
    if kind == "bb":
        chain = 0
        while chain + 1 in bases:
            chain += 1
        new = {(b + 1 if b <= chain else b): v for b, v in bases.items()}
        new[1] = slot
        adv = [f"{b}-{'H' if b == 3 else b + 1}" for b in sorted(bases, reverse=True) if b <= chain]
        text = rnd.choice(["W", "IW", "HP"]) + ("." + ";".join(adv) if adv else "")
        return text, 0, {b: v for b, v in new.items() if b < 4}
    if kind in ("hit", "hr", "e", "fc"):
        if kind == "hr":
            adv = [f"{b}-H" for b in runners]
            return "HR" + ("." + ";".join(adv) if adv else ""), 0, {}
        batter_to = {"hit": rnd.choice([1, 1, 1, 2, 3]), "e": 1, "fc": 1}[kind]
        if kind == "fc":
            n = dict(bases)
            n.pop(1)
            n[1] = slot
            return "64(1)/FO/G", 1, n
        new = {batter_to: slot}
        adv = []
        taken = {batter_to}
        for b in runners:
            to = min(4, b + batter_to + rnd.choice([0, 0, 1]))
            while to in taken and to < 4:
                to -= 1
            if to <= b and b not in taken:
                to = b
            if to != b:
                adv.append(f"{b}-{'H' if to == 4 else to}")
            if to < 4:
                new[to] = bases[b]
                taken.add(to)
            if b == to:
                taken.add(b)
        head = {"hit": "SDT"[batter_to - 1] + rnd.choice("789"), "e": "E6"}[kind]
        return head + ("." + ";".join(adv) if adv else ""), 0, new
    if kind == "dp":
        n = dict(bases)
        n.pop(1)
        text = "64(1)3/GDP"
        return text, 2, n
    if kind == "sb":
        b = rnd.choice([b for b in bases if b < 3 and b + 1 not in bases])
        n = dict(bases)
        n[b + 1] = n.pop(b)
        return f"SB{b + 1}", 0, n
    if kind == "cs":
        b = rnd.choice([b for b in bases if b < 3 and b + 1 not in bases])
        n = dict(bases)
        n.pop(b)
        return f"CS{b + 1}(26)", 1, n
    if kind == "po":
        b = rnd.choice(list(bases))
        n = dict(bases)
        n.pop(b)
        return f"PO{b}(13)", 1, n
    raise AssertionError(kind)


def make_game(
    rnd: random.Random, game_no: int, vis: str, home: str, chaos: float = 0.0
) -> tuple[str, dict[str, int]]:
    """One game's records and the players it names (for rosters)."""
    usedh = rnd.random() < 0.4
    lines = [
        f"id,{home}{YEAR}0701{game_no}",
        "version,2",
        f"info,visteam,{vis}",
        f"info,hometeam,{home}",
        f"info,date,{YEAR}/07/01",
        f"info,number,{game_no}",
        f"info,usedh,{'true' if usedh else 'false'}",
        f"info,pitches,{rnd.choice(['pitches', 'count', 'none'])}",
        "info,site,TST01",
    ]
    if rnd.random() < 0.08:
        lines.append("info,htbf,true")
    suspended = rnd.random() < 0.15
    people: dict[str, int] = {}
    lineup: dict[int, list[str]] = {0: [], 1: []}
    holder: dict[int, dict[int, int]] = {
        0: {},
        1: {},
    }  # fielding position -> lineup slot (0: the pitcher)
    bench = {0: 20, 1: 20}
    for team, tid in ((0, vis), (1, home)):
        positions = list(range(2, 10))
        rnd.shuffle(positions)
        slots = [(positions[i], i) for i in range(8)]
        if usedh:
            slots.append((10, 8))
        else:
            slots.append((1, 8))
        order = [(p, s) for p, s in slots]
        rnd.shuffle(order)
        for slot, (pos, _) in enumerate(order, 1):
            pid = _pid(tid, slot)
            lineup[team].append(pid)
            holder[team][pos] = slot
            people[pid] = team
            lines.append(f'start,{pid},"Player {slot} {tid}",{team},{slot},{pos}')
        if usedh:
            pit = _pid(tid, 30)
            holder[team][1] = 0
            people[pit] = team
            lines.append(f'start,{pit},"Pitcher {tid}",{team},0,1')
    batter = [0, 0]
    pending: dict[int, dict[int, str]] = {0: {}, 1: {}}  # slot -> pinch player awaiting a position
    for inning in range(1, rnd.randint(2, 10)):
        for team in (0, 1):
            outs = 0
            bases: dict[int, int] = {}
            for pslot, pnew in sorted(pending[1 - team].items()):
                ppos = next(k for k, v in holder[1 - team].items() if v == pslot)
                lines.append(f'sub,{pnew},"Bench {pnew}",{1 - team},{pslot},{ppos}')
            pending[1 - team].clear()
            while outs < 3:
                r = rnd.random()
                if r < 0.07 and any(x.startswith("play,") for x in lines):  # substitution
                    kind = rnd.choice(["ph", "pr", "def", "def", "dhloss", "dhpitch", "dhback"])
                    defteam = 1 - team
                    if kind == "dhback" and usedh:
                        # the starting pitcher (outside the batting order) comes in at a slot
                        slot = rnd.randint(1, 9)
                        new = _pid(vis if team == 0 else home, 30)
                        lineup[team][slot - 1] = new
                        lines.append(
                            f'sub,{new},"Pitcher {new}",{team},{slot},{rnd.choice([1, 11])}'
                        )
                        continue
                    if kind in ("dhloss", "dhpitch"):
                        # a pitcher takes a fielder's place in the batting order (the DH is lost)
                        # or pinch hits for the DH; the old DH slot is cleared
                        slot = rnd.randint(1, 9)
                        new = _pid(vis if team == 0 else home, bench[team])
                        bench[team] += 1
                        people[new] = team
                        lineup[team][slot - 1] = new
                        pos = 1 if kind == "dhloss" else 11
                        lines.append(f'sub,{new},"Bench {new}",{team},{slot},{pos}')
                        continue
                    if kind == "pr" and not bases:
                        continue
                    if kind == "ph":
                        slot = batter[team] % 9
                        new = _pid(vis if team == 0 else home, bench[team])
                        bench[team] += 1
                        people[new] = team
                        lineup[team][slot] = new
                        lines.append(f'sub,{new},"Bench {new}",{team},{slot + 1},11')
                        if slot + 1 in holder[team].values():
                            pending[team][slot + 1] = new
                    elif kind == "pr" and bases:
                        base = rnd.choice(sorted(bases))
                        slot = bases[base]
                        new = _pid(vis if team == 0 else home, bench[team])
                        bench[team] += 1
                        people[new] = team
                        lineup[team][slot] = new
                        lines.append(f'sub,{new},"Runner {new}",{team},{slot + 1},12')
                        if slot + 1 in holder[team].values():
                            pending[team][slot + 1] = new
                    else:
                        pos = rnd.choice(sorted(holder[defteam]))
                        slot = holder[defteam][pos]
                        pending[defteam].pop(slot, None)
                        new = _pid(vis if defteam == 0 else home, bench[defteam])
                        bench[defteam] += 1
                        people[new] = defteam
                        if slot:
                            lineup[defteam][slot - 1] = new
                        lines.append(f'sub,{new},"Fielder {new}",{defteam},{slot},{pos}')
                elif r < 0.2:
                    k = rnd.randrange(7)
                    who = rnd.choice(list(people))
                    if k == 0:
                        lines.append(f"badj,{who},{rnd.choice(HANDS)}")
                    elif k == 1:
                        lines.append(f"padj,{who},{rnd.choice(HANDS)}")
                    elif k == 2:
                        lines.append(f"ladj,{team},{rnd.randint(1, 9)}")
                    elif k == 3:
                        lines.append(f"presadj,{who},{rnd.randint(1, 3)}")
                    elif k == 4:
                        lines.append(f"radj,{who},{rnd.randint(1, 3)}")
                    elif k == 5:
                        lines.append(f'com,"comment {rnd.randint(0, 99)}"')
                    else:
                        lines.append(f"padj,{who},")
                slot = batter[team] % 9
                who = lineup[team][slot]
                batter[team] += 1
                if rnd.random() < chaos:
                    text, add = rnd.choice(PLAYS)
                    bases = {}
                else:
                    text, add, bases = _simulate(rnd, bases, slot)
                count = rnd.choice(["??", "00", "32", "12", "01"])
                pitches = rnd.choice(["", "", "BCFX", "CBSX", ".>B*X"])
                lines.append(f"play,{inning},{team},{who},{count},{pitches},{text}")
                outs += add
                if rnd.random() < 0.05:
                    lines.append(f'com,"$ note {rnd.randint(0, 99)}"')
                if suspended:
                    lines.append(f'com,"suspended,{YEAR}/06/{rnd.randint(10, 28)}"')
                    suspended = False
    for pid in rnd.sample(sorted(people), min(3, len(people))):
        lines.append(f"data,er,{pid},{rnd.randint(0, 4)}")
    return "\n".join(lines) + "\n", people


def make_boxscore_game(
    rnd: random.Random, game_no: int, vis: str, home: str
) -> tuple[str, dict[str, int]]:
    """A "boxscore event file" game: starters plus ``stat`` records, no plays."""
    lines = [
        f"id,{home}{YEAR}0702{game_no}",
        "version,2",
        f"info,visteam,{vis}",
        f"info,hometeam,{home}",
        f"info,date,{YEAR}/07/02",
        f"info,number,{game_no}",
        "info,usedh,false",
        "info,site,TST01",
    ]
    people: dict[str, int] = {}
    n = lambda hi: rnd.randint(0, hi)  # noqa: E731
    for team, tid in ((0, vis), (1, home)):
        positions = list(range(1, 10))
        rnd.shuffle(positions)
        ids: list[str] = []
        for slot in range(1, 10):
            pid = _pid(tid, slot)
            ids.append(pid)
            people[pid] = team
            lines.append(f'start,{pid},"Player {slot} {tid}",{team},{slot},{positions[slot - 1]}')
        for slot, pid in enumerate(list(ids), 1):
            stats = ",".join(str(n(3)) for _ in range(17))
            lines.append(f"stat,bline,{pid},{team},{slot},1,{stats}")
            if rnd.random() < 0.3:
                new = _pid(tid, 40 + slot)
                people[new] = team
                stats = ",".join(str(n(2)) for _ in range(17))
                lines.append(f"stat,bline,{new},{team},{slot},{rnd.randint(2, 3)},{stats}")
                lines.append(
                    f"stat,{rnd.choice(['phline', 'prline'])},{new},{rnd.randint(5, 9)},{team}"
                )
                ids.append(new)
        pitcher = ids[positions.index(1)]
        stats = ",".join(str(n(6)) for _ in range(17))
        lines.append(f"stat,pline,{pitcher},{team},1,{stats}")
        relief = _pid(tid, 50)
        people[relief] = team
        stats = ",".join(str(n(4)) for _ in range(17))
        lines.append(f"stat,pline,{relief},{team},2,{stats}")
        for seq, pid in enumerate(ids[:9], 1):
            stats = ",".join(str(n(5)) for _ in range(7))
            lines.append(f"stat,dline,{pid},{team},1,{positions[seq - 1]},{stats}")
        if rnd.random() < 0.3:
            lines.append(
                f"stat,dline,{rnd.choice(ids)},{team},2,{rnd.randint(1, 9)},{n(9)},{n(4)},{n(3)},{n(1)},{n(1)},0,0"
            )
        lines.append(f"stat,tline,{team},{n(9)},{n(5)},{n(2)},{n(1)}")
        lines.append("line," + str(team) + "," + ",".join(str(n(3)) for _ in range(9)))
        if rnd.random() < 0.4:
            lines.append(f"event,dpline,{team},{ids[0]},{ids[1]}")
        if rnd.random() < 0.2:
            lines.append(f"event,tpline,{team},{ids[0]},{ids[1]},{ids[2]}")
    lines.append(f"data,er,{ids[0]},{n(3)}")
    return "\n".join(lines) + "\n", people


def make_file(seed: int) -> tuple[bytes, dict[str, bytes]]:
    """An event file of several games, plus team and roster files with mixed hands (and some
    players missing from the rosters, so names come out empty)."""
    rnd = random.Random(seed)
    vis, home = rnd.sample(["AAA", "BBB", "CCC", "DDD"], 2)
    text = ""
    everyone: dict[str, int] = {}
    box = rnd.random() < 0.2
    chaos = rnd.choice([0.0, 0.0, 0.0, 0.05, 0.5])
    for g in range(rnd.randint(1, 4)):
        if box:
            body, people = make_boxscore_game(rnd, g, vis, home)
        else:
            body, people = make_game(rnd, g, vis, home, chaos)
        text += body
        everyone.update(people)
    support: dict[str, bytes] = {}
    if rnd.random() < 0.8:
        support[f"TEAM{YEAR}"] = f"{vis},A,City of {vis},Nick\n{home},N,{home} Town,Club\n".encode()
        for tid, team in ((vis, 0), (home, 1)):
            rows = ""
            for pid, t in sorted(everyone.items()):
                if t == team and rnd.random() < 0.85:
                    rows += f"{pid},Last{pid[4:]},{'' if rnd.random() < 0.3 else 'First'},{rnd.choice(HANDS)},{rnd.choice('LR?')},{tid},X\n"
            support[f"{tid}{YEAR}.ROS"] = rows.encode()
    return text.encode(), support
