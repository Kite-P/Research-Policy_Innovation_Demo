import pandas as pd

from scripts.run_financial_pilot import finalize_financial_gate, select_pilot_universe_years


def test_pilot_year_filter_keeps_only_2020_to_2025():
    universe = pd.DataFrame(
        {
            "firm_key": ["SSE:1:2000"] * 3,
            "year": [2019, 2020, 2025],
        }
    )
    result = select_pilot_universe_years(universe)
    assert result["year"].tolist() == [2020, 2025]


def test_finalize_financial_gate_separates_six_required_groups(tmp_path):
    sample = pd.DataFrame(
        {
            "firm_key": ["SSE:1", "SSE:2", "SZSE:3", "BSE:4", "BSE:5", "SSE:6"],
            "exchange": ["SSE", "SSE", "SZSE", "BSE", "BSE", "SSE"],
            "pilot_stratum": [
                "seasoned_current_sse",
                "recent_ipo_sse",
                "seasoned_current_szse",
                "bse_transferred",
                "bse_post_2021",
                "delisted_sse",
            ],
        }
    )
    panel = sample.assign(
        year=2025,
        delisting_date=[pd.NaT, pd.NaT, pd.NaT, pd.NaT, pd.NaT, pd.Timestamp("2025-01-01")],
        financial_success=[True, True, True, False, True, False],
        total_assets=1.0,
        total_liabilities=1.0,
        cash=1.0,
        revenue=1.0,
        net_profit=1.0,
        employees=1.0,
        rd_expense=1.0,
        failure_reason="",
    )
    result = finalize_financial_gate(panel, sample, tmp_path)
    assert result["sample_type"].tolist() == [
        "current_nonfinancial",
        "current_nonfinancial",
        "delisted",
        "delisted",
        "bse_transferred",
        "bse_native",
    ]
    assert set(result["exchange"]) == {"SSE", "SZSE", "BSE"}
