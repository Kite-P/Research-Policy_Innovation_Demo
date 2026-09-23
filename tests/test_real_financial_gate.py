import pandas as pd

from src.real_financial_gate import (
    build_financial_pilot_sample,
    build_financial_stress_test_sample,
    failure_decomposition_by_group,
    financial_gate,
    stable_pick,
)


def _universe():
    return pd.DataFrame(
        {
            "firm_key": ["SSE:1:2020", "SSE:2:2020", "BSE:3:2022"],
            "exchange": ["SSE", "SSE", "BSE"],
            "listing_date": pd.to_datetime(["2010-01-01", "2010-01-01", "2022-01-01"]),
            "predecessor_listing_date": pd.to_datetime([pd.NaT, pd.NaT, pd.NaT]),
            "market_listing_date": pd.to_datetime(["2010-01-01", "2010-01-01", "2022-01-01"]),
            "delisting_date": [pd.NaT, pd.NaT, pd.NaT],
            "industry_csrc": ["制造业-通用设备制造业", "金融业-货币金融服务", pd.NA],
            "year": [2025, 2025, 2025],
        }
    )


def test_financial_pilot_excludes_financial_firms():
    sample = build_financial_pilot_sample(_universe())
    assert not sample["firm_key"].eq("SSE:2:2020").any()


def test_financial_pilot_uses_sha256_sampling():
    frame = pd.DataFrame({"firm_key": [f"SSE:{i}:2020" for i in range(20)]})
    a = stable_pick(frame, 5, "20260923", "test")
    b = stable_pick(frame, 5, "20260923", "test")
    assert a["firm_key"].tolist() == b["firm_key"].tolist()


def test_financial_pilot_contains_bse_native_when_available():
    frame = _universe()
    frame.loc[frame["firm_key"].eq("BSE:3:2022"), "industry_csrc"] = "制造业-通用设备制造业"
    sample = build_financial_pilot_sample(frame)
    assert sample["firm_key"].eq("BSE:3:2022").any()


def test_financial_stress_sample_is_deterministic():
    frame = pd.DataFrame(
        {
            "firm_key": [f"SSE:{i}:2020" for i in range(40)]
            + [f"SZSE:{i}:2020" for i in range(40, 80)],
            "exchange": ["SSE"] * 40 + ["SZSE"] * 40,
            "listing_date": pd.to_datetime(["2010-01-01"] * 80),
            "predecessor_listing_date": pd.NaT,
            "delisting_date": pd.NaT,
            "industry_csrc": ["制造业-通用设备制造业"] * 80,
        }
    )
    a = build_financial_stress_test_sample(frame, seed="test-seed")
    b = build_financial_stress_test_sample(frame.sample(frac=1, random_state=7), seed="test-seed")
    assert a[["firm_key", "pilot_stratum"]].reset_index(drop=True).equals(
        b[["firm_key", "pilot_stratum"]].reset_index(drop=True)
    )


def test_financial_stress_sample_does_not_cross_fill_strata():
    frame = _universe().assign(
        stock_code_current=["000001", "000002", "830001"],
        industry_csrc="制造业-通用设备制造业",
    )
    sample = build_financial_stress_test_sample(frame)
    assert set(sample["pilot_stratum"]) == {"seasoned_current_sse", "bse_post_2021"}


def test_failure_decomposition_groups_by_exchange_year():
    panel = _universe().assign(
        pilot_stratum="seasoned_current_sse",
        total_assets=[1.0, None, 1.0],
        total_liabilities=[1.0, None, 1.0],
        cash=[1.0, 1.0, 1.0],
        revenue=[1.0, 1.0, 1.0],
        net_profit=[1.0, 1.0, 1.0],
        employees=[1.0, 1.0, 1.0],
        failure_reason=["", "BALANCE_SOURCE_EMPTY", ""],
    )
    result = failure_decomposition_by_group(panel)
    assert {"exchange", "year", "field", "failure_reason"}.issubset(result.columns)
    assert result["failure_reason"].eq("BALANCE_SOURCE_EMPTY").any()


def test_finance_gate_uses_only_current_nonfinancial_firms():
    panel = _universe().assign(
        pilot_stratum="seasoned_current_sse",
        financial_success=[True, False, False],
        rd_expense=[1.0, None, None],
    )
    result = financial_gate(panel)
    sse = result.loc[result["pilot_stratum"].eq("SSE_current_nonfinancial_combined")].iloc[0]
    assert sse["firms"] == 1
    assert sse["core_complete_rate"] == 1.0
