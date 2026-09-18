import pandas as pd

from src.chapter3_robustness import build_lagged_policy, run_robustness


def test_lagged_policy_is_missing_for_first_year():
    panel = pd.DataFrame(
        {
            "stock_code": ["a", "a", "b", "b"],
            "province": ["甲", "甲", "乙", "乙"],
            "year": [2020, 2021, 2020, 2021],
            "policy_continuity_tfidf": [0.2, 0.3, 0.4, 0.5],
        }
    )
    lagged = build_lagged_policy(panel, "policy_continuity_tfidf")
    assert lagged.loc[lagged.year == 2020, "policy_lag"].isna().all()
    assert lagged.loc[lagged.year == 2021, "policy_lag"].notna().all()


def test_robustness_reports_fixed_metric_families():
    panel = pd.DataFrame(
        {
            "stock_code": ["a", "a", "b", "b", "c", "c"],
            "province": ["甲", "甲", "乙", "乙", "丙", "丙"],
            "year": [2020, 2021, 2020, 2021, 2020, 2021],
            "patent_total_ln": [1, 2, 1.5, 2.5, 2, 3],
            "invention_ln": [0.5, 1, 0.7, 1.2, 1, 1.5],
            "citation_ln": [0.2, 0.4, 0.3, 0.5, 0.4, 0.7],
            "policy_continuity_tfidf": [0.2, 0.3, 0.4, 0.5, 0.6, 0.7],
            "policy_continuity_tfidf_expanding": [0.2, 0.3, 0.4, 0.5, 0.6, 0.7],
            "policy_continuity_full_tfidf": [0.2, 0.3, 0.4, 0.5, 0.6, 0.7],
            "policy_continuity_theme": [0.2, 0.3, 0.4, 0.5, 0.6, 0.7],
            "size_ln": [1, 1.1, 1.2, 1.3, 1.4, 1.5],
            "leverage": [0.2] * 6,
            "roa": [0.1] * 6,
            "cash_ratio": [0.3] * 6,
            "employee_ln": [2, 2.1, 2.2, 2.3, 2.4, 2.5],
        }
    )
    result = run_robustness(panel, reps=10)
    assert set(result.loc[result["model"] != "lagged_primary", "model"]) == {
        "expanding",
        "full_report",
        "theme",
    }
