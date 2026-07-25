-- Raw landing tables for the Chadwick Bureau Register (ID crosswalk), source-faithful:
-- every column is text, matching the CSV exactly. Typing/cleaning happens in the
-- conformed layer, not here (see docs/ARCHITECTURE.md).
--
-- _loaded_at records when this snapshot was landed. The register is a point-in-time
-- snapshot, not an event stream, so connectors truncate-and-reload these tables on
-- each run rather than appending.

CREATE TABLE raw.register_people (
    key_person text,
    key_uuid text,
    key_mlbam text,
    key_retro text,
    key_bbref text,
    key_bbref_minors text,
    key_fangraphs text,
    key_npb text,
    key_sr_nfl text,
    key_sr_nba text,
    key_sr_nhl text,
    key_wikidata text,
    name_last text,
    name_first text,
    name_given text,
    name_suffix text,
    name_matrilineal text,
    name_nick text,
    birth_year text,
    birth_month text,
    birth_day text,
    death_year text,
    death_month text,
    death_day text,
    pro_played_first text,
    pro_played_last text,
    mlb_played_first text,
    mlb_played_last text,
    col_played_first text,
    col_played_last text,
    pro_managed_first text,
    pro_managed_last text,
    mlb_managed_first text,
    mlb_managed_last text,
    col_managed_first text,
    col_managed_last text,
    pro_umpired_first text,
    pro_umpired_last text,
    mlb_umpired_first text,
    mlb_umpired_last text,
    _loaded_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE raw.register_names (
    key_person text,
    name_last text,
    name_first text,
    name_given text,
    birth_year text,
    birth_month text,
    birth_day text,
    altname_type text,
    altname_lang text,
    altname_last text,
    altname_first text,
    altname_given text,
    altname_matrilineal text,
    altname_nick text,
    altname_date_start text,
    altname_date_end text,
    _loaded_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE raw.register_links (
    key_person text,
    source text,
    value text,
    _loaded_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE raw.register_countries (
    key_iso_alpha2 text,
    key_iso_alpha3 text,
    key_ioc text,
    key_fifa text,
    name_full_en text,
    _loaded_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX ON raw.register_people (key_retro);
CREATE INDEX ON raw.register_people (key_mlbam);
CREATE INDEX ON raw.register_people (key_bbref);
CREATE INDEX ON raw.register_people (key_fangraphs);
