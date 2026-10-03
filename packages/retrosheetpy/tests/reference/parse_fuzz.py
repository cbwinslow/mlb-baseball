# ruff: noqa: E501
"""Parser differential: ``cw_parse_event`` (C, under ASAN/UBSAN, one fork per play) vs ``parse_event``.

Build the harness:
    gcc -w -g -fsanitize=address,undefined,bounds-strict -fno-sanitize-recover=all -I $CW/cwlib -I $CW parse_dump.c $CW/cwlib/*.c -o parse_dump
Run (PD = the built harness; SEED then one or more Retrosheet event zips):
    PD=./parse_dump uv run --package retrosheetpy python parse_fuzz.py SEED ZIP...
Real play strings, randomly mutated copies and (GRAMMAR=N) N grammar-generated plays are compared on every parsed field. Known
differences are only garbled ``POCS(...`` plays, where the C writes out of bounds (undefined).
"""

import os
import random
import subprocess
import sys
import zipfile

from parse_grammar import generate
from retrosheetpy.cw.parse import parse_event
from retrosheetpy.records import is_event_filename


def esc(p):
    return "".join(f"\\x{ord(c):02x}" if ord(c) < 32 or ord(c) > 126 or c == "\\" else c for c in p)


def ints(k, a):
    return f"{k}=" + "".join(f"{x}," for x in a) + "|"


def dump(text):
    e, ok = parse_event(text)
    s = (
        f"ok={int(ok)}|type={int(e.event_type)}|"
        + ints("adv", e.advance[:4])
        + ints("rbi", e.rbi_flag[:4])
        + ints("fc", e.fc_flag[:4])
        + ints("muff", e.muff_flag[:4])
    )
    for i in range(4):
        s += f"play{i}={esc(e.play[i])}|"
    s += f"sh={e.sh_flag}|sf={e.sf_flag}|dp={e.dp_flag}|gdp={e.gdp_flag}|tp={e.tp_flag}|wp={e.wp_flag}|pb={e.pb_flag}|foul={e.foul_flag}|bunt={e.bunt_flag}|force={e.force_flag}|"
    s += ints("sb", e.sb_flag[1:4]) + ints("cs", e.cs_flag[1:4]) + ints("po", e.po_flag[1:4])
    s += f"fby={e.fielded_by}|np={e.num_putouts}|na={e.num_assists}|ne={e.num_errors}|nt={e.num_touches}|"
    s += (
        ints("put", e.putouts[:3])
        + ints("ast", e.assists[:10])
        + ints("err", e.errors[:10])
        + ints("tch", e.touches[:19])
    )
    s += (
        "et="
        + "".join(e.error_types[:10])
        + f"|bbt={ord(e.batted_ball_type)}|hl={esc(e.hit_location)}"
    )
    return s


def compare(
    corpus: list[str], harness: str, diffs_file: str | None = None
) -> tuple[int, list[str], int]:
    """Run ``harness`` (the C parser) and the port over ``corpus``; (compared, differences, ub-skipped).
    Each difference is a printable block: the play, the C dump and the port dump."""
    r = subprocess.run(
        [harness],
        input=("\n".join(corpus) + "\n").encode("latin-1"),
        capture_output=True,
        env={**os.environ, "ASAN_OPTIONS": "detect_leaks=0"},
        check=False,
    )
    it = iter(r.stdout.decode("latin-1").split("\n"))  # an ``UB`` line replaces a play's dump
    diffs: list[str] = []
    ub = 0
    for text in corpus:
        c = next(it)
        if c == "UB":
            ub += 1
            continue
        p = dump(text)
        if p != c:
            block = f"{text!r}\n C  {c}\n Py {p}\n"
            diffs.append(block)
            if diffs_file:
                with open(diffs_file, "a") as fh:
                    fh.write(block)
    return len(corpus) - ub, diffs, ub


def real_plays(zips: list[str]) -> list[str]:
    plays = set()
    for z in zips:
        with zipfile.ZipFile(z) as zf:
            for name in zf.namelist():
                if not is_event_filename(name):
                    continue
                for line in zf.read(name).decode("latin-1").splitlines():
                    if line.startswith("play,"):
                        parts = line.split(",", 6)
                        if len(parts) == 7:
                            plays.add(parts[6])
    return sorted(plays)


def mutate(rnd: random.Random, plays: list[str]) -> list[str]:
    alphabet = "0123456789()/.-;#+!?*ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    muts = []
    for _ in range(len(plays)):
        t = list(rnd.choice(plays))
        for _ in range(rnd.randint(1, 4)):
            k = rnd.randrange(3)
            pos = rnd.randrange(len(t) + 1)
            if k == 0:
                t.insert(pos, rnd.choice(alphabet))
            elif k == 1 and t:
                del t[min(pos, len(t) - 1)]
            elif t:
                t[min(pos, len(t) - 1)] = rnd.choice(alphabet)
        muts.append("".join(t))
    return muts


def main() -> None:
    plays = real_plays(sys.argv[2:])
    rnd = random.Random(int(sys.argv[1]))
    muts = mutate(rnd, plays)
    gram = generate(rnd, int(os.environ["GRAMMAR"])) if os.environ.get("GRAMMAR") else []
    corpus = gram if os.environ.get("ONLY_GRAMMAR") else plays + muts + gram
    print("corpus", len(plays), "real +", len(muts), "mutated +", len(gram), "grammar", flush=True)
    compared, diffs, ub = compare(corpus, os.environ["PD"], os.environ.get("DIFFS"))
    for block in diffs[:8]:
        print("DIFF", block, end="")
    print("compared", compared, "diffs", len(diffs), "ub-skipped", ub)


if __name__ == "__main__":
    main()
