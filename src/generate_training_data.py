import argparse
from pathlib import Path

import numpy as np
import pandas as pd

SEED = 20260915


COMPANY_STEMS = [
    "\u534e\u8fb0",
    "\u65b0\u5cb3",
    "\u6d77\u5ddd",
    "\u4e2d\u76db",
    "\u5b8f\u8fdc",
    "\u667a\u6052",
    "\u745e\u534e",
    "\u661f\u6d77",
    "\u5929\u6210",
    "\u535a\u521b",
    "\u4e1c\u6cf0",
    "\u534e\u666f",
    "\u91d1\u79d1",
    "\u660e\u5fb7",
    "\u6c38\u76db",
    "\u6668\u5149",
    "\u4e91\u79d1",
    "\u5609\u6cf0",
    "\u9f0e\u65b0",
    "\u542f\u822a",
    "\u6052\u901a",
    "\u8fdc\u671b",
    "\u8054\u521b",
    "\u5b89\u8fbe",
    "\u6e90\u521b",
    "\u6052\u661f",
    "\u5146\u4e30",
    "\u4e2d\u79d1",
    "\u7eff\u80fd",
    "\u5929\u5b87",
    "\u4e1c\u65b9",
    "\u4e07\u6e90",
    "\u534e\u9f0e",
    "\u65b0\u8fbe",
    "\u79d1\u521b",
    "\u8054\u76db",
    "\u535a\u745e",
    "\u6052\u745e",
    "\u4e2d\u4fe1",
    "\u9e3f\u8fdc",
]

COMPANY_SUFFIX = "\u79d1\u6280\u80a1\u4efd\u6709\u9650\u516c\u53f8"
SHORT_SUFFIX = "\u79d1\u6280\u6709\u9650\u516c\u53f8"

REGIONS = [
    ("\u5e7f\u4e1c", "\u5e7f\u5dde\u5e02"),
    ("\u5e7f\u4e1c\u7701", "\u6df1\u5733\u5e02"),
    ("\u5317\u4eac", "\u5317\u4eac\u5e02"),
    ("\u5317\u4eac\u5e02", "\u5317\u4eac\u5e02"),
    ("\u6d59\u6c5f", "\u676d\u5dde\u5e02"),
    ("\u6d59\u6c5f\u7701", "\u5b81\u6ce2\u5e02"),
    ("\u6c5f\u82cf", "\u5357\u4eac\u5e02"),
    ("\u6c5f\u82cf\u7701", "\u82cf\u5dde\u5e02"),
    ("\u4e0a\u6d77", "\u4e0a\u6d77\u5e02"),
    ("\u4e0a\u6d77\u5e02", "\u4e0a\u6d77\u5e02"),
    ("\u56db\u5ddd\u7701", "\u6210\u90fd\u5e02"),
    ("\u6e56\u5317\u7701", "\u6b66\u6c49\u5e02"),
]

INDUSTRIES = [
    "\u8f6f\u4ef6\u548c\u4fe1\u606f\u6280\u672f\u670d\u52a1\u4e1a",
    "\u6c7d\u8f66\u5236\u9020\u4e1a",
    "\u533b\u836f\u5236\u9020\u4e1a",
    "\u8ba1\u7b97\u673a\u901a\u4fe1\u548c\u5176\u4ed6\u7535\u5b50\u8bbe\u5907\u5236\u9020\u4e1a",
    "\u4e13\u7528\u8bbe\u5907\u5236\u9020\u4e1a",
    "\u7535\u6c14\u673a\u68b0\u548c\u5668\u6750\u5236\u9020\u4e1a",
]

OWNERSHIP_TYPES = [
    "\u56fd\u6709",
    "\u6c11\u8425",
    "\u5916\u8d44",
]


def company_catalog():
    rows = []

    for index, stem in enumerate(COMPANY_STEMS, start=1):
        rows.append(
            {
                "stock_code": f"{index:06d}",
                "company_name": stem + COMPANY_SUFFIX,
            }
        )

    return rows


def dirty_company_name(base_name, firm_index, year):
    if year == 2021 and firm_index % 7 == 0:
        return f" {base_name} "

    if year == 2022 and firm_index % 8 == 0:
        stem = COMPANY_STEMS[firm_index]
        return stem + SHORT_SUFFIX

    if year == 2024 and firm_index % 9 == 0:
        return "ST" + base_name

    if year == 2025 and firm_index % 10 == 0:
        return "*ST" + base_name

    return base_name


