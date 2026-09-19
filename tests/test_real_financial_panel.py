import pandas as pd

from src.build_real_financial_panel import (
    SourceBlocked,
    construct_variables,
    extract_financial_rows,
)


def test_extract_financial_rows_uses_frozen_fields_and_query_code():
    balance = pd.DataFrame(
        {
            "REPORT_DATE": ["2020-12-31", "2021-12-31"],
            "TOTAL_ASSETS": [100.0, 120.0],
            "TOTAL_LIABILITIES": [40.0, 48.0],
            "MONETARYFUNDS": [20.0, 24.0],
        }
    )
    profit = pd.DataFrame(
        {
            "REPORT_DATE": ["2020-12-31", "2021-12-31"],
            "TOTAL_OPERATE_INCOME": [50.0, 60.0],
            "PARENT_NETPROFIT": [5.0, 6.0],
            "RESEARCH_EXPENSE": [2.0, None],
        }
    )
    employee = pd.DataFrame(
        {"REPORT_DATE": ["2020-12-31", "2021-12-31"], "STAFF_NUM": [100, 110]}
    )
    result = extract_financial_rows(
        "SSE", "600000", "600000", balance, profit, employee, (2020, 2021)
    )
    assert result.loc[result["year"].eq(2020), "revenue"].iloc[0] == 50.0
    assert result["financial_query_code"].eq("600000").all()
    assert pd.isna(result.loc[result["year"].eq(2021), "rd_expense"]).iloc[0]


def test_construct_variables_preserves_invalid_values_as_missing():
    frame = pd.DataFrame(
        {
            "total_assets": [100.0, 0.0],
            "total_liabilities": [50.0, 2.0],
            "cash": [10.0, 1.0],
            "revenue": [20.0, 0.0],
            "net_profit": [5.0, -1.0],
            "employees": [10.0, 0.0],
            "rd_expense": [2.0, 1.0],
        }
    )
    result = construct_variables(frame)
    assert result.loc[0, "size_ln"] > 0
    assert pd.isna(result.loc[1, "size_ln"])
    assert pd.isna(result.loc[1, "employee_ln"])
    assert pd.isna(result.loc[1, "rd_intensity"])


def test_blocking_errors_are_stopped_immediately():
    blocked = SourceBlocked.from_exception(RuntimeError("HTTP 429 verification required"))
    assert "429" in str(blocked)
