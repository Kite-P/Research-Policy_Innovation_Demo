from __future__ import annotations

import time

import akshare as ak
import pandas as pd

PILOT_YEARS = (2022, 2023, 2024)
CORE_FIELDS = ("total_assets", "total_liabilities", "cash", "revenue", "net_profit")
FIELD_CANDIDATES = {
    "total_assets": (("TOTAL_ASSETS",), ("TOTAL", "ASSET")),
    "total_liabilities": (("TOTAL_LIABILITIES", "TOTAL_LIABILITY"), ("TOTAL", "LIABIL")),
    "cash": (("MONETARYFUNDS", "MONETARY_FUNDS"), ("MONETARY", "FUND")),
    "revenue": (("TOTAL_OPERATE_INCOME", "OPERATE_INCOME"), ("OPERATE", "INCOME")),
    "net_profit": (("PARENT_NETPROFIT", "PARENT_NET_PROFIT", "NETPROFIT"), ("NET", "PROFIT")),
    "rd_expense": (
        ("RESEARCH_EXPENSE", "RESEARCH_AND_DEVELOPMENT_EXPENSE"),
        ("RESEARCH", "EXPENSE"),
    ),
}
EMPLOYEE_PATTERNS = ("EMPLOYEE", "STAFF", "PERSONNEL")


def to_em_symbol(exchange: str, stock_code: str) -> str:
    prefixes = {"SSE": "SH", "SZSE": "SZ", "BSE": "BJ"}
    if exchange not in prefixes:
        raise ValueError(f"unsupported exchange: {exchange}")
    return f"{prefixes[exchange]}{str(stock_code).zfill(6)}"


def select_year_end_rows(
    frame: pd.DataFrame,
    years: tuple[int, ...] = PILOT_YEARS,
) -> pd.DataFrame:
    if "REPORT_DATE" not in frame.columns:
        return frame.iloc[0:0].copy()
    result = frame.copy()
    result["_report_date"] = pd.to_datetime(result["REPORT_DATE"], errors="coerce")
    dates = [pd.Timestamp(year=year, month=12, day=31) for year in years]
    return result.loc[result["_report_date"].isin(dates)].copy()


def _normalize_column(value: object) -> str:
    return str(value).strip().upper()


def resolve_column(
    columns: list[str],
    exact_candidates: tuple[str, ...],
    contains_candidates: tuple[str, ...] = (),
) -> str | None:
    normalized = {_normalize_column(column): column for column in columns}
    exact_matches = [
        normalized[candidate] for candidate in exact_candidates if candidate in normalized
    ]
    if len(exact_matches) == 1:
        return exact_matches[0]
    if len(exact_matches) > 1:
        return None
    if not contains_candidates:
        return None
    terms = tuple(_normalize_column(term) for term in contains_candidates)
    contains_matches = [
        original
        for normalized_name, original in normalized.items()
        if all(term in normalized_name for term in terms)
    ]
    return contains_matches[0] if len(contains_matches) == 1 else None


def _call_statement(function, symbol: str) -> pd.DataFrame:
    last_error: Exception | None = None
    for attempt in range(3):
        try:
            return function(symbol=symbol)
        except Exception as exc:  # AKShare wraps different HTTP clients
            last_error = exc
            message = str(exc).lower()
            if any(token in message for token in ("403", "429", "captcha", "verification")):
                break
            if attempt < 2 and any(
                token in message
                for token in ("timeout", "connection", "reset", "500", "502", "503", "504")
            ):
                time.sleep(1.0)
                continue
            break
    if last_error is not None:
        raise last_error
    return pd.DataFrame()


def fetch_financial_statements(exchange: str, stock_code: str) -> dict[str, pd.DataFrame]:
    symbol = to_em_symbol(exchange, stock_code)
    return {
        "balance_sheet": _call_statement(ak.stock_balance_sheet_by_report_em, symbol),
        "profit_sheet": _call_statement(ak.stock_profit_sheet_by_report_em, symbol),
    }


def _column_inventory(frames: dict[str, pd.DataFrame]) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for statement, frame in frames.items():
        for column in frame.columns:
            matched_target = None
            match_status = "unavailable"
            for target, (exact, contains) in FIELD_CANDIDATES.items():
                if column in exact:
                    matched_target = target
                    match_status = "exact"
                elif all(term in _normalize_column(column) for term in contains):
                    matched_target = target
                    match_status = "candidate_contains"
            if any(pattern in _normalize_column(column) for pattern in EMPLOYEE_PATTERNS):
                matched_target = "employees"
                match_status = "employee_candidate"
            rows.append(
                {
                    "statement": statement,
                    "column_name": column,
                    "matched_target": matched_target,
                    "match_status": match_status,
                    "example_nonmissing_count": int(frame[column].notna().sum()),
                }
            )
    return pd.DataFrame(rows)