def dirty_stock_code(code, firm_index, year):
    if firm_index == 0 and year == 2020:
        return f" {code} "

    if firm_index == 1 and year == 2021:
        return int(code)

    if firm_index == 2 and year == 2022:
        return code.lstrip("0")

    if firm_index == 3 and year == 2023:
        return None

    if firm_index == 4 and year == 2024:
        return f"{code} "

    return code


def dirty_year(year, firm_index):
    if firm_index < 5 and year == 2023:
        return f"{year}\u5e74"

    if firm_index in {5, 6, 7} and year == 2022:
        return str(year)

    return year


def build_financials(rng):
    rows = []
    companies = company_catalog()

    for firm_index, company in enumerate(companies):
        for year in range(2020, 2026):
            assets = int(rng.integers(800_000_000, 60_000_000_000))
            liability_ratio = float(rng.uniform(0.15, 0.8))
            liabilities = int(assets * liability_ratio)

            revenue = int(rng.integers(200_000_000, 45_000_000_000))
            margin = float(rng.normal(0.07, 0.11))
            net_profit = int(revenue * margin)

            cash = int(assets * float(rng.uniform(0.03, 0.3)))
            rd_expense = int(revenue * float(rng.uniform(0.005, 0.12)))
            roe = round(net_profit / max(assets - liabilities, 1), 4)
            employees = int(rng.integers(120, 45_000))

            rows.append(
                {
                    "stock_code": dirty_stock_code(
                        company["stock_code"],
                        firm_index,
                        year,
                    ),
                    "company_name": dirty_company_name(
                        company["company_name"],
                        firm_index,
                        year,
                    ),
                    "year": dirty_year(year, firm_index),
                    "total_assets": assets,
                    "total_liabilities": liabilities,
                    "revenue": revenue,
                    "net_profit": net_profit,
                    "cash": cash,
                    "rd_expense": rd_expense,
                    "roe": roe,
                    "employees": employees,
                }
            )

    frame = pd.DataFrame(rows)
    
    mixed_columns = [
    "total_assets",
    "total_liabilities",
    "revenue",
    "net_profit",
    "cash",
    "rd_expense",
    "roe",
    "employees",
    ]

    frame[mixed_columns] = frame[mixed_columns].astype("object")

    frame.loc[8, "total_assets"] = f"{int(frame.loc[8, 'total_assets']):,}"
    frame.loc[29, "total_liabilities"] = "-"
    frame.loc[47, "revenue"] = f"{int(frame.loc[47, 'revenue']):,}"
    frame.loc[63, "net_profit"] = "NA"
    frame.loc[91, "cash"] = ""
    frame.loc[115, "rd_expense"] = "-"

    frame.loc[14, "roe"] = "13.5%"
    frame.loc[58, "roe"] = 13.5
    frame.loc[103, "roe"] = "7.25%"

    frame.loc[27, "employees"] = str(frame.loc[27, "employees"])
    frame.loc[75, "employees"] = None
    frame.loc[130, "employees"] = 9_999_999

    frame.loc[166, "total_assets"] = 9_999_999_999_999
    frame.loc[177, "net_profit"] = -8_888_888_888

    exact_indices = [0, 17, 34, 51, 68, 85, 102, 119, 136, 153]
    exact_duplicates = frame.iloc[exact_indices].copy()

    partial_indices = [10, 27, 44, 61, 78, 95, 112, 129, 146, 163]
    partial_duplicates = frame.iloc[partial_indices].copy()

    partial_duplicates["net_profit"] = [
        int(rng.integers(-500_000_000, 2_000_000_000))
        for _ in range(len(partial_duplicates))
    ]

    frame = pd.concat(
        [frame, exact_duplicates, partial_duplicates],
        ignore_index=True,
    )

    return frame


def profile_company_name(base_name, firm_index):
    if firm_index % 11 == 0:
        stem = COMPANY_STEMS[firm_index]
        return stem + SHORT_SUFFIX

    if firm_index % 13 == 0:
        return f" {base_name} "

    return base_name


def listing_date_value(index):
    year = 2005 + index % 15
    month = index % 12 + 1
    day = index % 25 + 1

    if index % 4 == 0:
        return f"{year:04d}-{month:02d}-{day:02d}"

    if index % 4 == 1:
        return f"{year:04d}/{month:02d}/{day:02d}"

    if index % 4 == 2:
        return 40_000 + index * 17

    return None


