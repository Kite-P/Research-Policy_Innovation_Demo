from __future__ import annotations

import pandas as pd

PATENT_VALUE_COLUMNS = [
    "invention_patents",
    "utility_patents",
    "patent_citations",
]
PATENT_COLUMNS = ["stock_code", "year", *PATENT_VALUE_COLUMNS]


def normalize_stock_code(values: pd.Series) -> pd.Series:
    """Return six-digit codes while preserving invalid values as missing."""
    text = values.astype("string").str.strip()
    valid = text.str.fullmatch(r"\d+")
    return text.where(valid).str.zfill(6)


def _integer_series(values: pd.Series) -> pd.Series:
    numeric = pd.to_numeric(values, errors="coerce")
    integral = numeric.isna() | (numeric % 1 == 0)
    if not integral.all():
        bad = values.loc[~integral].tolist()
        raise ValueError(f"Non-integer patent values: {bad}")
    return numeric.astype("Int64")


def _outlier_upper_bound(values: pd.Series) -> float | None:
    observed = values.dropna().astype(float)
    if len(observed) < 3:
        return None
    median = float(observed.median())
    mad = float((observed - median).abs().median())
    if mad > 0:
        return median + 10 * mad
    q1, q3 = observed.quantile([0.25, 0.75])
    iqr = float(q3 - q1)
    if iqr <= 0:
        return None
    return float(q3 + 3 * iqr)


def _mark_extreme_citations_missing(frame: pd.DataFrame) -> pd.DataFrame:
    result = frame.copy()
    bound = _outlier_upper_bound(result["patent_citations"])
    if bound is not None:
        extreme = result["patent_citations"] > bound
        result.loc[extreme, "patent_citations"] = pd.NA
    return result


def _deduplicate(frame: pd.DataFrame) -> pd.DataFrame:
    result = frame.drop_duplicates().copy()
    if not result.duplicated(["stock_code", "year"]).any():
        return result

    rows: list[pd.Series] = []
    for _, group in result.groupby(["stock_code", "year"], sort=False, dropna=False):
        if len(group) == 1:
            rows.append(group.iloc[0])
            continue
        # After extreme citations are set missing, the row with the fewest missing
        # values is the evidence-supported version of a conflicting duplicate.
        missing_counts = group.isna().sum(axis=1)
        rows.append(group.loc[missing_counts.idxmin()])
    result = pd.DataFrame(rows, columns=result.columns).reset_index(drop=True)
    result["stock_code"] = normalize_stock_code(result["stock_code"])
    result["year"] = pd.to_numeric(result["year"], errors="coerce").astype("Int64")
    for column in PATENT_VALUE_COLUMNS:
        result[column] = _integer_series(result[column])
    return result


def clean_patents(frame: pd.DataFrame) -> pd.DataFrame:
    """Clean patent observations without manufacturing unobserved firm-years."""
    missing = set(PATENT_COLUMNS) - set(frame.columns)
    if missing:
        raise ValueError(f"Missing patent columns: {sorted(missing)}")

    result = frame[PATENT_COLUMNS].copy()
    result["stock_code"] = normalize_stock_code(result["stock_code"])
    result["year"] = pd.to_numeric(result["year"], errors="coerce").astype("Int64")
    for column in PATENT_VALUE_COLUMNS:
        result[column] = _integer_series(result[column])

    if result["stock_code"].isna().any():
        raise ValueError("Patent stock_code contains invalid or missing values")
    if result["year"].isna().any() or not result["year"].between(2020, 2025).all():
        raise ValueError("Patent year must be an integer from 2020 through 2025")
    for column in PATENT_VALUE_COLUMNS:
        if (result[column].dropna() < 0).any():
            raise ValueError(f"Patent values cannot be negative: {column}")

    result = _mark_extreme_citations_missing(result)
    return _deduplicate(result)


def audit_patents(frame: pd.DataFrame, financial_panel: pd.DataFrame) -> dict:
    """Return reproducible audit summaries for the raw patent table."""
    raw = frame[PATENT_COLUMNS].copy()
    candidate = normalize_stock_code(raw["stock_code"])
    audit_key = pd.DataFrame(
        {
            "stock_code": candidate,
            "year": pd.to_numeric(raw["year"], errors="coerce").astype("Int64"),
        }
    )
    duplicate_mask = audit_key.duplicated(["stock_code", "year"], keep=False)
    duplicate_groups = audit_key.loc[duplicate_mask].drop_duplicates(
        ["stock_code", "year"]
    )
    unique_patent_keys = audit_key.drop_duplicates()
    financial_keys = financial_panel[["stock_code", "year"]].copy()
    financial_keys["stock_code"] = normalize_stock_code(financial_keys["stock_code"])
    financial_keys["year"] = pd.to_numeric(
        financial_keys["year"], errors="coerce"
    ).astype("Int64")
    financial_keys = financial_keys.drop_duplicates()
    observed = financial_keys.merge(
        unique_patent_keys,
        on=["stock_code", "year"],
        how="left",
        indicator=True,
    )
    summary = {
        "raw_rows": int(len(raw)),
        "raw_columns": int(raw.shape[1]),
        "raw_firms": int(candidate.nunique()),
        "year_min": int(pd.to_numeric(raw["year"]).min()),
        "year_max": int(pd.to_numeric(raw["year"]).max()),
        "unique_firm_year": int(len(unique_patent_keys)),
        "duplicate_member_rows": int(duplicate_mask.sum()),
        "duplicate_groups": int(len(duplicate_groups)),
        "financial_firm_year": int(len(financial_keys)),
        "observed_financial_firm_year": int((observed["_merge"] == "both").sum()),
        "unobserved_financial_firm_year": int((observed["_merge"] == "left_only").sum()),
        "patent_firms": int(candidate.nunique()),
        "patent_value_missing": {
            column: int(raw[column].astype("string").str.strip().eq("").sum())
            for column in PATENT_VALUE_COLUMNS
        },
    }
    return summary


def load_and_clean_patents(raw_path, output_path=None) -> pd.DataFrame:
    raw = pd.read_csv(raw_path, dtype=object, keep_default_na=False)
    cleaned = clean_patents(raw)
    if output_path is not None:
        cleaned.to_parquet(output_path, index=False)
    return cleaned


def stata_ready(frame: pd.DataFrame) -> pd.DataFrame:
    """Convert nullable pandas integers to Stata-compatible numeric columns."""
    result = frame.copy()
    for column in ["year", *PATENT_VALUE_COLUMNS]:
        result[column] = pd.to_numeric(result[column], errors="coerce").astype(float)
    return result
