"""Wraps the Chadwick Baseball Bureau's `cwevent`/`cwgame`/`cwbox` CLI tools
to parse Retrosheet's raw event and box-score files into structured records.

The CLI tools are used directly (already installed on this machine) rather
than the `pychadwick` pip package, which fails to build against modern CMake
(an upstream packaging bug) — see docs/DECISIONS.md ADR-004. All three tools
resolve each game's roster and team files (`{TTT}{year}.ROS`, `TEAM{year}`)
relative to their working directory rather than as explicit arguments, so
they must be run with cwd set to the directory the event files were
extracted into. Retrosheet's per-year regular-season zips already bundle the
matching roster/team files; several other archives (the Negro League event
file archive, and every box-score-only archive `cwbox` needs) do not, and
must have real ones supplied — see `write_team_file` and ADR-012. This is
Retrosheet's own documented requirement, not a Chadwick quirk: their BEVENT
documentation (retrosheet.org/datause.html) states plainly "you must have
the 'team' and the appropriate roster files in the same directory."
"""

import io
import re
import shutil
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path

import pandas as pd

CWEVENT_FIELDS = "0-96"
# Confirmed against the installed Chadwick 0.10.0 binary (`cwevent -d`):
# the real max extended-field number is 63, not 66. The old value of 66
# made every cwevent call requesting extended fields fail outright
# ("Invalid field spec ... max field number, 63") -- found when a real
# full-history retrosheet_event bootstrap died on the very first archive
# for exactly this reason (see docs/DECISIONS.md ADR-060). Chadwick's own
# field counts have changed across releases -- if this is ever run against
# a different installed version, re-verify with `cwevent -d` rather than
# trusting this value blindly.
CWEVENT_EXTENDED_FIELDS = "0-63"

REQUIRED_TOOLS = ("cwevent", "cwgame", "cwbox")

# Tried in order. A naive "first 4 digits anywhere" scan is ambiguous for
# team codes ending in a digit (e.g. "WS1") glued directly to a year, e.g.
# "WS11910.ROS" contains a run of 5 consecutive digits ("11910"). Shared by
# every connector that has to split one of Retrosheet's flat, multi-year
# archives into per-year directories (retrosheet_event.py, retrosheet_box.py).
_YEAR_PATTERNS = [
    re.compile(r"^(\d{4})"),  # event/deduced/box files: 1910BOS.EVA, 1910.EDA, 1900.EBN
    re.compile(r"^TEAM(\d{4})$"),  # TEAM1910
    re.compile(r"(\d{4})\.ROS$"),  # roster files: BOS1910.ROS, WS11910.ROS
]


def year_of(filename: str) -> int | None:
    for pattern in _YEAR_PATTERNS:
        match = pattern.search(filename)
        if match:
            return int(match.group(1))
    return None


def split_by_year(extract_dir: Path) -> dict[int, Path]:
    """Reorganizes a flat, multi-year archive's extracted contents into
    per-year subdirectories, matching the shape run_cwevent/run_cwgame/
    run_cwbox expect. Does not touch team/roster files beyond copying
    whatever's already there — callers that need a TEAM{year} file present
    (every one of them: see module docstring) are responsible for adding
    one afterward, since what "correct" means differs: an empty placeholder
    is fine for cwevent/cwgame (confirmed: their team-code fields come from
    the event file's own info records, not the team file), but run_cwbox
    needs a real, populated one (see write_team_file)."""
    year_dirs: dict[int, Path] = {}
    for f in extract_dir.iterdir():
        if not f.is_file():
            continue
        year = year_of(f.name)
        if year is None:
            continue
        year_dir = extract_dir / "by_year" / str(year)
        year_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(f, year_dir / f.name)
        year_dirs[year] = year_dir
    return year_dirs


INSTALL_HINT = (
    "build from source: https://github.com/chadwickbureau/chadwick "
    "(./configure && make && sudo make install) — the pip package `pychadwick` "
    "does not work here, see docs/DECISIONS.md ADR-004"
)


def missing_tools() -> list[str]:
    """Which of REQUIRED_TOOLS aren't on PATH, if any — used by
    retrosheet_event.health_check() so a missing system dependency shows up
    in `mlb doctor` before a multi-hour bootstrap, not as a cryptic
    FileNotFoundError partway through one."""
    return [tool for tool in REQUIRED_TOOLS if shutil.which(tool) is None]


