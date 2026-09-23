import pandas as pd

from src.build_real_financial_panel import (
    SourceBlocked,
    construct_variables,
    extract_financial_rows,
    fetch_company_with_fallback,
    financial_cache_path,
    run_financial_panel,
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
    employee = pd.DataFrame({"REPORT_DATE": ["2020-12-31", "2021-12-31"], "STAFF_NUM": [100, 110]})
    result = extract_financial_rows(
        "SSE", "600000", "600000", "SSE:600000:2000-01-01", balance, profit, employee, (2020, 2021)
    )
    assert result.loc[result["year"].eq(2020), "revenue"].iloc[0] == 50.0
    assert result["financial_query_code"].eq("600000").all()
    assert pd.isna(result.loc[result["year"].eq(2021), "rd_expense"]).iloc[0]
    assert result.loc[result["year"].eq(2020), "balance_available"].iloc[0]
    assert result.loc[result["year"].eq(2020), "failure_reason"].iloc[0] == ""


def test_financial_cache_is_keyed_by_firm_key(tmp_path):
    first = financial_cache_path(tmp_path, "SSE:600000:2000-01-01")
    second = financial_cache_path(tmp_path, "SSE:600000:2010-01-01")
    assert first != second
    assert first.name.endswith(".parquet")


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


def test_financial_fallback_checks_only_valid_years(monkeypatch):
    def fake_fetch(exchange, current, query, firm_key, valid_years):
        result = pd.DataFrame({"year": list(range(2020, 2026))})
        result["financial_success"] = result["year"].isin(valid_years)
        return result

    monkeypatch.setattr("src.build_real_financial_panel._fetch_one_company_for_years", fake_fetch)
    result = fetch_company_with_fallback(
        "SSE", "600000", ["600000"], "SSE:600000:2000-01-01", (2022, 2023, 2024)
    )
    assert result.loc[result["year"].isin((2022, 2023, 2024)), "financial_success"].all()
    assert not result.loc[~result["year"].isin((2022, 2023, 2024)), "financial_success"].any()


def test_financial_keys_equal_valid_universe_keys(monkeypatch, tmp_path):
    universe = pd.DataFrame(
        {
            "firm_key": ["SSE:600000:2000-01-01"] * 3,
            "exchange": ["SSE"] * 3,
            "stock_code_current": ["600000"] * 3,
            "year": [2022, 2023, 2024],
        }
    )

    def fake_fetch(exchange, current, query, firm_key, valid_years):
        rows = []
        for year in range(2020, 2026):
            rows.append(
                {
                    "exchange": exchange,
                    "firm_key": firm_key,
                    "stock_code_current": current,
                    "year": year,
                    "financial_query_code": query,
                    "total_assets": 100.0,
                    "total_liabilities": 40.0,
                    "cash": 20.0,
                    "revenue": 50.0,
                    "net_profit": 5.0,
                    "rd_expense": 2.0,
                    "employees": 10.0,
                    "financial_success": year in valid_years,
                }
            )
        return pd.DataFrame(rows)

    monkeypatch.setattr("src.build_real_financial_panel._fetch_one_company_for_years", fake_fetch)
    result = run_financial_panel(universe, tmp_path, request_spacing=0)
    assert set(map(tuple, result[["firm_key", "year"]].to_numpy())) == set(
        map(tuple, universe[["firm_key", "year"]].to_numpy())
    )


def test_stale_cache_is_not_used_for_valid_years(monkeypatch, tmp_path):
    universe = pd.DataFrame(
        {
            "firm_key": ["SSE:600000:2000-01-01"] * 2,
            "exchange": ["SSE"] * 2,
            "stock_code_current": ["600000"] * 2,
            "year": [2022, 2023],
        }
    )
    stale = pd.DataFrame(
        {
            "firm_key": ["SSE:600000:2000-01-01"],
            "year": [2020],
            "financial_success": [True],
        }
    )
    stale.to_parquet(tmp_path / "SSE_600000.parquet", index=False)

    def fake_fetch(exchange, current, query, firm_key, valid_years):
        return pd.DataFrame(
            {
                "exchange": [exchange] * len(valid_years),
                "firm_key": [firm_key] * len(valid_years),
                "stock_code_current": [current] * len(valid_years),
                "year": list(valid_years),
                "financial_query_code": [query] * len(valid_years),
                "total_assets": [100.0] * len(valid_years),
                "total_liabilities": [40.0] * len(valid_years),
                "cash": [20.0] * len(valid_years),
                "revenue": [50.0] * len(valid_years),
                "net_profit": [5.0] * len(valid_years),
                "rd_expense": [2.0] * len(valid_years),
                "employees": [10.0] * len(valid_years),
                "financial_success": [True] * len(valid_years),
            }
        )

    monkeypatch.setattr("src.build_real_financial_panel._fetch_one_company_for_years", fake_fetch)
    result = run_financial_panel(universe, tmp_path, request_spacing=0)
    assert set(result.year) == {2022, 2023}


def test_financial_cache_reuse(monkeypatch, tmp_path):
    universe = pd.DataFrame(
        {
            "firm_key": ["SSE:600000:2000-01-01"] * 2,
            "exchange": ["SSE"] * 2,
            "stock_code_current": ["600000"] * 2,
            "year": [2022, 2023],
        }
    )
    calls = {"count": 0}

    def fake_fetch(exchange, current, query, firm_key, valid_years):
        calls["count"] += 1
        return pd.DataFrame(
            {
                "exchange": [exchange] * len(valid_years),
                "firm_key": [firm_key] * len(valid_years),
                "stock_code_current": [current] * len(valid_years),
                "year": list(valid_years),
                "financial_query_code": [query] * len(valid_years),
                "total_assets": [100.0] * len(valid_years),
                "total_liabilities": [40.0] * len(valid_years),
                "cash": [20.0] * len(valid_years),
                "revenue": [50.0] * len(valid_years),
                "net_profit": [5.0] * len(valid_years),
                "rd_expense": [2.0] * len(valid_years),
                "employees": [10.0] * len(valid_years),
                "financial_success": [True] * len(valid_years),
                "failure_reason": [""] * len(valid_years),
            }
        )

    monkeypatch.setattr("src.build_real_financial_panel.fetch_company_with_fallback", fake_fetch)
    first = run_financial_panel(universe, tmp_path, request_spacing=0)
    second = run_financial_panel(universe, tmp_path, request_spacing=0)
    assert calls["count"] == 1
    pd.testing.assert_frame_equal(first, second)
