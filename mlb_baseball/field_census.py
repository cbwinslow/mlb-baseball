"""Read-only raw-to-core-to-gold field lineage census.

The census is intentionally an inventory, not a schema-promoter.  It makes
unmapped raw fields visible with their database evidence so a researcher can
decide whether a narrow, point-in-time-safe gold family is warranted.
"""

# ruff: noqa: E501

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import psycopg
from psycopg import sql

from mlb_baseball.db import get_connection


@dataclass(frozen=True)
class SourceContract:
    provider: str
    grain: str
    natural_key: str
    event_time: str
    availability: str
    rights: str


@dataclass(frozen=True)
class Mapping:
    destination: str
    classification: str
    reason: str
    candidate_family: str | None = None
    leakage_risk: str = "review feature cutoff before use"
    validation: str = "document grain, join, null policy, and PIT cutoff"


_DEFAULT = SourceContract(
    "source-specific raw landing",
    "provider record",
    "see connector/parser contract",
    "source-specific or unavailable",
    "landing time is not automatically pregame availability",
    "see docs/SOURCE_RIGHTS.md",
)

# These describe tables, not a promise that every field within them is a
# feature. Unknown business fields remain visible as needs_research instead of
# being silently called dropped data.
_SOURCE_CONTRACTS: dict[str, SourceContract] = {
    "mlb_schedule": SourceContract(
        "MLB Stats API",
        "schedule observation (history retained)",
        "game_id + observed schedule state",
        "game_datetime when supplied",
        "scheduled start; revisions remain raw",
        "local_research only",
    ),
    "mlb_playbyplay": SourceContract(
        "MLB Stats API",
        "game/play observation",
        "game_pk + play/event identity",
        "play timestamp/order when supplied",
        "live or postgame unless captured before cutoff",
        "local_research only",
    ),
    "statcast_pitch": SourceContract(
        "Baseball Savant/Statcast",
        "tracked pitch",
        "provider pitch/game identity",
        "pitch event time",
        "post-pitch; historical values need a declared cutoff",
        "local_research only",
    ),
    "retrosheet_event": SourceContract(
        "Retrosheet",
        "play/event record",
        "game_id + event number",
        "event order",
        "historical descriptive; not live pregame",
        "public_safe with attribution",
    ),
    "retrosheet_gameinfo": SourceContract(
        "Retrosheet",
        "completed game",
        "gid",
        "game date",
        "postgame archive",
        "public_safe with attribution",
    ),
    "bref_batting": SourceContract(
        "Baseball-Reference",
        "player-season final line",
        "mlbid + season",
        "season",
        "final-season/reporting, not pregame",
        "local_research only",
    ),
    "bref_pitching": SourceContract(
        "Baseball-Reference",
        "player-season final line",
        "mlbid + season",
        "season",
        "final-season/reporting, not pregame",
        "local_research only",
    ),
    "bref_war_batting": SourceContract(
        "Baseball-Reference",
        "player-season/stint WAR",
        "player + season + stint",
        "season",
        "final-season/reporting, not pregame",
        "local_research only",
    ),
    "bref_war_pitching": SourceContract(
        "Baseball-Reference",
        "player-season/stint WAR",
        "player + season + stint",
        "season",
        "final-season/reporting, not pregame",
        "local_research only",
    ),
    "lahman_teams": SourceContract(
        "Lahman",
        "team-season final line",
        "teamIDretro + yearID",
        "season",
        "final-season/reporting, not pregame",
        "license review required for public use",
    ),
    "mlb_probable": SourceContract(
        "MLB Stats API",
        "scheduled probable starter snapshot",
        "game_pk + side + captured state",
        "schedule/capture time",
        "candidate only if capture is before game cutoff",
        "local_research only",
    ),
    "mlb_venue": SourceContract(
        "MLB Stats API",
        "venue catalog row",
        "venue id",
        "catalog revision",
        "descriptive; join to scheduled game before cutoff",
        "local_research only",
    ),
    "statcast_oaa": SourceContract(
        "Baseball Savant/Statcast",
        "player-season-position aggregate",
        "player + season + position",
        "season",
        "final-season/descriptive unless prior snapshot exists",
        "local_research only",
    ),
    "statcast_sprint_speed": SourceContract(
        "Baseball Savant/Statcast",
        "player-season aggregate",
        "player + season",
        "season",
        "final-season/descriptive unless prior snapshot exists",
        "local_research only",
    ),
    "statcast_framing": SourceContract(
        "Baseball Savant/Statcast",
        "catcher-season aggregate",
        "player + season",
        "season",
        "final-season/descriptive unless prior snapshot exists",
        "local_research only",
    ),
    "polymarket_snapshot": SourceContract(
        "Polymarket",
        "timestamped price observation",
        "market/outcome + captured_at",
        "captured_at",
        "valid only strictly before game start",
        "local_research only",
    ),
    "kalshi_snapshot": SourceContract(
        "Kalshi",
        "timestamped price observation",
        "market + captured_at",
        "captured_at",
        "valid only strictly before game start",
        "local_research only",
    ),
}

