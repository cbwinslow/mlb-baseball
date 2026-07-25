from mlb_baseball.connectors.chadwick_register import extract_columns

COUNTRIES_SAMPLE = (
    "key_iso_alpha2,key_iso_alpha3,key_ioc,key_fifa,name_full_en\nAD,AND,AND,AND,Andorra\n"
)


def test_extract_columns_reads_header_in_order():
    assert extract_columns(COUNTRIES_SAMPLE) == [
        "key_iso_alpha2",
        "key_iso_alpha3",
        "key_ioc",
        "key_fifa",
        "name_full_en",
    ]
