import pandas as pd

from src.build_real_company_universe import expand_firm_years, standardize_listing_frame


def test_standardize_listing_frame_creates_stable_firm_key_and_fields():
    frame = pd.DataFrame(
        {
            "A股代码": ["920185"],
            "A股简称": ["贝特瑞"],
            "A股上市日期": ["2020-07-27"],
            "所属行业": ["制造业"],
            "地区": ["广东省"],
        }
    )
    result = standardize_listing_frame(frame, "BSE")
    assert result.loc[0, "firm_key"] == "BSE:贝特瑞:2020-07-27"
    assert result.loc[0, "province_source"] == "static_registered_address"
    assert result.loc[0, "stock_code_current"] == "920185"


def test_expand_firm_years_excludes_bse_2020_and_respects_listing_date():
    firms = pd.DataFrame(
        {
            "firm_key": ["BSE:甲:2021-01-01", "SSE:乙:2019-01-01"],
            "exchange": ["BSE", "SSE"],
            "listing_date": pd.to_datetime(["2021-01-01", "2019-01-01"]),
            "delisting_date": [pd.NaT, pd.NaT],
        }
    )
    result = expand_firm_years(firms, start_year=2020, end_year=2021)
    assert set(zip(result["exchange"], result["year"])) == {
        ("SSE", 2020),
        ("SSE", 2021),
        ("BSE", 2021),
    }
