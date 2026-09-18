import pandas as pd

from src.patent_cleaning import audit_patents, clean_patents, normalize_stock_code


def test_normalize_stock_code_strips_and_zero_fills_numeric_codes():
    values = pd.Series([" 000004 ", "7", "000010"])

    result = normalize_stock_code(values)

    assert result.tolist() == ["000004", "000007", "000010"]


def test_clean_patents_removes_exact_duplicates_and_marks_unrecoverable_outliers_missing():
    raw = pd.DataFrame(
        [
            ["1", 2020, "2", "3", "4"],
            ["000001", 2020, "2", "3", "4"],
            ["000002", 2020, "5", "6", "99999"],
            ["000003", 2020, "4", "5", "5"],
        ],
        columns=[
            "stock_code",
            "year",
            "invention_patents",
            "utility_patents",
            "patent_citations",
        ],
    )

    cleaned = clean_patents(raw)

    assert cleaned.shape == (3, 5)
    assert cleaned["stock_code"].tolist() == ["000001", "000002", "000003"]
    assert str(cleaned["year"].dtype) == "Int64"
    assert cleaned.loc[cleaned["stock_code"] == "000002", "patent_citations"].isna().all()
    assert not cleaned.duplicated(["stock_code", "year"]).any()


def test_audit_patents_compares_years_across_raw_and_processed_dtypes():
    raw = pd.DataFrame(
        [["1", "2020", "2", "3", "4"]],
        columns=[
            "stock_code",
            "year",
            "invention_patents",
            "utility_patents",
            "patent_citations",
        ],
    )
    financial = pd.DataFrame([["000001", 2020]], columns=["stock_code", "year"])

    result = audit_patents(raw, financial)

    assert result["observed_financial_firm_year"] == 1
    assert result["unobserved_financial_firm_year"] == 0
