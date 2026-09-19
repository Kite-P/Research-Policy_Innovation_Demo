from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path

import pandas as pd

CANONICAL_COLUMNS = [
    "application_number",
    "application_date",
    "publication_number",
    "publication_date",
    "applicant_raw",
    "patent_title",
    "patent_type_raw",
    "ipc_raw",
]

COLUMN_ALIASES = {
    "application_number": ("申请号", "申请编号"),
    "application_date": ("申请日", "申请日期"),
    "publication_number": ("公开（公告）号", "公开公告号", "公开号", "公告号"),
    "publication_date": ("公开（公告）日", "公开公告日", "公开日", "公告日"),
    "applicant_raw": ("申请人（专利权人）", "申请人", "专利权人"),
    "patent_title": ("发明名称", "专利名称", "名称"),
    "patent_type_raw": ("专利类型/文献类型", "专利类型", "文献类型"),
    "ipc_raw": ("IPC", "主分类号", "分类号"),
}


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _read_xml(path: Path) -> pd.DataFrame:
    root = ET.parse(path).getroot()
    records: list[dict[str, str]] = []
    for node in root.iter():
        children = list(node)
        if not children or not all(list(child) == [] for child in children):
            continue
        record = {
            _local_name(child.tag): (child.text or "").strip() for child in children
        }
        if record:
            records.append(record)
    return pd.DataFrame(records)


def _read_raw_export(path: Path) -> pd.DataFrame:
    suffix = path.suffix.lower()
    if suffix in {".xlsx", ".xls"}:
        return pd.read_excel(path)
    if suffix == ".xml":
        return _read_xml(path)
    raise ValueError(f"unsupported CNIPA export format: {path.suffix}")


def normalize_cnipa_columns(frame: pd.DataFrame) -> pd.DataFrame:
    result = pd.DataFrame(index=frame.index)
    for canonical in CANONICAL_COLUMNS:
        source = next(
            (name for name in COLUMN_ALIASES[canonical] if name in frame.columns), None
        )
        result[canonical] = frame[source] if source else pd.NA
    return result


def read_cnipa_export(path: Path) -> pd.DataFrame:
    return normalize_cnipa_columns(_read_raw_export(Path(path)))


def classify_cn_patent(publication_number: str, raw_type: str | None) -> str:
    text = "" if raw_type is None else str(raw_type).strip().lower()
    if "发明" in text and "实用" not in text:
        return "invention"
    if "实用新型" in text:
        return "utility_model"
    if "外观设计" in text or "外观" in text:
        return "design"
    return "unknown"
