import pandas as pd

from src.chapter3_measurement import missing_patent_diagnostic


def test_missing_patent_diagnostic_does_not_fill_missing_outcomes():
    panel = pd.DataFrame(
        {
            "province": ["甲", "甲", "乙", "乙"],
            "year": [2020, 2021, 2020, 2021],
            "patent_record_present": [1, 0, 1, 0],
            "policy_continuity_tfidf": [0.2, 0.3, 0.4, 0.5],
            "patent_total_ln": [1.0, None, 2.0, None],
        }
    )
    result = missing_patent_diagnostic(panel)
    assert result["missing_firm_years"] == 2
    assert result["outcome_missing_when_absent"] == 2
    assert panel["patent_total_ln"].isna().sum() == 2
