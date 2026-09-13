-- Named INSERT resource for catalog.py::load() (metric-catalog, ADR-291).
-- One row per validated mlb_baseball/metrics/*.yaml entry. The caller
-- TRUNCATEs meta.metric once per build and executes this once per entry
-- inside that same transaction -- same idempotent full-rebuild pattern as
-- every other gold/meta loader in this project.
INSERT INTO meta.metric (
    name,
    definition,
    formula,
    citation,
    data_source,
    grain,
    layer,
    complexity,
    implementation,
    status,
    visibility,
    test_ref,
    notes,
    source_permalink
) VALUES (
    %(name)s,
    %(definition)s,
    %(formula)s,
    %(citation)s,
    %(data_source)s,
    %(grain)s,
    %(layer)s,
    %(complexity)s,
    %(implementation)s,
    %(status)s,
    %(visibility)s,
    %(test_ref)s,
    %(notes)s,
    %(source_permalink)s
);
