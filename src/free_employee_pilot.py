from __future__ import annotations

import time

import akshare as ak
import pandas as pd

PILOT_YEARS = (2022, 2023, 2024)


def to_f10_symbol(exchange: str, stock_code: str) -> str:
    suffix = {"SSE": "SH", "SZSE": "SZ", "BSE": "BJ"}.get(exchange)
    if suffix is None:
        raise ValueError(f"unsupported exchange: {exchange}")
    return f"{str(stock_code).zfill(6)}.{suffix}"


def fetch_main_financial_indicators(exchange: str, stock_code: str) -> pd.DataFrame:
    symbol = to_f10_symbol(exchange, stock_code)
    return ak.stock_financial_analysis_indicator_em(symbol=symbol, indicator="按报告期")


def select_staff_year_end_rows(
    frame: pd.DataFrame,
    years: tuple[int, ...] = PILOT_YEARS,
) -> pd.DataFrame:
    if "REPORT_DATE" not in frame.columns:
        return frame.iloc[0:0].copy()
    result = frame.copy()
    result["_report_date"] = pd.to_datetime(result["REPORT_DATE"], errors="coerce")
    dates = [pd.Timestamp(year=year, month=12, day=31) for year in years]
    return result.loc[result["_report_date"].isin(dates)].copy()


def run_employee_pilot(pilot: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for index, pilot_row in pilot.iterrows():
        stock_code = pilot_row["stock_code"]
        exchange = pilot_row["exchange"]
        try:
            frame = fetch_main_financial_indicators(exchange, stock_code)
            year_end = select_staff_year_end_rows(frame)
            has_staff = "STAFF_NUM" in year_end.columns
            for year in PILOT_YEARS:
                matching = year_end.loc[
                    year_end["_report_date"].eq(pd.Timestamp(year=year, month=12, day=31))
                ]
                if len(matching) == 1 and has_staff:
                    value = matching.iloc[0]["STAFF_NUM"]
                    success = pd.notna(value)
                    error = None if success else "staff_num_missing"
                    report_date = matching.iloc[0].get("REPORT_DATE")
                else:
                    value = None
                    success = False
                    error = "staff_num_unavailable_or_ambiguous"
                    report_date = None
                rows.append(
                    {
                        "stock_code": stock_code,
                        "exchange": exchange,
                        "year": year,
                        "staff_num": value,
                        "report_date": report_date,
                        "employee_success": bool(success),
                        "employee_error": error,
                    }
                )
        except Exception as exc:
            for year in PILOT_YEARS:
                rows.append(
                    {
                        "stock_code": stock_code,
                        "exchange": exchange,
                        "year": year,
                        "staff_num": None,
                        "report_date": None,
                        "employee_success": False,
                        "employee_error": f"{type(exc).__name__}: {str(exc)[:160]}",
                    }
                )
        if index < len(pilot) - 1:
            time.sleep(1.0)
    return pd.DataFrame(rows)
