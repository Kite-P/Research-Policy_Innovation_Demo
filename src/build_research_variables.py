from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

RATIO_DEFINITIONS = {
    "leverage": ("total_liabilities", "total_assets"),
    "roa": ("net_profit", "total_assets"),
    "rd_intensity": ("rd_expense", "revenue"),
    "cash_ratio": ("cash", "total_assets"),
}
PATENT_FIELDS = ["invention_patents", "utility_patents", "patent_citations"]
DERIVED_PATENT_FIELDS = [
    "patent_total",
    "patent_total_ln",
    "invention_ln",
    "citation_ln",
    "invention_share",
    "citations_per_invention",
]


def _require_columns(frame: pd.DataFrame) -> None:
    required = {
        "stock_code", "year", "total_assets", "total_liabilities", "revenue",
        "net_profit", "cash", "rd_expense", "employees", "listing_date",
        "patent_record_present", *PATENT_FIELDS,
    }
    missing = required - set(frame.columns)
    if missing:
        raise ValueError(f"Panel missing variable columns: {sorted(missing)}")


def _numeric(frame: pd.DataFrame, column: str) -> pd.Series:
    return pd.to_numeric(frame[column], errors="coerce").astype(float)


def _safe_ratio(numerator: pd.Series, denominator: pd.Series) -> pd.Series:
    result = pd.Series(np.nan, index=numerator.index, dtype="float64")
    valid = numerator.notna() & denominator.notna() & (denominator > 0)
    result.loc[valid] = numerator.loc[valid] / denominator.loc[valid]
    return result


def _safe_log(values: pd.Series) -> pd.Series:
    result = pd.Series(np.nan, index=values.index, dtype="float64")
    valid = values.notna() & (values > 0)
    result.loc[valid] = np.log(values.loc[valid])
    return result


def build_research_variables(panel: pd.DataFrame) -> pd.DataFrame:
    """Construct first-stage variables while preserving missing observations."""
    _require_columns(panel)
    result = panel.copy()

    assets = _numeric(result, "total_assets")
    revenue = _numeric(result, "revenue")
    employees = _numeric(result, "employees")
    result["size_ln"] = _safe_log(assets)
    result["leverage"] = _safe_ratio(_numeric(result, "total_liabilities"), assets)
    result["roa"] = _safe_ratio(_numeric(result, "net_profit"), assets)
    result["rd_intensity"] = _safe_ratio(_numeric(result, "rd_expense"), revenue)
    result["cash_ratio"] = _safe_ratio(_numeric(result, "cash"), assets)
    result["employee_ln"] = _safe_log(employees)

    listing_year = pd.to_datetime(result["listing_date"], errors="coerce").dt.year
    firm_age = pd.to_numeric(result["year"], errors="coerce") - listing_year + 1
    result["firm_age"] = firm_age.where(firm_age > 0).astype("Float64")

    for column in PATENT_FIELDS:
        result[column] = _numeric(result, column)
    observed = pd.to_numeric(result["patent_record_present"], errors="coerce").eq(1)
    result.loc[~observed, PATENT_FIELDS] = np.nan

    invention = result["invention_patents"]
    utility = result["utility_patents"]
    citations = result["patent_citations"]
    result["patent_total"] = invention + utility
    result.loc[invention.isna() | utility.isna() | ~observed, "patent_total"] = np.nan
    result["patent_total_ln"] = _safe_log(result["patent_total"] + 1)
    result["invention_ln"] = _safe_log(invention + 1)
    result["citation_ln"] = _safe_log(citations + 1)
    result["invention_share"] = _safe_ratio(invention, result["patent_total"])
    result["citations_per_invention"] = _safe_ratio(citations, invention)

    numeric = result.select_dtypes(include=["number"])
    if np.isinf(numeric.to_numpy(dtype=float)).any():
        raise ValueError("Variable construction produced infinite values")
    return result


def variable_summary(frame: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for column in [
        "size_ln", "leverage", "roa", "rd_intensity", "cash_ratio", "employee_ln",
        "firm_age", *PATENT_FIELDS, *DERIVED_PATENT_FIELDS,
    ]:
        values = pd.to_numeric(frame[column], errors="coerce")
        rows.append(
            {
                "variable": column,
                "N": int(values.notna().sum()),
                "missing": int(values.isna().sum()),
                "min": values.min(),
                "median": values.median(),
                "max": values.max(),
            }
        )
    return pd.DataFrame(rows)


def load_and_build_variables(processed_dir) -> pd.DataFrame:
    processed_dir = Path(processed_dir)
    panel = pd.read_parquet(processed_dir / "research_panel_base.parquet")
    return build_research_variables(panel)
