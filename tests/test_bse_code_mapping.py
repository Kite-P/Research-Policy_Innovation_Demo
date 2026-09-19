import pandas as pd

from src.bse_code_mapping import normalize_bse_mapping, resolve_bse_codes


def test_bse_known_mapping():
    frame = normalize_bse_mapping(
        pd.DataFrame({"旧代码": ["835185", "833266"], "新代码": ["920185", "920266"]})
    )
    old_to_new = dict(zip(frame["old_stock_code"], frame["new_stock_code"]))
    assert old_to_new["835185"] == "920185"
    assert old_to_new["833266"] == "920266"


def test_resolve_bse_codes_uses_mapping_and_preserves_unmatched():
    mapping = normalize_bse_mapping(
        pd.DataFrame({"旧代码": ["835185"], "新代码": ["920185"]})
    )
    assert resolve_bse_codes("920185", mapping) == ["835185", "920185"]
    assert resolve_bse_codes("920999", mapping) == ["920999"]