def _run(tool: str, args: list[str], event_dir: Path) -> pd.DataFrame:
    try:
        result = subprocess.run(
            [tool, *args],
            cwd=event_dir,
            capture_output=True,
            text=True,
        )
    except FileNotFoundError as exc:
        raise RuntimeError(f"{tool} is not installed or not on PATH — {INSTALL_HINT}") from exc
    if result.returncode != 0:
        raise RuntimeError(f"{tool} failed in {event_dir}: {result.stderr.strip()}")
    if not result.stdout.strip():
        raise RuntimeError(f"{tool} produced no output in {event_dir}: {result.stderr.strip()}")
    return pd.read_csv(io.StringIO(result.stdout))


def _event_files(event_dir: Path) -> list[str]:
    # .EV? = full play-by-play; .ED? = deduced play-by-play (reconstructed from
    # newspaper accounts/box scores for seasons where the real record is
    # missing — same record format, same tools, see retrosheet.org/about.html
    # and the connector docstring in connectors/retrosheet_event.py).
    files = sorted(p.name for p in event_dir.glob("*.EV?")) + sorted(
        p.name for p in event_dir.glob("*.ED?")
    )
    if not files:
        raise RuntimeError(f"no event files (*.EV?/*.ED?) found in {event_dir}")
    return files


def run_cwevent(event_dir: Path, year: int) -> pd.DataFrame:
    """Parses every .EVA/.EVN/.EVF/.EVR/.EDA/.EDN file in event_dir into one play-level
    DataFrame. Requests the full field set (base 0-96, extended 0-66) rather
    than a curated subset — this lands in a raw layer table and should stay
    source-faithful and complete, not a hand-picked slice of what cwevent
    can produce."""
    args = ["-y", str(year), "-f", CWEVENT_FIELDS, "-x", CWEVENT_EXTENDED_FIELDS, "-n"]
    return _run("cwevent", [*args, *_event_files(event_dir)], event_dir)


def run_cwgame(event_dir: Path, year: int) -> pd.DataFrame:
    """Parses every .EVA/.EVN/.EVF/.EVR/.EDA/.EDN file in event_dir into one
    game-level DataFrame (date, umpires, attendance, lineups, final score, etc.)."""
    return _run("cwgame", ["-y", str(year), "-n", *_event_files(event_dir)], event_dir)


def write_team_file(dest_dir: Path, year: int, teams: list[tuple[str, str, str, str]]) -> None:
    """Writes a TEAM{year} file in Retrosheet's documented format: one line
    per team active that year, `team_id,league,city,nickname` — see
    retrosheet.org/eventfile.htm: "contains the team codes and team names
    in the particular season." Confirmed against a real bundled TEAM{year}
    file before relying on it. Needed for run_cwbox on archives that don't
    bundle their own (the Negro League and box-score-only archives) — see
    ADR-012."""
    path = dest_dir / f"TEAM{year}"
    with path.open("w") as f:
        for team_id, league, city, nickname in teams:
            f.write(f"{team_id},{league},{city},{nickname}\n")


def _box_files(event_dir: Path) -> list[str]:
    files = sorted(p.name for p in event_dir.glob("*.EB?"))
    if not files:
        raise RuntimeError(f"no box-score files (*.EB?) found in {event_dir}")
    return files


# cwbox emits bare "&" in attribute values for real historical names that
# contain one (e.g. team "WPS", "Western Pipe & Steel", 1943 Negro League
# data) instead of escaping it as "&amp;" — found by a real ParseError, not
# guessed. Matches an "&" not already starting a valid XML entity
# (&amp; &lt; &gt; &apos; &quot; or a numeric entity like &#39;) and escapes
# it; every other "&" is left alone since it's already valid.
_UNESCAPED_AMPERSAND_RE = re.compile(r"&(?!amp;|lt;|gt;|apos;|quot;|#\d+;|#x[0-9a-fA-F]+;)")


