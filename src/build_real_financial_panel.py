from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import akshare as ak
import numpy as np
import pandas as pd

try:
    from .bse_code_mapping import load_bse_mapping, resolve_bse_codes
    from .free_financial_pilot import to_em_symbol
except ImportError:
    from bse_code_mapping import load_bse_mapping, resolve_bse_codes
    from free_financial_pilot import to_em_symbol

CORE_FIELDS = (
    "total_assets",
    "total_liabilities",
    "cash",
    "revenue",
    "net_profit",
    "employees",
)
YEARS = tuple(range(2020, 2026))


class SourceBlocked(RuntimeError):
    @classmethod
    def from_exception(cls, exc: Exception) -> "SourceBlocked":
        return cls(str(exc))


def _is_blocking_error(exc: Exception) -> bool:
    text = str(exc).lower()
    return any(token in text for token in ("403", "429", "captcha", "verification"))


def _call(function, **kwargs) -> pd.DataFrame:
    last_error: Exception | None = None
    for attempt in range(3):
        try:
            return function(**kwargs)
        except Exception as exc:
            last_error = exc
            if _is_blocking_error(exc):
                raise SourceBlocked.from_exception(exc) from exc
            if attempt < 2 and any(
                token in str(exc).lower()
                for token in ("timeout", "connection", "reset", "500", "502", "503", "504")
            ):
                time.sleep(1.0)
                continue
            break
    if last_error is not None:
        raise last_error
    return pd.DataFrame()


def _year_rows(frame: pd.DataFrame, years: tuple[int, ...]) -> dict[int, pd.Series | None]:
    if "REPORT_DATE" not in frame.columns:
        return {year: None for year in years}
    dates = pd.to_datetime(frame["REPORT_DATE"], errors="coerce")
    result: dict[int, pd.Series | None] = {}
    for year in years:
        rows = frame.loc[dates.eq(pd.Timestamp(year=year, month=12, day=31))]
        result[year] = rows.iloc[0] if len(rows) == 1 else None
    return result


def extract_financial_rows(
    exchange: str,
    current_stock_code: str,
    financial_query_code: str,
    firm_key: str,
    balance: pd.DataFrame,
    profit: pd.DataFrame,
    employee: pd.DataFrame,
    years: tuple[int, ...] = YEARS,
) -> pd.DataFrame:
    balances = _year_rows(balance, years)
    profits = _year_rows(profit, years)
    employees = _year_rows(employee, years)
    rows: list[dict[str, object]] = []
    for year in years:
        balance_row = balances[year]
        profit_row = profits[year]
        employee_row = employees[year]
        row: dict[str, object] = {
            "exchange": exchange,
            "firm_key": firm_key,
            "stock_code_current": str(current_stock_code).zfill(6),
            "year": year,
            "financial_query_code": str(financial_query_code).zfill(6),
            "total_assets": (
                balance_row.get("TOTAL_ASSETS") if balance_row is not None else np.nan
            ),
            "total_liabilities": (
                balance_row.get("TOTAL_LIABILITIES") if balance_row is not None else np.nan
            ),
            "cash": (
                balance_row.get("MONETARYFUNDS", balance_row.get("MONETARY_FUNDS"))
                if balance_row is not None
                else np.nan
            ),
            "revenue": profit_row.get("TOTAL_OPERATE_INCOME") if profit_row is not None else np.nan,
            "net_profit": profit_row.get("PARENT_NETPROFIT") if profit_row is not None else np.nan,
            "rd_expense": profit_row.get("RESEARCH_EXPENSE") if profit_row is not None else np.nan,
            "employees": employee_row.get("STAFF_NUM") if employee_row is not None else np.nan,
        }
        row["financial_success"] = all(pd.notna(row[field]) for field in CORE_FIELDS)
        rows.append(row)
    return pd.DataFrame(rows)


def construct_variables(frame: pd.DataFrame) -> pd.DataFrame:
    result = frame.copy()
    positive = {
        column: result[column].where(result[column] > 0)
        for column in ("total_assets", "employees")
    }
    assets = result["total_assets"].where(result["total_assets"] > 0)
    revenue = result["revenue"].where(result["revenue"] > 0)
    result["size_ln"] = np.log(positive["total_assets"])
    result["leverage"] = result["total_liabilities"].where(assets.notna()) / assets
    result["roa"] = result["net_profit"].where(assets.notna()) / assets
    result["cash_ratio"] = result["cash"].where(assets.notna()) / assets
    result["employee_ln"] = np.log(positive["employees"])
    result["rd_intensity"] = result["rd_expense"].where(revenue.notna()) / revenue
    for column in ("size_ln", "leverage", "roa", "cash_ratio", "employee_ln", "rd_intensity"):
        result[column] = result[column].replace([np.inf, -np.inf], np.nan)
    return result


def _fetch_one_company_for_years(
    exchange: str,
    current_code: str,
    query_code: str,
    firm_key: str,
    valid_years: tuple[int, ...],
) -> pd.DataFrame:
    symbol = to_em_symbol(exchange, query_code)
    suffix = {"SSE": "SH", "SZSE": "SZ", "BSE": "BJ"}[exchange]
    balance = _call(ak.stock_balance_sheet_by_report_em, symbol=symbol)
    profit = _call(ak.stock_profit_sheet_by_report_em, symbol=symbol)
    employee = _call(
        ak.stock_financial_analysis_indicator_em,
        symbol=f"{query_code.zfill(6)}.{suffix}",
        indicator="按报告期",
    )
    return extract_financial_rows(
        exchange,
        current_code,
        query_code,
        firm_key,
        balance,
        profit,
        employee,
        valid_years,
    )