def build_profile():
    companies = company_catalog()
    rows = []

    for firm_index, company in enumerate(companies):
        province, city = REGIONS[firm_index % len(REGIONS)]

        code = company["stock_code"]
        if firm_index % 10 == 1:
            code = int(code)
        elif firm_index % 10 == 2:
            code = code.lstrip("0")
        elif firm_index % 10 == 3:
            code = f" {code} "

        ownership = OWNERSHIP_TYPES[firm_index % len(OWNERSHIP_TYPES)]
        if firm_index in {7, 21, 35}:
            ownership = None

        rows.append(
            {
                "stock_code": code,
                "company_name": profile_company_name(
                    company["company_name"],
                    firm_index,
                ),
                "province": province,
                "city": city,
                "industry": INDUSTRIES[firm_index % len(INDUSTRIES)],
                "ownership": ownership,
                "listing_date": listing_date_value(firm_index),
            }
        )

    extra_companies = [
        {
            "stock_code": "900001",
            "company_name": "\u8fdc\u5e06" + COMPANY_SUFFIX,
            "province": "\u5e7f\u4e1c\u7701",
            "city": "\u73e0\u6d77\u5e02",
            "industry": INDUSTRIES[0],
            "ownership": "\u6c11\u8425",
            "listing_date": "2018-06-12",
        },
        {
            "stock_code": "900002",
            "company_name": "\u666f\u548c" + COMPANY_SUFFIX,
            "province": "\u6d59\u6c5f\u7701",
            "city": "\u7ecd\u5174\u5e02",
            "industry": INDUSTRIES[4],
            "ownership": "\u56fd\u6709",
            "listing_date": "2019/09/20",
        },
    ]

    rows.extend(extra_companies)

    return pd.DataFrame(rows)


def build_patents(rng):
    rows = []

    for firm_index in range(40):
        code = f"{firm_index + 1:06d}"

        for year in range(2020, 2026):
            invention = int(rng.poisson(8))
            utility = int(rng.poisson(13))
            citations = int(rng.poisson(max(invention * 3, 1)))

            rows.append(
                {
                    "stock_code": code,
                    "year": year,
                    "invention_patents": invention,
                    "utility_patents": utility,
                    "patent_citations": citations,
                }
            )

    frame = pd.DataFrame(rows)

    frame["stock_code"] = frame["stock_code"].astype("object")

    remove_indices = rng.choice(
        frame.index.to_numpy(),
        size=20,
        replace=False,
    )
    frame = frame.drop(index=remove_indices).reset_index(drop=True)

    frame.loc[3, "stock_code"] = int(frame.loc[3, "stock_code"])
    frame.loc[17, "stock_code"] = f" {frame.loc[17, 'stock_code']} "
    frame.loc[35, "stock_code"] = str(frame.loc[35, "stock_code"]).lstrip("0")

    frame.loc[24, "invention_patents"] = None
    frame.loc[67, "utility_patents"] = None
    frame.loc[101, "patent_citations"] = None
    frame.loc[140, "patent_citations"] = 99_999

    duplicates = frame.iloc[[4, 33, 72, 111, 150]].copy()
    duplicates.loc[duplicates.index[-1], "patent_citations"] = 1234

    frame = pd.concat([frame, duplicates], ignore_index=True)

    return frame


def write_datasets(output_dir):
    rng = np.random.default_rng(SEED)

    financials = build_financials(rng)
    profile = build_profile()
    patents = build_patents(rng)

    output_dir.mkdir(parents=True, exist_ok=True)

    financials.to_excel(
        output_dir / "firm_financials.xlsx",
        index=False,
        engine="openpyxl",
    )

    profile.to_csv(
        output_dir / "firm_profile.csv",
        index=False,
        encoding="utf-8-sig",
    )

    patents.to_csv(
        output_dir / "patents.csv",
        index=False,
        encoding="utf-8-sig",
    )

    print(f"firm_financials.xlsx: {financials.shape}")
    print(f"firm_profile.csv: {profile.shape}")
    print(f"patents.csv: {patents.shape}")


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output-dir",
        type=Path,
        required=True,
    )
    return parser.parse_args()


def main():
    args = parse_args()
    write_datasets(args.output_dir)


if __name__ == "__main__":
    main()
