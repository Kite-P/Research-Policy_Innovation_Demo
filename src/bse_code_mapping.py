from __future__ import annotations

from pathlib import Path

import pandas as pd

BSE_MAPPING_SOURCE = "https://www.bse.cn/service/code_mapping.html"


def _code(value: object) -> str:
    text = str(value).strip()
    if text.endswith(".0"):
        text = text[:-2]
    return text.zfill(6) if text.isdigit() else ""


def normalize_bse_mapping(frame: pd.DataFrame) -> pd.DataFrame:
    old_col = next((c for c in ("旧代码", "old_stock_code") if c in frame), None)
    new_col = next((c for c in ("新代码", "new_stock_code") if c in frame), None)
    if old_col is None or new_col is None:
        raise ValueError("BSE mapping must contain old and new stock code columns")
    result = pd.DataFrame(
        {
            "old_stock_code": frame[old_col].map(_code),
            "new_stock_code": frame[new_col].map(_code),
        }
    )
    result = result.loc[
        result["old_stock_code"].ne("") & result["new_stock_code"].ne("")
    ].drop_duplicates()
    if result["old_stock_code"].duplicated().any() or result["new_stock_code"].duplicated().any():
        raise ValueError("BSE mapping contains duplicate code assignments")
    return result.reset_index(drop=True)


def load_bse_mapping(path: Path) -> pd.DataFrame:
    path = Path(path)
    if path.suffix.lower() in {".xlsx", ".xls"}:
        raw = pd.read_excel(path)
    elif path.suffix.lower() == ".csv":
        raw = pd.read_csv(path)
    elif path.suffix.lower() in {".html", ".htm"}:
        raw = pd.read_html(path)[0]
    else:
        raise ValueError(f"unsupported BSE mapping format: {path.suffix}")
    return normalize_bse_mapping(raw)


def resolve_bse_codes(current_code: str, mapping: pd.DataFrame) -> list[str]:
    current = _code(current_code)
    rows = mapping.loc[
        mapping["new_stock_code"].eq(current) | mapping["old_stock_code"].eq(current)
    ]
    if rows.empty:
        return [current]
    row = rows.iloc[0]
    return [row["old_stock_code"], row["new_stock_code"]]