def fetch_company_with_fallback(
    exchange: str,
    current_code: str,
    query_codes: list[str],
    firm_key: str,
    valid_years: tuple[int, ...],
) -> pd.DataFrame:
    last_error: Exception | None = None
    for query_code in query_codes:
        try:
            frame = _fetch_one_company_for_years(
                exchange, current_code, query_code, firm_key, valid_years
            )
            valid_success = frame.loc[frame["year"].isin(valid_years), "financial_success"]
            if len(valid_success) == len(valid_years) and valid_success.all():
                return frame
        except SourceBlocked:
            raise
        except Exception as exc:
            last_error = exc
    if last_error is not None:
        raise last_error
    return _fetch_one_company_for_years(
        exchange, current_code, query_codes[-1], firm_key, valid_years
    )


def _empty_financial_rows(
    exchange: str, current_code: str, firm_key: str, valid_years: tuple[int, ...], error: str
) -> pd.DataFrame:
    rows = []
    for year in valid_years:
        row = {
            "exchange": exchange,
            "firm_key": firm_key,
            "stock_code_current": str(current_code).zfill(6),
            "year": year,
            "financial_query_code": pd.NA,
            **{field: np.nan for field in CORE_FIELDS},
            "rd_expense": np.nan,
            "financial_success": False,
            "financial_error": error,
        }
        rows.append(row)
    return pd.DataFrame(rows)


def _cache_path(cache_dir: Path, exchange: str, current_code: str) -> Path:
    return cache_dir / f"{exchange}_{str(current_code).zfill(6)}.parquet"


def run_financial_panel(
    universe: pd.DataFrame,
    cache_dir: Path,
    mapping: pd.DataFrame | None = None,
    request_spacing: float = 1.0,
) -> pd.DataFrame:
    cache_dir.mkdir(parents=True, exist_ok=True)
    mapping = (
        mapping
        if mapping is not None
        else pd.DataFrame(columns=["old_stock_code", "new_stock_code"])
    )
    rows: list[pd.DataFrame] = []
    valid_pairs = universe[["firm_key", "year"]].drop_duplicates()
    firms = universe.drop_duplicates(subset=["firm_key"]).sort_values(
        ["exchange", "stock_code_current"]
    )
    for index, firm in enumerate(firms.itertuples(index=False)):
        path = _cache_path(cache_dir, firm.exchange, firm.stock_code_current)
        valid_years = tuple(
            sorted(
                valid_pairs.loc[
                    valid_pairs["firm_key"].eq(firm.firm_key), "year"
                ].astype(int)
            )
        )
        expected_keys = set(zip([firm.firm_key] * len(valid_years), valid_years))
        cached = pd.read_parquet(path) if path.exists() else None
        cached_keys = (
            set(zip(cached["firm_key"], cached["year"].astype(int)))
            if cached is not None and {"firm_key", "year"}.issubset(cached.columns)
            else set()
        )
        if cached is not None and cached_keys == expected_keys:
            rows.append(cached)
        else:
            query_codes = (
                resolve_bse_codes(firm.stock_code_current, mapping)
                if firm.exchange == "BSE"
                else [str(firm.stock_code_current).zfill(6)]
            )
            try:
                frame = fetch_company_with_fallback(
                    firm.exchange,
                    firm.stock_code_current,
                    query_codes,
                    firm.firm_key,
                    valid_years,
                )
            except SourceBlocked:
                raise
            except Exception as exc:
                frame = _empty_financial_rows(
                    firm.exchange,
                    firm.stock_code_current,
                    firm.firm_key,
                    valid_years,
                    f"{type(exc).__name__}: {str(exc)[:160]}",
                )
            frame.to_parquet(path, index=False)
            rows.append(frame)
        if index < len(firms) - 1:
            time.sleep(request_spacing)
    actual = pd.concat(rows, ignore_index=True) if rows else pd.DataFrame()
    result = valid_pairs.merge(actual, on=["firm_key", "year"], how="left")
    return construct_variables(result)


def coverage_table(panel: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for (exchange, year), group in panel.groupby(["exchange", "year"], dropna=False):
        for field in CORE_FIELDS + ("rd_expense",):
            rows.append(
                {
                    "exchange": exchange,
                    "year": year,
                    "field": field,
                    "coverage": int(group[field].notna().sum()),
                    "denominator": len(group),
                }
            )
    return pd.DataFrame(rows)


def _stata_ready(frame: pd.DataFrame) -> pd.DataFrame:
    result = frame.copy()
    for column in result.select_dtypes(include=["object", "string"]).columns:
        result[column] = result[column].where(result[column].notna(), "").astype(str)
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--universe", type=Path, default=Path("data/processed/real_company_universe.parquet")
    )
    parser.add_argument("--cache", type=Path, default=Path("results/real_financial_fetch/cache"))
    parser.add_argument("--mapping", type=Path)
    parser.add_argument("--output", type=Path, default=Path("data/processed"))
    parser.add_argument("--spacing", type=float, default=1.0)
    args = parser.parse_args()
    universe = pd.read_parquet(args.universe)
    mapping = load_bse_mapping(args.mapping) if args.mapping else None
    panel = run_financial_panel(universe, args.cache, mapping, args.spacing)
    args.output.mkdir(parents=True, exist_ok=True)
    panel.to_parquet(args.output / "real_financials_clean.parquet", index=False)
    _stata_ready(panel).to_stata(
        args.output / "real_financials_clean.dta", write_index=False, version=118
    )
    coverage_table(panel).to_csv(args.output / "real_financials_coverage.csv", index=False)
    print(json.dumps({"rows": len(panel), "firms": panel["stock_code_current"].nunique()}))


if __name__ == "__main__":
    main()
