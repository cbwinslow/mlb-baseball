import zipfile

from mlb_baseball.connectors.lahman import TABLES, _read_from_zip


def test_every_table_has_a_unique_name():
    names = [table for table, _filename, _fetch in TABLES]
    assert len(names) == len(set(names))


def test_reads_csv_nested_inside_a_dated_folder_name(tmp_path):
    zip_path = tmp_path / "lahman_1871-2099_csv.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("lahman_1871-2099_csv/Parks.csv", "key_iso_alpha2,name\nAD,Andorra\n")

    with zipfile.ZipFile(zip_path) as zf:
        df = _read_from_zip(zf, "Parks.csv")

    assert list(df.columns) == ["key_iso_alpha2", "name"]
    assert df.iloc[0]["name"] == "Andorra"