# cwbox -X emits seven supplementary event lists alongside the main
# boxscore — confirmed by generating real XML output and inspecting every
# top-level element cwbox actually produces, not by reading documentation:
# <doubles>/<double>, <triples>/<triple>, <homeruns>/<homerun>,
# <stolenbases>/<stolenbase>, <doubleplays>/<doubleplay>,
# <tripleplays>/<tripleplay>, <sacbunts>/<sacbunt>. Previously excluded
# entirely (see ADR-012's mention of "supplementary doubles, triples,
# stolen-base, and double-play lists") — the plural container name and
# singular child element name for each pair, so one generic loop handles
# all seven instead of one hand-written block per type.
SUPPLEMENTARY_LISTS = {
    "double": "doubles",
    "triple": "triples",
    "homerun": "homeruns",
    "stolenbase": "stolenbases",
    "doubleplay": "doubleplays",
    "tripleplay": "tripleplays",
    "sacbunt": "sacbunts",
}


def _parse_cwbox_xml(xml_text: str) -> dict[str, pd.DataFrame]:
    """cwbox's -X output is a bare sequence of <boxscore> elements, not one
    well-formed document (multiple root elements) — wrapped in a throwaway
    root before parsing. Returns one DataFrame per record type: a player can
    have more than one <fielding> block (position changes mid-game), so
    every child is collected, not just the first."""
    xml_text = _UNESCAPED_AMPERSAND_RE.sub("&amp;", xml_text)
    root = ET.fromstring(f"<games>{xml_text}</games>")
    games, batting, fielding, pitching = [], [], [], []
    supplementary: dict[str, list[dict]] = {child: [] for child in SUPPLEMENTARY_LISTS}
    for box in root.findall("boxscore"):
        game_id = box.attrib["game_id"]
        game_row = dict(box.attrib)
        linescore = box.find("linescore")
        if linescore is not None:
            game_row.update({f"linescore_{k}": v for k, v in linescore.attrib.items()})
        games.append(game_row)

        for players in box.findall("players"):
            team = players.attrib.get("team")
            for player in players.findall("player"):
                player_info = {
                    "game_id": game_id,
                    "team": team,
                    "id": player.attrib.get("id"),
                    "lname": player.attrib.get("lname"),
                    "fname": player.attrib.get("fname"),
                    "slot": player.attrib.get("slot"),
                    "seq": player.attrib.get("seq"),
                    "start_pos": player.attrib.get("pos"),
                }
                for bat in player.findall("batting"):
                    batting.append({**player_info, **bat.attrib})
                for fld in player.findall("fielding"):
                    fielding.append({**player_info, **fld.attrib})

        for pitching_block in box.findall("pitching"):
            team = pitching_block.attrib.get("team")
            for pitcher in pitching_block.findall("pitcher"):
                pitching.append({"game_id": game_id, "team": team, **pitcher.attrib})

        for child_tag, container_tag in SUPPLEMENTARY_LISTS.items():
            container = box.find(container_tag)
            if container is None:
                continue
            for entry in container.findall(child_tag):
                supplementary[child_tag].append({"game_id": game_id, **entry.attrib})

    return {
        "game": pd.DataFrame(games),
        "batting": pd.DataFrame(batting),
        "fielding": pd.DataFrame(fielding),
        "pitching": pd.DataFrame(pitching),
        **{name: pd.DataFrame(rows) for name, rows in supplementary.items()},
    }


# Real data-integrity errors in Retrosheet's own historical box files (found
# by a real failure, not anticipated): a game whose "dline" (defensive line)
# references a player never otherwise registered for that game. cwbox aborts
# ALL output for the files it was given when this happens — one bad game out
# of an entire year's file otherwise loses every good game alongside it.
# Historical Retrosheet box-score records can contain individual malformed
# games: missing roster players, impossible fielding positions, and similar
# source-record defects.  cwbox identifies the exact game on an ERROR line,
# then exits nonzero even when it has skipped the game itself.  The parser can
# safely isolate that one named game from its temporary copy and retry the
# rest of the official archive; an error without a game ID still fails loudly.
_BAD_GAME_ERROR_RE = re.compile(r"^ERROR: In (\S+?),", re.MULTILINE)
_BAD_GAME_WARNING_RE = re.compile(
    r"^WARNING: (?:In (\S+?), skipping invalid record|Sanity check fails for game (\S+), skipping)",
    re.MULTILINE,
)
_BOXSCORE_GAME_ID_RE = re.compile(r'<boxscore\s+game_id="([^"]+)"')


