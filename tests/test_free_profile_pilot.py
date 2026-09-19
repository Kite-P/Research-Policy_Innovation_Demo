import pandas as pd

from src.free_profile_pilot import (
    extract_province_from_address,
    normalize_stock_code,
    stable_pick,
)


def test_normalize_stock_code_preserves_leading_zero():
    assert normalize_stock_code("1") == "000001"
    assert normalize_stock_code(1) == "000001"
    assert normalize_stock_code("600519") == "600519"


def test_stable_pick_is_deterministic():
    frame = pd.DataFrame(
        {
            "stock_code": [f"{i:06d}" for i in range(100)],
            "stock_name": [f"Firm{i}" for i in range(100)],
            "exchange": ["SSE"] * 100,
            "listing_date": [pd.Timestamp("2020-01-01")] * 100,
        }
    )

    a = stable_pick(frame, "SSE", 8)
    b = stable_pick(frame.sample(frac=1, random_state=7), "SSE", 8)

    assert a["stock_code"].tolist() == b["stock_code"].tolist()


def test_extract_province_from_address():
    assert extract_province_from_address("北京市海淀区某路1号") == "北京市"
    assert extract_province_from_address("广东省深圳市南山区某路") == "广东省"
    assert extract_province_from_address("中国（上海）自由贸易试验区某路") == "上海市"
    assert extract_province_from_address(None) is None