_MAPPINGS: dict[tuple[str, str], Mapping] = {
    ("mlb_schedule", "game_id"): Mapping(
        "core.game.game_pk; gold.game_feature.mlb_game_pk",
        "canonical_core",
        "canonical MLB game identity after schedule-history collapse",
    ),
    ("mlb_schedule", "game_datetime"): Mapping(
        "gold.game_feature.feature_cutoff_at",
        "existing_gold",
        "declared pregame cutoff for game_base_v1",
        "game_base_v1",
        "must retain schedule revision semantics",
    ),
    ("mlb_schedule", "home_id"): Mapping(
        "core.game.home_team_id; gold.game_feature.home_team_id",
        "canonical_core",
        "resolved provider team identity",
    ),
    ("mlb_schedule", "away_id"): Mapping(
        "core.game.away_team_id; gold.game_feature.away_team_id",
        "canonical_core",
        "resolved provider team identity",
    ),
    ("mlb_schedule", "game_num"): Mapping(
        "core.game.game_number; gold.game_feature.game_number",
        "canonical_core",
        "doubleheader ordering after source-specific normalization",
    ),
    ("statcast_pitch", "game_pk"): Mapping(
        "core.pitch.source_game_pk; core.pitch.game_id",
        "canonical_core",
        "provider key retained even when crosswalk is unresolved",
    ),
    ("retrosheet_event", "game_id"): Mapping(
        "core.play.game_id",
        "canonical_core",
        "Retrosheet game identity resolves canonical play when available",
    ),
    ("mlb_playbyplay", "game_pk"): Mapping(
        "core.play.game_id",
        "canonical_core",
        "MLB game identity resolves canonical play when available",
    ),
    ("bref_war_batting", "war"): Mapping(
        "core.player_war; gold.player_season",
        "existing_gold",
        "provider-specific final-season WAR retained for reporting",
        None,
        "leaks if used as current-season pregame input",
        "build entering-game WAR separately or use prior completed season",
    ),
    ("bref_war_pitching", "war"): Mapping(
        "core.player_war; gold.player_season",
        "existing_gold",
        "provider-specific final-season WAR retained for reporting",
        None,
        "leaks if used as current-season pregame input",
        "build entering-game WAR separately or use prior completed season",
    ),
    ("retrosheet_park", "park_id"): Mapping(
        "core.venue.retro_park_id", "canonical_core", "Retrosheet venue identity"
    ),
    ("mlb_venue", "id"): Mapping(
        "core.venue.mlb_venue_id",
        "canonical_core",
        "MLB venue identity enriches exact matched venue",
    ),
    ("mlb_standing", "team_id"): Mapping(
        "core.standing.team_id", "canonical_core", "provider team identity resolves season standing"
    ),
    ("mlb_team_history", "id"): Mapping(
        "core.team.mlb_team_id",
        "unconformed_candidate",
        "candidate provider team identity requires source coverage/reconciliation review",
    ),
}


