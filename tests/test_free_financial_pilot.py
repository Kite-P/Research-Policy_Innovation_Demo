import pandas as pd

from src.free_financial_pilot import resolve_column, select_year_end_rows, to_em_symbol


def test_to_em_symbol():
    assert to_em_symbol("SSE", "600519") == "SH600519"
    assert to_em_symbol("SZSE", "000001") == "SZ000001"
    assert to_em_symbol("BSE", "430047") == "BJ430047"


def test_select_year_end_rows_excludes_interim_reports():
    frame = pd.DataFrame(
        {
            "REPORT_DATE": ["2022-12-31", "2022-09-30", "2023-12-31"],
            "REPORT_TYPE": ["年报", "三季报", "年报"],
        }
    )
    result = select_year_end_rows(frame)
    assert result["REPORT_DATE"].tolist() == ["2022-12-31", "2023-12-31"]


def test_resolve_column_rejects_ambiguous_matches():
    columns = ["TOTAL_ASSETS", "TOTAL_ASSETS_OTHER"]
    result = resolve_column(
        columns,
        exact_candidates=("NOT_PRESENT",),
        contains_candidates=("TOTAL", "ASSET"),
    )
    assert result is None
