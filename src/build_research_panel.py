from __future__ import annotations

from pathlib import Path

import pandas as pd

PANEL_KEY = ["stock_code", "year"]
PATENT_COLUMNS = [
    "invention_patents",
    "utility_patents",
    "patent_citations",
]


def _require_columns(frame: pd.DataFrame, columns: list[str], name: str) -> None:
    missing = set(columns) - set(frame.columns)
    if missing:
        raise ValueError(f"{name} missing columns: {sorted(missing)}")


def _validate_unique(frame: pd.DataFrame, key: list[str], name: str) -> None:
    if frame[key].isna().any().any():
        raise ValueError(f"{name} contains missing key values: {key}")
    if frame.duplicated(key).any():
        raise ValueError(f"{name} key is not unique: {key}")


def build_research_panel(
    financial: pd.DataFrame,
    profile: pd.DataFrame,
    patents: pd.DataFrame,
) -> pd.DataFrame:
    """Build the financial-skeleton research panel without filling patent gaps."""
    _require_columns(financial, PANEL_KEY, "financial")
    _require_columns(profile, ["stock_code"], "Profile")
    _require_columns(patents, [*PANEL_KEY, *PATENT_COLUMNS], "Patent")
    _validate_unique(financial, PANEL_KEY, "financial")
    _validate_unique(profile, ["stock_code"], "Profile")
    _validate_unique(patents, PANEL_KEY, "Patent")

    profile_input = profile.copy()
    if "company_name" in profile_input.columns and "company_name" in financial.columns:
        profile_input = profile_input.rename(
            columns={"company_name": "profile_company_name"}
        )

    panel = financial.merge(
        profile_input,
        on="stock_code",
        how="left",
        validate="many_to_one",
        indicator="profile_merge",
    )
    if not panel["profile_merge"].eq("both").all():
        unmatched = panel.loc[panel["profile_merge"] != "both", "stock_code"].tolist()
        raise ValueError(f"Profile match failed for financial firms: {unmatched}")
    panel = panel.drop(columns="profile_merge")

    panel = panel.merge(
        patents[PANEL_KEY + PATENT_COLUMNS],
        on=PANEL_KEY,
        how="left",
        validate="one_to_one",
        indicator="patent_merge",
    )
    panel["patent_record_present"] = panel["patent_merge"].eq("both").astype("Int64")
    panel = panel.drop(columns="patent_merge")
    return panel.sort_values(PANEL_KEY).reset_index(drop=True)


def load_processed_panel(processed_dir) -> pd.DataFrame:
    processed_dir = Path(processed_dir)
    financial = pd.read_parquet(processed_dir / "firm_financials_clean.parquet")
    profile = pd.read_parquet(processed_dir / "firm_profile_clean.parquet")
    patents = pd.read_parquet(processed_dir / "patents_clean.parquet")
    return build_research_panel(financial, profile, patents)
