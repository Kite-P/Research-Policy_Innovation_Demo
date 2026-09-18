import pandas as pd
import pytest

from src.build_research_panel import build_research_panel


def frames():
    financial = pd.DataFrame(
        [["000001", 2020, 100.0], ["000001", 2021, 110.0]],
        columns=["stock_code", "year", "total_assets"],
    )
    profile = pd.DataFrame(
        [["000001", "甲公司"]],
        columns=["stock_code", "company_name"],
    )
    patents = pd.DataFrame(
        [["000001", 2020, 2, 3, 4]],
        columns=[
            "stock_code",
            "year",
            "invention_patents",
            "utility_patents",
            "patent_citations",
        ],
    )
    return financial, profile, patents


def test_panel_keeps_unobserved_patent_year_missing_and_marks_provenance():
    financial, profile, patents = frames()

    result = build_research_panel(financial, profile, patents)

    assert result.shape[0] == 2
    assert result["patent_record_present"].tolist() == [1, 0]
    missing = result.loc[result["year"] == 2021, "invention_patents"]
    assert missing.isna().all()


def test_panel_rejects_duplicate_financial_keys():
    financial, profile, patents = frames()
    financial = pd.concat([financial, financial.iloc[[0]]], ignore_index=True)

    with pytest.raises(ValueError, match="financial.*stock_code.*year"):
        build_research_panel(financial, profile, patents)


def test_panel_rejects_missing_profile_match():
    financial, profile, patents = frames()
    profile = profile.iloc[0:0]

    with pytest.raises(ValueError, match="Profile.*match"):
        build_research_panel(financial, profile, patents)
