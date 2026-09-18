import numpy as np
import pandas as pd

from src.policy_continuity_validation import (
    distribution_summary,
    rank_correlation,
    validate_coverage,
)


def test_coverage_identifies_first_year_and_available_years():
    metrics = pd.DataFrame(
        {
            "province": ["甲省", "甲省", "乙省", "乙省"],
            "year": [2019, 2020, 2019, 2020],
            "policy_continuity_tfidf": [np.nan, 0.5, np.nan, 0.7],
        }
    )
    result = validate_coverage(metrics, provinces=["甲省", "乙省"], years=range(2019, 2021))
    assert result["expected_cells"] == 4
    assert result["available_primary_cells"] == 2
    assert result["missing_primary_cells"] == 0


def test_distribution_summary_and_rank_correlation():
    frame = pd.DataFrame({"x": [0.1, 0.2, np.nan, 0.8], "y": [0.2, 0.3, 0.4, 0.7]})
    summary = distribution_summary(frame, ["x"])
    assert summary.loc[0, "N"] == 3
    assert summary.loc[0, "min"] == 0.1
    assert rank_correlation(frame["x"], frame["y"]) > 0.9