def _classification(table: str, column: str) -> Mapping:
    mapped = _MAPPINGS.get((table, column))
    if mapped is not None:
        return mapped
    if column.startswith("_"):
        return Mapping(
            "raw only",
            "raw_only_by_design",
            "loader scope/provenance metadata",
            None,
            "not a baseball measurement",
            "retain for replay and source lineage",
        )
    if "deprecated" in column:
        return Mapping(
            "raw only",
            "invalid_or_low_value",
            "provider marks the field deprecated",
            None,
            "obsolete source definition",
            "do not admit without a replacement contract",
        )
    contract = _SOURCE_CONTRACTS.get(table, _DEFAULT)
    if "final-season" in contract.availability or "postgame" in contract.availability:
        return Mapping(
            "raw/reporting only",
            "raw_only_by_design",
            f"{contract.availability}; preserve without treating as pregame input",
            None,
            "postgame/final-season leakage",
            "require prior snapshot or entering-game reconstruction",
        )
    if table.startswith(("bref_", "lahman_")):
        return Mapping(
            "raw/reporting only",
            "raw_only_by_design",
            "final/historical source record retained for reporting and reconstruction",
            None,
            "final-season leakage until reconstructed",
            "build a prior-event or as-of version",
        )
    if table.startswith("statcast_") and table != "statcast_pitch":
        return Mapping(
            "raw only",
            "raw_only_by_design",
            "provider aggregate requires coverage and historical-availability review",
            None,
            "season aggregate may leak current outcome",
            "prove as-of availability or recompute from pitches",
        )
    if table in {
        "retrosheet_box",
        "retrosheet_gamelog",
        "retrosheet_schedule",
        "retrosheet_transaction",
    }:
        return Mapping(
            "raw only",
            "raw_only_by_design",
            "source-faithful historical record retained at provider grain",
            None,
            "postgame/history timing varies",
            "derive an explicit prior-event feature family",
        )
    return Mapping(
        "no declared destination",
        "needs_research",
        "business field is landed but has no approved canonical/PIT feature contract",
        "candidate queue",
        "availability and join semantics unproven",
        "research formula, identity, coverage, and PIT test required",
    )


def _relations(cur: psycopg.Cursor) -> list[tuple[str, float]]:
    cur.execute(
        """
        SELECT c.relname, c.reltuples
        FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname = 'raw' AND c.relkind IN ('r', 'p')
        ORDER BY c.relname
        """
    )
    return [(str(name), float(rows)) for name, rows in cur.fetchall()]


def collect(conn: psycopg.Connection, *, exact: bool = False) -> dict[str, Any]:
    """Collect a deterministic, read-only census from one database connection."""
    with conn.cursor() as cur:
        relations = _relations(cur)
        cur.execute(
            """
            SELECT c.table_name, c.column_name, c.data_type, c.is_nullable,
                   coalesce(s.null_frac, -1), coalesce(s.n_distinct, 0),
                   coalesce(pgd.description, '')
            FROM information_schema.columns c
            LEFT JOIN pg_class pc ON pc.relname = c.table_name
            LEFT JOIN pg_namespace pn ON pn.oid = pc.relnamespace AND pn.nspname = c.table_schema
            LEFT JOIN pg_stats s ON s.schemaname = c.table_schema
                AND s.tablename = c.table_name AND s.attname = c.column_name
            LEFT JOIN pg_description pgd ON pgd.objoid = pc.oid
                AND pgd.objsubid = (SELECT attnum FROM pg_attribute
                                    WHERE attrelid = pc.oid AND attname = c.column_name)
            WHERE c.table_schema = 'raw'
            ORDER BY c.table_name, c.ordinal_position
            """
        )
        column_rows = cur.fetchall()
        exact_counts: dict[str, int] = {}
        exact_field_stats: dict[tuple[str, str], dict[str, Any]] = {}
        if exact:
            for table, _ in relations:
                cur.execute(sql.SQL("SELECT count(*) FROM raw.{}").format(sql.Identifier(table)))
                row = cur.fetchone()
                assert row is not None
                exact_counts[table] = int(row[0])
            for table, column, *_rest in column_rows:
                cur.execute(
                    sql.SQL(
                        "SELECT count(*) FILTER (WHERE {} IS NULL), count(DISTINCT {}) FROM raw.{}"
                    ).format(sql.Identifier(column), sql.Identifier(column), sql.Identifier(table))
                )
                field_stat_row = cur.fetchone()
                assert field_stat_row is not None
                null_count, distinct_count = field_stat_row
                exact_field_stats[(str(table), str(column))] = {
                    "null_count": int(null_count),
                    "distinct_count": int(distinct_count),
                }
            for table, _ in relations:
                field_names = {str(row[1]) for row in column_rows if str(row[0]) == table}
                season_field = "_season" if "_season" in field_names else "season"
                if season_field not in field_names:
                    continue
                cur.execute(
                    sql.SQL("SELECT min({})::text, max({})::text FROM raw.{}").format(
                        sql.Identifier(season_field),
                        sql.Identifier(season_field),
                        sql.Identifier(table),
                    )
                )
                season_row = cur.fetchone()
                assert season_row is not None
                season_min, season_max = season_row
                for field_name in field_names:
                    exact_field_stats.setdefault((table, field_name), {})["season_min"] = season_min
                    exact_field_stats.setdefault((table, field_name), {})["season_max"] = season_max
    estimated = dict(relations)
    fields: list[dict[str, Any]] = []
    for table, column, data_type, nullable, null_fraction, distinct, description in column_rows:
        contract = _SOURCE_CONTRACTS.get(str(table), _DEFAULT)
        mapping = _classification(str(table), str(column))
        rows = exact_counts.get(str(table), round(estimated.get(str(table), 0)))
        exact_stats = exact_field_stats.get((str(table), str(column)), {})
        null_count = exact_stats.get("null_count")
        fields.append(
            {
                "raw_relation": f"raw.{table}",
                "field": column,
                "postgres_type": data_type,
                "nullable": nullable == "YES",
                "row_count": rows,
                "row_count_method": "exact" if exact else "catalog_estimate",
                "null_count": null_count,
                "null_fraction": (
                    (float(null_count) / rows if rows else 0.0)
                    if null_count is not None
                    else (None if float(null_fraction) < 0 else float(null_fraction))
                ),
                "distinct_count": exact_stats.get("distinct_count"),
                "distinct_estimate": None if exact else float(distinct),
                "season_min": exact_stats.get("season_min"),
                "season_max": exact_stats.get("season_max"),
                "comment": description or None,
                "provider": contract.provider,
                "source_grain": contract.grain,
                "natural_key": contract.natural_key,
                "event_time": contract.event_time,
                "availability": contract.availability,
                "rights_profile": contract.rights,
                "destination": mapping.destination,
                "classification": mapping.classification,
                "reason": mapping.reason,
                "candidate_family": mapping.candidate_family,
                "leakage_risk": mapping.leakage_risk,
                "required_validation": mapping.validation,
            }
        )
    counts: dict[str, int] = {}
    for record in fields:
        counts[record["classification"]] = counts.get(record["classification"], 0) + 1
    return {
        "schema": "raw",
        "exact": exact,
        "relations": len(relations),
        "fields": fields,
        "classification_counts": counts,
    }


