"""Unit coverage for mlb_baseball.catalog's pure schema-validation and
reproducibility-link logic (metric-catalog, ADR-291). No database needed --
`load()`'s meta.metric integration is covered separately in
tests/integration/test_catalog_loader.py.
"""

import pytest
from pydantic import ValidationError

from mlb_baseball.catalog import CatalogError, MetricEntry, _load_one, _source_permalink, load_all

_VALID_FIELDS = {
    "name": "fangraphs_guts",
    "definition": "FanGraphs' per-season linear-weight constants.",
    "formula": "mlb_baseball/sql/gold_fangraphs_guts.sql",
    "citation": "FanGraphs, Guts! constants (https://www.fangraphs.com/guts.aspx)",
    "data_source": "raw.fangraphs_guts",
    "grain": "season",
    "layer": "gold",
    "complexity": "arithmetic",
    "implementation": "sql",
    "status": "published",
    "visibility": "public",
}


def test_valid_entry_accepted():
    entry = MetricEntry.model_validate(_VALID_FIELDS)
    assert entry.name == "fangraphs_guts"
    assert entry.test_ref is None
    assert entry.notes is None


def test_missing_required_field_rejected():
    fields = dict(_VALID_FIELDS)
    del fields["citation"]
    with pytest.raises(ValidationError):
        MetricEntry.model_validate(fields)


@pytest.mark.parametrize(
    "field,bad_value",
    [
        ("status", "definitely-not-a-status"),
        ("visibility", "semi-public"),
        ("complexity", "medium"),
        ("implementation", "duckdb"),
        ("layer", "silver"),
    ],
)
def test_bad_enum_value_rejected(field, bad_value):
    fields = dict(_VALID_FIELDS)
    fields[field] = bad_value
    with pytest.raises(ValidationError):
        MetricEntry.model_validate(fields)


def test_validated_status_requires_test_ref():
    fields = dict(_VALID_FIELDS)
    fields["status"] = "validated"
    with pytest.raises(Exception, match="test_ref"):
        MetricEntry.model_validate(fields)


def test_validated_status_with_test_ref_accepted():
    fields = dict(_VALID_FIELDS)
    fields["status"] = "validated"
    fields["test_ref"] = "tests/integration/test_x.py::test_y"
    entry = MetricEntry.model_validate(fields)
    assert entry.test_ref == "tests/integration/test_x.py::test_y"


def test_load_one_names_file_and_field_on_missing_field(tmp_path):
    path = tmp_path / "broken.yaml"
    fields = dict(_VALID_FIELDS)
    del fields["visibility"]
    import yaml

    path.write_text(yaml.safe_dump(fields), encoding="utf-8")
    with pytest.raises(CatalogError) as exc_info:
        _load_one(path)
    message = str(exc_info.value)
    assert str(path) in message
    assert "visibility" in message


def test_load_one_names_file_and_field_on_bad_enum(tmp_path):
    path = tmp_path / "broken.yaml"
    fields = dict(_VALID_FIELDS)
    fields["status"] = "not-a-real-status"
    import yaml

    path.write_text(yaml.safe_dump(fields), encoding="utf-8")
    with pytest.raises(CatalogError) as exc_info:
        _load_one(path)
    message = str(exc_info.value)
    assert str(path) in message
    assert "status" in message


def test_load_all_reads_every_yaml_file(tmp_path):
    import yaml

    for i in range(2):
        fields = dict(_VALID_FIELDS)
        fields["name"] = f"metric_{i}"
        (tmp_path / f"metric_{i}.yaml").write_text(yaml.safe_dump(fields), encoding="utf-8")
    entries = load_all(tmp_path)
    assert {entry.name for entry in entries} == {"metric_0", "metric_1"}


def test_load_all_raises_on_first_invalid_entry(tmp_path):
    import yaml

    good = dict(_VALID_FIELDS)
    good["name"] = "good_metric"
    (tmp_path / "good_metric.yaml").write_text(yaml.safe_dump(good), encoding="utf-8")

    bad = dict(_VALID_FIELDS)
    bad["name"] = "bad_metric"
    del bad["citation"]
    (tmp_path / "bad_metric.yaml").write_text(yaml.safe_dump(bad), encoding="utf-8")

    with pytest.raises(CatalogError) as exc_info:
        load_all(tmp_path)
    assert "bad_metric.yaml" in str(exc_info.value)


def test_source_permalink_strips_function_suffix():
    permalink = _source_permalink("mlb_baseball/model/framing.py::compute", "abc123")
    assert (
        permalink
        == "https://github.com/cbwinslow/mlb-baseball/blob/abc123/mlb_baseball/model/framing.py"
    )


def test_source_permalink_bare_file_path():
    permalink = _source_permalink("mlb_baseball/sql/gold_fangraphs_guts.sql", "deadbeef")
    assert permalink == (
        "https://github.com/cbwinslow/mlb-baseball/blob/deadbeef/"
        "mlb_baseball/sql/gold_fangraphs_guts.sql"
    )


def test_real_fangraphs_guts_entry_loads_and_passes_validation():
    """The one demo entry shipped in mlb_baseball/metrics/ must pass the
    validator it's a demonstration of -- catches drift between the schema
    and the shipped example (tasks.md 2.2's own requirement)."""
    from mlb_baseball.catalog import METRICS_DIR

    entries = load_all(METRICS_DIR)
    names = {entry.name for entry in entries}
    assert "fangraphs_guts" in names
    entry = next(e for e in entries if e.name == "fangraphs_guts")
    assert entry.visibility == "public"
    assert entry.status == "published"
