from __future__ import annotations

import argparse
from pathlib import Path

import akshare as ak
import pandas as pd

try:
    from .bse_code_mapping import BSE_MAPPING_SOURCE, load_bse_mapping
except ImportError:
    from bse_code_mapping import BSE_MAPPING_SOURCE, load_bse_mapping

START_YEAR = 2020
END_YEAR = 2025
BSE_MARKET_START = pd.Timestamp("2021-11-15")


def _code(value: object) -> str:
    text = str(value).strip()
    if text.endswith(".0"):
        text = text[:-2]
    return text.zfill(6) if text.isdigit() else ""


def _first(frame: pd.DataFrame, names: tuple[str, ...]) -> pd.Series:
    for name in names:
        if name in frame.columns:
            return frame[name]
    return pd.Series(pd.NA, index=frame.index)


def _market_dates(listing_date: pd.Series, exchange: str) -> tuple[pd.Series, pd.Series]:
    original = pd.to_datetime(listing_date, errors="coerce")
    if exchange == "BSE":
        market = original.where(original >= BSE_MARKET_START, BSE_MARKET_START)
        return original, market
    return original, original


def _empty_delisting(frame: pd.DataFrame) -> pd.Series:
    return pd.Series(pd.NaT, index=frame.index, dtype="datetime64[ns]")


def standardize_listing_frame(frame: pd.DataFrame, exchange: str) -> pd.DataFrame:
    stock_code = _first(frame, ("证券代码", "A股代码")).map(_code)
    stock_name = _first(frame, ("证券简称", "A股简称"))
    legal_name = _first(frame, ("公司名称", "公司全称"))
    listing_date, market_date = _market_dates(_first(frame, ("上市日期", "A股上市日期")), exchange)
    predecessor_date = (
        listing_date
        if exchange == "BSE"
        else pd.Series(pd.NaT, index=frame.index, dtype="datetime64[ns]")
    )
    firm_key = exchange + ":" + stock_code + ":" + market_date.dt.strftime(
        "%Y-%m-%d"
    ).fillna("")
    result = pd.DataFrame(
        {
            "firm_key": firm_key,
            "stock_code_current": stock_code,
            "historical_stock_code": pd.NA,
            "stock_code_source_year": market_date.dt.year.astype("Int64"),
            "stock_name": stock_name.astype("string").str.strip(),
            "company_name_legal": legal_name.astype("string").str.strip(),
            "exchange": exchange,
            "listing_date": listing_date,
            "predecessor_listing_date": predecessor_date,
            "market_listing_date": market_date,
            "delisting_date": _empty_delisting(frame),
            "industry_name": _first(frame, ("所属行业",)),
            "registered_address": pd.Series(pd.NA, index=frame.index, dtype="string"),
            "province": _first(frame, ("地区",)),
            "province_source": "static_registered_address",
            "profile_source": "AKShare exchange listing",
            "profile_status": "LISTING_SOURCE_ONLY",
        }
    )
    result.loc[result["province"].isna(), "province_source"] = "unavailable"
    return result.drop_duplicates(subset=["firm_key"]).reset_index(drop=True)


def standardize_delisted_frame(frame: pd.DataFrame, exchange: str) -> pd.DataFrame:
    code_names = ("公司代码", "证券代码", "A股代码")
    stock_code = _first(frame, code_names).map(_code)
    stock_name = _first(frame, ("公司简称", "证券简称", "A股简称"))
    listing_date, market_date = _market_dates(_first(frame, ("上市日期", "A股上市日期")), exchange)
    predecessor_date = (
        listing_date
        if exchange == "BSE"
        else pd.Series(pd.NaT, index=frame.index, dtype="datetime64[ns]")
    )
    firm_key = exchange + ":" + stock_code + ":" + market_date.dt.strftime(
        "%Y-%m-%d"
    ).fillna("")
    delisting_date = pd.to_datetime(
        _first(frame, ("终止上市日期", "暂停上市日期", "退市日期")), errors="coerce"
    )
    return pd.DataFrame(
        {
            "firm_key": firm_key,
            "stock_code_current": stock_code,
            "historical_stock_code": pd.NA,
            "stock_code_source_year": market_date.dt.year.astype("Int64"),
            "stock_name": stock_name.astype("string").str.strip(),
            "company_name_legal": pd.Series(pd.NA, index=frame.index, dtype="string"),
            "exchange": exchange,
            "listing_date": listing_date,
            "predecessor_listing_date": predecessor_date,
            "market_listing_date": market_date,
            "delisting_date": delisting_date,
            "industry_name": pd.Series(pd.NA, index=frame.index, dtype="string"),
            "registered_address": pd.Series(pd.NA, index=frame.index, dtype="string"),
            "province": pd.Series(pd.NA, index=frame.index, dtype="string"),
            "province_source": "unavailable",
            "profile_source": "AKShare delisting list",
            "profile_status": "DELISTED_PROFILE_UNAVAILABLE",
        }
    ).drop_duplicates(subset=["firm_key"]).reset_index(drop=True)


