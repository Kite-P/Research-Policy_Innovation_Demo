import pandas as pd

from src.enrich_real_company_profiles import (
    normalize_profile_response,
    profile_pilot_sample,
)


def test_cnipa_company_name_never_uses_stock_abbreviation():
    response = pd.DataFrame(
        {"公司名称": ["甲股份有限公司"], "证券简称": ["甲股份"], "注册地址": ["上海市浦东新区"]}
    )
    result = normalize_profile_response(response, "SSE", "600000", "SSE:600000:2000-01-01")
    assert result["company_name_legal"] == "甲股份有限公司"
    assert result["company_name_legal"] != "甲股份"


def test_delisted_profile_unavailable_is_explicit():
    result = normalize_profile_response(
        pd.DataFrame(), "SZSE", "000001", "SZSE:000001:1991-01-01", delisted=True
    )
    assert result["profile_status"] == "DELISTED_PROFILE_UNAVAILABLE"
    assert result["company_name_legal"] is None


def test_profile_pilot_sample_has_requested_strata():
    universe = pd.DataFrame(
        {
            "firm_key": [
                *[f"SSE:{i:06d}:2000-01-01" for i in range(20)],
                *[f"SZSE:{i:06d}:2000-01-01" for i in range(20)],
                *[f"BSE:{i:06d}:2021-11-15" for i in range(10)],
            ],
            "exchange": ["SSE"] * 20 + ["SZSE"] * 20 + ["BSE"] * 10,
            "profile_status": ["LISTING_SOURCE_ONLY"] * 50,
        }
    )
    result = profile_pilot_sample(universe, pd.DataFrame())
    assert result["exchange"].value_counts().to_dict() == {"SSE": 20, "SZSE": 20, "BSE": 10}