def _resolve_field(frame: pd.DataFrame, target: str) -> str | None:
    exact, contains = FIELD_CANDIDATES[target]
    return resolve_column(list(frame.columns), exact, contains)


def _field_match_status(frame: pd.DataFrame, target: str) -> tuple[str | None, str]:
    exact, contains = FIELD_CANDIDATES[target]
    normalized = {_normalize_column(column): column for column in frame.columns}
    exact_matches = [normalized[candidate] for candidate in exact if candidate in normalized]
    if len(exact_matches) == 1:
        return exact_matches[0], "exact"
    if len(exact_matches) > 1:
        return None, "ambiguous"
    terms = tuple(_normalize_column(term) for term in contains)
    contains_matches = [
        original
        for normalized_name, original in normalized.items()
        if all(term in normalized_name for term in terms)
    ]
    if len(contains_matches) == 1:
        return contains_matches[0], "candidate_contains"
    if len(contains_matches) > 1:
        return None, "ambiguous"
    return None, "unavailable"


def _year_row(frame: pd.DataFrame, year: int) -> tuple[pd.Series | None, bool]:
    rows = frame.loc[frame["_report_date"].eq(pd.Timestamp(year=year, month=12, day=31))]
    if len(rows) != 1:
        return (rows.iloc[0] if len(rows) == 1 else None), len(rows) > 1
    return rows.iloc[0], False


def run_financial_pilot(pilot: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    results: list[dict[str, object]] = []
    inventories: list[pd.DataFrame] = []
    for index, pilot_row in pilot.iterrows():
        stock_code = pilot_row["stock_code"]
        exchange = pilot_row["exchange"]
        base_error: list[str] = []
        try:
            frames = fetch_financial_statements(exchange, stock_code)
            for name, frame in frames.items():
                frames[name] = select_year_end_rows(frame)
            inventories.append(_column_inventory(frames))
        except Exception as exc:
            frames = {"balance_sheet": pd.DataFrame(), "profit_sheet": pd.DataFrame()}
            base_error.append(f"{type(exc).__name__}: {str(exc)[:160]}")

        for year in PILOT_YEARS:
            row: dict[str, object] = {
                "stock_code": stock_code,
                "exchange": exchange,
                "year": year,
                "total_assets": None,
                "total_liabilities": None,
                "cash": None,
                "revenue": None,
                "net_profit": None,
                "rd_expense": None,
                "employees": None,
                "financial_success": False,
                "ambiguous_report_rows": False,
                "financial_error": "; ".join(base_error),
            }
            field_errors: list[str] = []
            for target, statement in (
                ("total_assets", "balance_sheet"),
                ("total_liabilities", "balance_sheet"),
                ("cash", "balance_sheet"),
                ("revenue", "profit_sheet"),
                ("net_profit", "profit_sheet"),
                ("rd_expense", "profit_sheet"),
            ):
                frame = frames[statement]
                source_column, match_status = (
                    _field_match_status(frame, target) if not frame.empty else (None, "unavailable")
                )
                source_row, ambiguous = _year_row(frame, year) if not frame.empty else (None, False)
                row["ambiguous_report_rows"] = bool(row["ambiguous_report_rows"] or ambiguous)
                if ambiguous:
                    field_errors.append(f"ambiguous_{year}_{statement}")
                elif source_column is None:
                    field_errors.append(f"{match_status}_{target}")
                elif source_row is not None:
                    row[target] = source_row.get(source_column)
            complete = all(pd.notna(row[field]) for field in CORE_FIELDS)
            row["financial_success"] = bool(complete and not row["ambiguous_report_rows"])
            if not complete:
                field_errors.append("core_fields_incomplete")
            row["financial_error"] = "; ".join(
                error for error in [row["financial_error"], *field_errors] if error
            )
            results.append(row)
        if index < len(pilot) - 1:
            time.sleep(1.0)
    inventory = pd.concat(inventories, ignore_index=True) if inventories else pd.DataFrame()
    return pd.DataFrame(results), inventory
