import numpy as np
import pandas as pd

from src.build_research_variables import build_research_variables


def test_constructs_financial_and_innovation_variables_with_defined_missing_rules():
    panel = pd.DataFrame(
        [
            ["000001", 2020, 100.0, 40.0, 10.0, 20.0, 5.0, 2.0, 10, "2000-01-01", 2, 3, 4, 1],
            ["000002", 2020, 0.0, 2.0, 1.0, 3.0, 1.0, 1.0, 0, None, 0, 0, 0, 1],
            ["000003", 2020, -10.0, 2.0, 1.0, 3.0, 1.0, 1.0, -2, "2010-01-01", None, None, None, 0],
        ],
        columns=[
            "stock_code", "year", "total_assets", "total_liabilities", "revenue",
            "net_profit", "cash", "rd_expense", "employees", "listing_date", "invention_patents",
            "utility_patents", "patent_citations", "patent_record_present",
        ],
    )

    result = build_research_variables(panel)

    assert np.isclose(result.loc[0, "size_ln"], np.log(100))
    assert np.isclose(result.loc[0, "leverage"], 0.4)
    assert np.isclose(result.loc[0, "patent_total"], 5)
    assert np.isclose(result.loc[0, "patent_total_ln"], np.log(6))
    assert np.isclose(result.loc[0, "invention_share"], 0.4)
    assert np.isclose(result.loc[0, "citations_per_invention"], 2)
    assert result.loc[0, "firm_age"] == 21

    assert result.loc[1, "size_ln"] is pd.NA or pd.isna(result.loc[1, "size_ln"])
    assert pd.isna(result.loc[1, "employee_ln"])
    assert pd.isna(result.loc[1, "invention_share"])
    assert pd.isna(result.loc[2, "patent_total"])
    assert pd.isna(result.loc[2, "patent_total_ln"])
    assert pd.isna(result.loc[2, "invention_ln"])
    assert result.loc[2, "firm_age"] == 11


def test_variable_construction_never_emits_infinite_values():
    panel = pd.DataFrame(
        [["000001", 2020, np.nan, 1, 1, 1, 1, 1, 1, None, None, None, None, 0]],
        columns=[
            "stock_code", "year", "total_assets", "total_liabilities", "revenue",
            "net_profit", "cash", "rd_expense", "employees", "listing_date", "invention_patents",
            "utility_patents", "patent_citations", "patent_record_present",
        ],
    )

    result = build_research_variables(panel)
    numeric = result.select_dtypes(include="number")

    assert not np.isinf(numeric.to_numpy(dtype=float)).any()
    assert result.loc[0, "invention_ln"] is pd.NA or pd.isna(result.loc[0, "invention_ln"])
