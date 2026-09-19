from pathlib import Path

import pandas as pd

from src.cnipa_patent_parser import (
    classify_cn_patent,
    normalize_cnipa_columns,
    read_cnipa_export,
)


def test_normalize_cnipa_columns_maps_required_export_fields():
    frame = pd.DataFrame(
        {
            "申请号": ["CN123"],
            "申请日": ["2024-01-02"],
            "公开（公告）号": ["CN111A"],
            "公开（公告）日": ["2024-07-02"],
            "申请人（专利权人）": ["甲有限公司"],
            "发明名称": ["测试发明"],
            "专利类型/文献类型": ["发明"],
            "IPC": ["A01B"],
        }
    )
    result = normalize_cnipa_columns(frame)
    assert list(result.columns) == [
        "application_number",
        "application_date",
        "publication_number",
        "publication_date",
        "applicant_raw",
        "patent_title",
        "patent_type_raw",
        "ipc_raw",
    ]
    assert result.loc[0, "publication_number"] == "CN111A"


def test_read_cnipa_export_supports_xlsx(tmp_path: Path):
    path = tmp_path / "export.xlsx"
    pd.DataFrame({"申请号": ["CN123"], "申请日": ["2024-01-02"]}).to_excel(
        path, index=False
    )
    result = read_cnipa_export(path)
    assert result.loc[0, "application_number"] == "CN123"


def test_classify_cn_patent_prefers_explicit_type_and_preserves_unknown():
    assert classify_cn_patent("CN123A", "实用新型") == "utility_model"
    assert classify_cn_patent("CN123U", None) == "unknown"
    assert classify_cn_patent("CN123", "") == "unknown"
