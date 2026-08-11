from mlb_baseball import schema_inventory


def test_schema_inventory_reports_core_contract_objects():
    rows = schema_inventory.relations()
    game = next(row for row in rows if row["schema_name"] == "core" and row["relname"] == "game")
    assert game["kind"] == "table"
    assert game["primary_keys"] == 1
    assert game["indexes"] >= 1
    assert all(row["partition_parent"] is None for row in rows)


def test_schema_inventory_can_include_child_partitions():
    rows = schema_inventory.relations(partitions=True)
    assert any(row["partition_parent"] == "play" for row in rows)