def render_markdown(census: dict[str, Any]) -> str:
    """Render a compact, deterministic summary; JSON holds every field."""
    lines = [
        "# Raw → core → gold field census",
        "",
        "This generated report is verified database metadata, not a promise that an unmapped field is safe for modeling.",
        "",
        f"- Raw relations inspected: {census['relations']}",
        f"- Fields inspected: {len(census['fields'])}",
        f"- Row-count method: {'exact' if census['exact'] else 'PostgreSQL catalog estimate'}",
        "",
        "## Classification summary",
        "",
        "| Classification | Fields | Meaning |",
        "| --- | ---: | --- |",
    ]
    meanings = {
        "canonical_core": "conformed canonical identity/fact",
        "existing_gold": "already reaches a documented derived/reporting relation",
        "raw_only_by_design": "preserved source/provenance/final-state data, not a current feature",
        "unconformed_candidate": "candidate canonical fact requiring reconciliation",
        "invalid_or_low_value": "not currently useful or valid",
        "needs_research": "landed business field without an approved PIT contract",
    }
    for key in sorted(meanings):
        lines.append(
            f"| `{key}` | {census['classification_counts'].get(key, 0)} | {meanings[key]} |"
        )
    lines.extend(
        [
            "",
            "## How to use this",
            "",
            "Review `needs_research` fields through the feature-admission queue. Do not promote a field merely because it is populated: it also needs a stable grain, join, availability time, rights review, null policy, formula, and point-in-time test.",
            "",
        ]
    )
    return "\n".join(lines)


def write_outputs(census: dict[str, Any], *, json_path: Path, markdown_path: Path) -> None:
    json_path.parent.mkdir(parents=True, exist_ok=True)
    markdown_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(census, indent=2, sort_keys=True) + "\n")
    markdown_path.write_text(render_markdown(census))


def run(*, exact: bool = False) -> dict[str, Any]:
    """Use the configured database read-only and return its census."""
    with get_connection() as conn:
        # The command is an evidence collector.  Make accidental future
        # changes fail at PostgreSQL's transaction boundary, including when it
        # points at production for an explicitly permitted read-only census.
        conn.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
        return collect(conn, exact=exact)


def print_report(
    *, exact: bool = False, output_json: Path | None = None, output_markdown: Path | None = None
) -> None:
    """Print the compact report and optionally write deterministic artifacts."""
    census = run(exact=exact)
    if (output_json is None) != (output_markdown is None):
        raise ValueError("--output-json and --output-markdown must be supplied together")
    if output_json is not None and output_markdown is not None:
        write_outputs(census, json_path=output_json, markdown_path=output_markdown)
    print(render_markdown(census))
