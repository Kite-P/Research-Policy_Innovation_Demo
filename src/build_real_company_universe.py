from __future__ import annotations

import argparse
from pathlib import Path

import akshare as ak
import pandas as pd

try:
    from .bse_code_mapping import BSE_MAPPING_SOURCE, load_bse_mapping
except ImportError:
    from bse_code_mapping import BSE_MAPPING_SOURCE, load_bse_mapping

YEARS = range(2020, 2026)


def _code(value: object) -> str:
    text = str(value).strip()
    if text.endswith(".0"):
        text = text[:-2]
    return text.zfill(6) if text.isdigit() else ""


def standardize_listing_frame(frame: pd.DataFrame, exchange: str) -> pd.DataFrame:
    aliases = {
        "stock_code_current": ("证券代码", "A股代码"),
        "company_name": ("公司全称", "证券全称", "A股简称", "证券简称"),
        "listing_date": ("上市日期", "A股上市日期"),
        "industry_name": ("所属行业",),
        "province": ("地区",),
    }

    def first(names: tuple[str, ...]) -> pd.Series:
        for name in names:
            if name in frame.columns:
                return frame[name]
        return pd.Series(pd.NA, index=frame.index)

    result = pd.DataFrame(
        {
            "stock_code_current": first(aliases["stock_code_current"]).map(_code),
            "company_name": first(aliases["company_name"]).astype("string").str.strip(),
            "listing_date": pd.to_datetime(first(aliases["listing_date"]), errors="coerce"),
            "industry_name": first(aliases["industry_name"]),
            "province": first(aliases["province"]),
        }
    )
    result["exchange"] = exchange
    result["firm_key"] = (
        exchange
        + ":"
        + result["company_name"].fillna("")
        + ":"
        + result["listing_date"].dt.strftime("%Y-%m-%d").fillna("")
    )
    result["stock_code_source_year"] = result["listing_date"].dt.year.astype("Int64")
    result["delisting_date"] = pd.NaT
    result["registered_address"] = pd.NA
    result["province_source"] = "static_registered_address"
    return result[
        [
            "firm_key",
            "stock_code_current",
            "stock_code_source_year",
            "company_name",
            "exchange",
            "listing_date",
            "delisting_date",
            "industry_name",
            "registered_address",
            "province",
            "province_source",
        ]
    ].drop_duplicates(subset=["firm_key"])


def fetch_exchange_listings() -> pd.DataFrame:
    sse = pd.concat(
        [
            ak.stock_info_sh_name_code(symbol="主板A股"),
            ak.stock_info_sh_name_code(symbol="科创板"),
        ],
        ignore_index=True,
    )
    frames = [
        standardize_listing_frame(sse, "SSE"),
        standardize_listing_frame(ak.stock_info_sz_name_code(symbol="A股列表"), "SZSE"),
        standardize_listing_frame(ak.stock_info_bj_name_code(), "BSE"),
    ]
    return pd.concat(frames, ignore_index=True).drop_duplicates("firm_key")


def expand_firm_years(firms: pd.DataFrame, start_year: int, end_year: int) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for _, firm in firms.iterrows():
        listing_date = firm["listing_date"]
        delisting_date = firm["delisting_date"]
        for year in range(start_year, end_year + 1):
            year_start = pd.Timestamp(year=year, month=1, day=1)
            year_end = pd.Timestamp(year=year, month=12, day=31)
            listed = pd.notna(listing_date) and listing_date <= year_end
            if pd.notna(delisting_date):
                listed = listed and delisting_date > year_start
            if listed and not (firm["exchange"] == "BSE" and year == 2020):
                row = firm.to_dict()
                row["year"] = year
                rows.append(row)
    return pd.DataFrame(rows)


def build_universe(mapping_path: Path | None = None) -> tuple[pd.DataFrame, dict[str, object]]:
    firms = fetch_exchange_listings()
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
    panel = expand_firm_years(firms, 2020, 2025)
    audit = {
        "company_count": int(len(firms)),
        "firm_year_count": int(len(panel)),
        "exchange_distribution": firms["exchange"].value_counts().to_dict(),
        "year_distribution": panel["year"].value_counts().sort_index().to_dict(),
        "province_missing": int(firms["province"].isna().sum()),
        "industry_missing": int(firms["industry_name"].isna().sum()),
        "company_name_missing": int(firms["company_name"].isna().sum()),
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
