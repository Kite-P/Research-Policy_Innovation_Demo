import pandas as pd

from src.free_employee_pilot import select_staff_year_end_rows, to_f10_symbol


def test_to_f10_symbol():
    assert to_f10_symbol("SSE", "600519") == "600519.SH"
    assert to_f10_symbol("SZSE", "000001") == "000001.SZ"
    assert to_f10_symbol("BSE", "430047") == "430047.BJ"


def test_select_staff_year_end_rows_only_keeps_annual_dates():
    frame = pd.DataFrame(
        {
            "REPORT_DATE": ["2022-12-31", "2023-06-30", "2024-12-31"],
            "STAFF_NUM": [10, 11, 12],
        }
    )
    result = select_staff_year_end_rows(frame)
    assert result["REPORT_DATE"].tolist() == ["2022-12-31", "2024-12-31"]
