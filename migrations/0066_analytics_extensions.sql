-- Enables core PostgreSQL extensions for analytics, fuzzy identity matching,
-- temporal constraints, vector embeddings, and crosstab reporting.
-- Evaluated and recommended in PROJECT_ASSESSMENT_AND_ENHANCEMENT_PLAN.md.

-- 1. pg_trgm: text similarity and trigram index acceleration for player/team crosswalking
CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- 2. btree_gist: index common data types in GiST for temporal/range exclusion constraints
CREATE EXTENSION IF NOT EXISTS btree_gist;

-- 3. vector: vector data type, distance operators, and HNSW/IVFFLAT indexes for embeddings
CREATE EXTENSION IF NOT EXISTS vector;

-- 4. tablefunc: crosstab() table functions for multi-season/platoon matrix pivoting
CREATE EXTENSION IF NOT EXISTS tablefunc;

-- GIN trigram indexes for accelerated fuzzy player, team, and alias matching
CREATE INDEX IF NOT EXISTS idx_core_player_name_trgm
    ON core.player USING gin ((first_name || ' ' || last_name) gin_trgm_ops);

CREATE INDEX IF NOT EXISTS idx_core_player_last_name_trgm
    ON core.player USING gin (last_name gin_trgm_ops);

CREATE INDEX IF NOT EXISTS idx_core_team_nickname_trgm
    ON core.team USING gin (nickname gin_trgm_ops);

CREATE INDEX IF NOT EXISTS idx_core_team_alias_trgm
    ON core.team_alias USING gin (alias gin_trgm_ops);
