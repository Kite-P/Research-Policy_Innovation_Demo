import pandas as pd

from src.build_real_company_universe import (
    expand_firm_years,
    standardize_delisted_frame,
    standardize_listing_frame,
)


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
    assert result.loc[0, "firm_key"] == "BSE:920185:2021-11-15"
    assert result.loc[0, "province_source"] == "static_registered_address"
    assert result.loc[0, "stock_code_current"] == "920185"
    assert result.loc[0, "predecessor_listing_date"] == pd.Timestamp("2020-07-27")
    assert result.loc[0, "market_listing_date"] == pd.Timestamp("2021-11-15")


def test_firm_key_does_not_change_when_company_name_changes():
    first = standardize_listing_frame(
        pd.DataFrame(
            {"A股代码": ["600000"], "A股简称": ["甲公司"], "A股上市日期": ["2000-01-01"]}
        ),
        "SSE",
    )
    second = standardize_listing_frame(
        pd.DataFrame(
            {"A股代码": ["600000"], "A股简称": ["甲公司更名"], "A股上市日期": ["2000-01-01"]}
        ),
        "SSE",
    )
    assert first.loc[0, "firm_key"] == second.loc[0, "firm_key"]


def test_delisted_firm_is_retained_only_during_listed_years():
    firms = standardize_delisted_frame(
        pd.DataFrame(
            {
                "证券代码": ["000001"],
                "证券简称": ["退市甲"],
                "上市日期": ["2018-01-01"],
                "终止上市日期": ["2022-06-30"],
            }
        ),
        "SZSE",
    )
    result = expand_firm_years(firms, 2020, 2025)
    assert result["year"].tolist() == [2020, 2021, 2022]
    assert result["delisting_date"].iloc[0] == pd.Timestamp("2022-06-30")


def test_expand_firm_years_excludes_bse_2020_and_respects_listing_date():
    firms = pd.DataFrame(
        {
            "firm_key": ["BSE:甲:2021-01-01", "SSE:乙:2019-01-01"],
            "exchange": ["BSE", "SSE"],
            "listing_date": pd.to_datetime(["2021-01-01", "2019-01-01"]),
            "market_listing_date": pd.to_datetime(["2021-11-15", "2019-01-01"]),
            "delisting_date": [pd.NaT, pd.NaT],
        }
    )
    result = expand_firm_years(firms, start_year=2020, end_year=2021)
    assert set(zip(result["exchange"], result["year"])) == {
        ("SSE", 2020),
        ("SSE", 2021),
        ("BSE", 2021),
    }


def test_bse_transfer_listing_date_is_2021_11_15():
    frame = standardize_listing_frame(
        pd.DataFrame(
            {"证券代码": ["920185"], "证券简称": ["贝特瑞"], "上市日期": ["2020-07-27"]}
        ),
        "BSE",
    )
    assert frame.loc[0, "market_listing_date"] == pd.Timestamp("2021-11-15")
