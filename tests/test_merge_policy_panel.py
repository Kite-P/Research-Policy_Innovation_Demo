import pandas as pd
import pytest

from src.merge_policy_panel import merge_policy_panel


def enterprise_frame():
    return pd.DataFrame(
        {
            "stock_code": ["000001", "000001", "000002"],
            "year": [2020, 2021, 2020],
            "province": ["甲省", "甲省", "缺省"],
            "outcome": [1, 2, 3],
        }
    )


def policy_frame():
    return pd.DataFrame(
        {
            "province": ["甲省"],
            "year": [2020],
            "policy_continuity_tfidf": [0.4],
            "policy_continuity_full_tfidf": [0.5],
            "policy_continuity_theme": [0.9],
            "policy_full_text_chars": [100],
            "policy_industry_text_chars": [50],
            "policy_industry_text_share": [0.5],
            "policy_keyword_hits": [10],
        }
    )


def test_many_to_one_merge_preserves_rows_and_provenance():
    merged = merge_policy_panel(enterprise_frame(), policy_frame())
    assert len(merged) == 3
    assert merged["stock_code"].tolist() == ["000001", "000001", "000002"]
    assert merged["policy_metric_present"].tolist() == [1, 0, 0]
    assert pd.isna(merged.loc[2, "policy_continuity_tfidf"])


def test_duplicate_policy_key_raises():
    policy = pd.concat([policy_frame(), policy_frame()], ignore_index=True)
    with pytest.raises(ValueError, match="policy province-year key is not unique"):
        merge_policy_panel(enterprise_frame(), policy)


def test_duplicate_enterprise_key_raises():
    enterprise = pd.concat([enterprise_frame(), enterprise_frame().iloc[[0]]], ignore_index=True)
    with pytest.raises(ValueError, match="enterprise stock_code-year key is not unique"):
        merge_policy_panel(enterprise, policy_frame())
