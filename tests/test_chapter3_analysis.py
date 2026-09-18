import pandas as pd

from src.chapter3_analysis import run_baseline_models


def test_baseline_models_keep_three_frozen_outcomes_and_cluster_counts():
    panel = pd.DataFrame(
        {
            "stock_code": ["a", "a", "b", "b", "c", "c"],
            "province": ["甲", "甲", "乙", "乙", "丙", "丙"],
            "year": [2020, 2021, 2020, 2021, 2020, 2021],
            "patent_total_ln": [1, 2, 1.5, 2.5, 2, 3],
            "invention_ln": [0.5, 1, 0.7, 1.2, 1, 1.5],
            "citation_ln": [0.2, 0.4, 0.3, 0.5, 0.4, 0.7],
            "policy_continuity_tfidf": [0.2, 0.3, 0.4, 0.5, 0.6, 0.7],
            "size_ln": [1, 1.1, 1.2, 1.3, 1.4, 1.5],
            "leverage": [0.2] * 6,
            "roa": [0.1] * 6,
            "cash_ratio": [0.3] * 6,
            "employee_ln": [2, 2.1, 2.2, 2.3, 2.4, 2.5],
        }
    )
    result = run_baseline_models(panel, reps=20, seed=20260918)
    assert result["baseline"].outcome.tolist() == [
        "patent_total_ln",
        "patent_total_ln",
        "invention_ln",
        "citation_ln",
    ]
    assert result["baseline"]["province_clusters"].eq(3).all()
    assert result["wcb"]["reps"].eq(20).all()
