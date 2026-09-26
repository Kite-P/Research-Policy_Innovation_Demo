from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]


def test_policy_region_scope_covers_mainland_scope_and_first_stage_panel():
    panel = pd.read_parquet(ROOT / "data/processed/research_panel_variables.parquet")
    scope = pd.read_csv(ROOT / "metadata/policy_region_scope.csv")

    assert scope["province"].is_unique
    assert scope["province_key"].is_unique
    scope_provinces = set(scope["province"])
    assert len(scope_provinces) == 31
    assert "香港特别行政区" not in scope_provinces
    assert set(panel["province"].dropna().unique()) <= scope_provinces
    assert (scope["panel_firm_count"] >= 0).all()
    assert (scope["panel_firm_year_count"] >= 0).all()
    assert scope["start_year"].eq(2020).all()
    assert scope["end_year"].eq(2025).all()


def test_policy_keyword_dictionary_has_core_and_context_terms():
    keywords = pd.read_csv(ROOT / "metadata/policy_industry_keywords.csv")

    assert keywords[["term", "category", "tier"]].notna().all().all()
    assert keywords["term"].is_unique
    assert set(keywords["tier"]) == {"core", "context"}
    assert (keywords["tier"] == "core").any()
    assert (keywords["tier"] == "context").any()
    assert keywords.loc[keywords["tier"] == "context", "category"].isin(
        ["enterprise_support", "talent"]
    ).all()