def _reported_bad_game_id(stderr: str) -> str | None:
    """Return the first source record cwbox explicitly says it skipped."""
    error = _BAD_GAME_ERROR_RE.search(stderr)
    if error is not None:
        return error.group(1)
    warning = _BAD_GAME_WARNING_RE.search(stderr)
    if warning is not None:
        return warning.group(1) or warning.group(2)
    return None


def _truncated_xml_game_id(xml_text: str) -> str | None:
    """Identify the enclosing game when cwbox emits malformed partial XML.

    This is used only after cwbox has already returned nonzero and its
    stderr names no bad record.  The output must fail our normal XML parser;
    then the last complete ``<boxscore game_id=...>`` before the parse error
    identifies the one source record to exclude from the temporary copy.
    """
    try:
        _parse_cwbox_xml(xml_text)
    except ET.ParseError as exc:
        line, column = exc.position
        lines = xml_text.splitlines(keepends=True)
        if line > len(lines):
            # ElementTree reports one line past the final physical line for
            # an abruptly truncated document.  The last opened boxscore is
            # still attributable and is the only candidate we may remove.
            offset = len(xml_text)
        else:
            offset = sum(len(part) for part in lines[: line - 1]) + column
        matches = list(_BOXSCORE_GAME_ID_RE.finditer(xml_text, 0, offset))
        return matches[-1].group(1) if matches else None
    return None


def _strip_game(text: str, game_id: str) -> str:
    """Removes one game's record block — from its `id,{game_id}` line up to
    (not including) the next `id,` line, or end of file — from a raw event/
    box-score file's text. No-op if game_id isn't in this particular file."""
    lines = text.splitlines(keepends=True)
    start = next((i for i, line in enumerate(lines) if line.startswith(f"id,{game_id}")), None)
    if start is None:
        return text
    end = next((i for i in range(start + 1, len(lines)) if lines[i].startswith("id,")), len(lines))
    return "".join(lines[:start] + lines[end:])


def _run_cwbox(event_dir: Path, year: int, files: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["cwbox", "-y", str(year), "-X", *files], cwd=event_dir, capture_output=True, text=True
    )


def run_cwbox(event_dir: Path, year: int) -> dict[str, pd.DataFrame]:
    """Parses every .EBA/.EBN/.EBR box-score file in event_dir into four
    DataFrames: game, batting, fielding, pitching. Unlike cwevent/cwgame,
    needs a *real*, populated TEAM{year} file (see write_team_file) — an
    empty placeholder produces blank team codes/names in cwbox's output,
    confirmed by testing both ways against real data, because box-score
    files don't carry `info,visteam,...`-style lines the way full event
    files do; cwevent/cwgame's team-code fields don't have this dependency."""
    files = _box_files(event_dir)
    result = _run_cwbox(event_dir, year, files)

    # A small number of Retrosheet's historical box-score records name a
    # player absent from that season's roster.  cwbox stops the whole yearly
    # file at the first such record.  Preserve the source artifact, but
    # exclude only the specifically reported unparseable game from this
    # temporary parser copy and continue.  More than one such record can
    # exist in a year, so retry until cwbox succeeds or reports a different
    # (therefore actionable) error.  The bound prevents an unexpected
    # upstream loop from becoming an unbounded mutation/retry cycle.
    attempts = 0
    max_bad_games = 100
    while result.returncode != 0 and attempts < max_bad_games:
        bad_game_id = _reported_bad_game_id(result.stderr)
        if bad_game_id is None and result.stdout.strip():
            bad_game_id = _truncated_xml_game_id(result.stdout)
        if bad_game_id is None:
            break
        removed = False
        for filename in files:
            path = event_dir / filename
            original = path.read_text()
            stripped = _strip_game(original, bad_game_id)
            if stripped != original:
                print(
                    f"chadwick_tools: dropping game {bad_game_id} from {filename} "
                    f"(cwbox: {result.stderr.strip().splitlines()[-1]})"
                )
                path.write_text(stripped)
                removed = True
        if not removed:
            break
        attempts += 1
        result = _run_cwbox(event_dir, year, files)

    if result.returncode != 0:
        raise RuntimeError(f"cwbox failed in {event_dir}: {result.stderr.strip()}")
    if not result.stdout.strip():
        raise RuntimeError(f"cwbox produced no output in {event_dir}: {result.stderr.strip()}")
    return _parse_cwbox_xml(result.stdout)