def fetch_exchange_listings() -> pd.DataFrame:
    sse = pd.concat(
        [
            ak.stock_info_sh_name_code(symbol="主板A股"),
            ak.stock_info_sh_name_code(symbol="科创板"),
        ],
        ignore_index=True,
    )
    return pd.concat(
        [
            standardize_listing_frame(sse, "SSE"),
            standardize_listing_frame(ak.stock_info_sz_name_code(symbol="A股列表"), "SZSE"),
            standardize_listing_frame(ak.stock_info_bj_name_code(), "BSE"),
        ],
        ignore_index=True,
    ).drop_duplicates("firm_key")


def fetch_delisted_listings() -> pd.DataFrame:
    return pd.concat(
        [
            standardize_delisted_frame(ak.stock_info_sh_delist(symbol="全部"), "SSE"),
            standardize_delisted_frame(
                ak.stock_info_sz_delist(symbol="终止上市公司"), "SZSE"
            ),
        ],
        ignore_index=True,
    ).drop_duplicates("firm_key")


def filter_firm_universe(firms: pd.DataFrame) -> pd.DataFrame:
    valid = firms["market_listing_date"].le(pd.Timestamp("2025-12-31"))
    valid &= firms["delisting_date"].isna() | firms["delisting_date"].ge(
        pd.Timestamp("2020-01-01")
    )
    return firms.loc[valid].copy()


def expand_firm_years(firms: pd.DataFrame, start_year: int, end_year: int) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for _, firm in firms.iterrows():
        for year in range(start_year, end_year + 1):
            year_start = pd.Timestamp(year=year, month=1, day=1)
            year_end = pd.Timestamp(year=year, month=12, day=31)
            listed = pd.notna(firm["market_listing_date"]) and (
                firm["market_listing_date"] <= year_end
            )
            if pd.notna(firm["delisting_date"]):
                listed = listed and firm["delisting_date"] > year_start
            if listed and not (firm["exchange"] == "BSE" and year == 2020):
                row = firm.to_dict()
                row["year"] = year
                rows.append(row)
    return pd.DataFrame(rows)


def build_universe(mapping_path: Path | None = None) -> tuple[pd.DataFrame, dict[str, object]]:
    current = fetch_exchange_listings()
    delisted = fetch_delisted_listings()
    firms = filter_firm_universe(
        pd.concat([current, delisted], ignore_index=True).drop_duplicates("firm_key")
    )
    mapping = load_bse_mapping(mapping_path) if mapping_path else pd.DataFrame(
        columns=["old_stock_code", "new_stock_code"]
    )
    bse = firms["exchange"].eq("BSE")
    firms["bse_mapping_status"] = "not_applicable"
    firms.loc[bse, "bse_mapping_status"] = "unmatched_official_mapping"
    if not mapping.empty:
        mapped_new = set(mapping["new_stock_code"])
        firms.loc[
            bse & firms["stock_code_current"].isin(mapped_new), "bse_mapping_status"
        ] = "matched"
    panel = expand_firm_years(firms, START_YEAR, END_YEAR)
    audit = {
        "company_count": int(len(firms)),
        "current_firms": int((firms["profile_status"] == "LISTING_SOURCE_ONLY").sum()),
        "delisted_firms": int((firms["profile_status"] == "DELISTED_PROFILE_UNAVAILABLE").sum()),
        "firm_year_count": int(len(panel)),
        "exchange_distribution": firms["exchange"].value_counts().to_dict(),
        "year_distribution": panel["year"].value_counts().sort_index().to_dict(),
        "province_coverage": firms.groupby("exchange")["province"]
        .apply(lambda s: int(s.notna().sum()))
        .to_dict(),
        "industry_coverage": firms.groupby("exchange")["industry_name"]
        .apply(lambda s: int(s.notna().sum()))
        .to_dict(),
        "legal_name_coverage": firms.groupby("exchange")["company_name_legal"]
        .apply(lambda s: int(s.notna().sum()))
        .to_dict(),
        "bse_mapping_source": BSE_MAPPING_SOURCE,
        "bse_mapping_rows": int(len(mapping)),
        "bse_unmatched": int((firms["bse_mapping_status"] == "unmatched_official_mapping").sum()),
    }
    return panel, audit


def _stata_ready(frame: pd.DataFrame) -> pd.DataFrame:
    result = frame.copy()
    for column in result.select_dtypes(include=["object", "string"]).columns:
        result[column] = result[column].where(result[column].notna(), "").astype(str)
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mapping", type=Path)
    parser.add_argument("--output", type=Path, default=Path("data/processed"))
    args = parser.parse_args()
    panel, audit = build_universe(args.mapping)
    args.output.mkdir(parents=True, exist_ok=True)
    panel.to_parquet(args.output / "real_company_universe.parquet", index=False)
    _stata_ready(panel).to_stata(
        args.output / "real_company_universe.dta", write_index=False, version=118
    )
    pd.DataFrame([audit]).to_json(
        args.output / "real_company_universe_audit.json", orient="records"
    )
    print(audit)


if __name__ == "__main__":
    main()
