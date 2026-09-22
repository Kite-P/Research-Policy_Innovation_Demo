import pandas as pd
import pytest

from src.eastmoney_company_profile import (
    EastMoneyProfileClient,
    build_profile_pilot_sample,
    merge_profiles,
    normalize_profile_record,
    profile_cache_path,
    to_eastmoney_secucode,
)


def test_to_eastmoney_secucode():
    assert to_eastmoney_secucode("SSE", "600519") == "600519.SH"
    assert to_eastmoney_secucode("SZSE", "000001") == "000001.SZ"
    assert to_eastmoney_secucode("BSE", "920185") == "920185.BJ"


def test_to_eastmoney_secucode_rejects_unknown_exchange():
    with pytest.raises(ValueError):
        to_eastmoney_secucode("OTC", "000001")


def test_profile_never_falls_back_to_stock_name():
    firm = pd.Series({"firm_key": "SSE:1:2020", "stock_code_current": "000001", "exchange": "SSE"})
    result = normalize_profile_record({"SECURITY_NAME_ABBR": "简称A"}, firm)
    assert result["company_name_legal"] is None
    assert result["profile_status"] == "LEGAL_NAME_MISSING"


def test_profile_province_conflict_is_flagged():
    firm = pd.Series({"firm_key": "SSE:1:2020", "stock_code_current": "000001", "exchange": "SSE"})
    result = normalize_profile_record(
        {"ORG_NAME": "甲有限公司", "PROVINCE": "广东", "REG_ADDRESS": "浙江省杭州市"}, firm
    )
    assert result["province"] is None
    assert result["province_conflict"] is True


def test_profile_province_short_name_matches_address_suffix():
    firm = pd.Series({"firm_key": "SSE:1:2020", "stock_code_current": "000001", "exchange": "SSE"})
    result = normalize_profile_record(
        {"ORG_NAME": "甲有限公司", "PROVINCE": "浙江", "REG_ADDRESS": "浙江省杭州市"}, firm
    )
    assert result["province"] == "浙江省"
    assert result["province_conflict"] is False


def test_profile_preserves_org_code_and_csrc_industry():
    firm = pd.Series({"firm_key": "SSE:1:2020", "stock_code_current": "000001", "exchange": "SSE"})
    result = normalize_profile_record(
        {"ORG_NAME": "甲有限公司", "ORG_CODE": "10001", "INDUSTRYCSRC1": "制造业"}, firm
    )
    assert result["source_org_code"] == "10001"
    assert result["industry_csrc"] == "制造业"


def test_financial_cache_key_uses_firm_key(tmp_path):
    assert profile_cache_path(tmp_path, "SSE:600000:1999-01-01") != profile_cache_path(
        tmp_path, "SSE:600000:2001-01-01"
    )


def test_profile_merge_preserves_rows():
    universe = pd.DataFrame({"firm_key": ["a", "a", "b"], "year": [2020, 2021, 2020]})
    profiles = pd.DataFrame({"firm_key": ["a", "b"], "company_name_legal": ["甲", "乙"]})
    merged = merge_profiles(universe, profiles)
    assert len(merged) == 3
    assert merged["firm_key"].tolist() == ["a", "a", "b"]


def test_profile_pilot_sample_is_deterministic():
    rows = []
    for exchange in ("SSE", "SZSE", "BSE"):
        for index in range(30):
            rows.append(
                {
                    "firm_key": f"{exchange}:{index}:2020",
                    "exchange": exchange,
                    "stock_code_current": f"{index:06d}",
                    "listing_date": pd.Timestamp("2020-01-01"),
                    "delisting_date": pd.NaT,
                    "predecessor_listing_date": pd.NaT,
                    "profile_status": "LISTING_SOURCE_ONLY",
                }
            )
    universe = pd.DataFrame(rows)
    sample_a = build_profile_pilot_sample(universe)
    sample_b = build_profile_pilot_sample(universe)
    assert sample_a["firm_key"].tolist() == sample_b["firm_key"].tolist()
    assert sample_a["firm_key"].is_unique


def test_client_request_contract():
    client = EastMoneyProfileClient(request_spacing=0, retries=0)
    assert client.request_spacing == 0
