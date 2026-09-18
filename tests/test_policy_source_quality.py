import pandas as pd

from src.policy_source_quality import classify_source, enrich_manifest


def test_source_tier_is_explicit_and_reasoned():
    tier, label, reason = classify_source("hubei_2022", "http://hb.china.com.cn/report")
    assert tier == 4
    assert label == "other_complete_reprint"
    assert len(reason) > 20


def test_enrich_manifest_separates_historical_fetch_issue():
    manifest = pd.DataFrame(
        {
            "policy_id": ["beijing_2019"],
            "source_url": ["https://www.beijing.gov.cn/report"],
            "source_domain": ["beijing.gov.cn"],
            "retrieval_status": ["success"],
            "notes": ["fetch_error=PermissionError"],
        }
    )
    result = enrich_manifest(manifest)
    assert result.loc[0, "source_tier"] == 1
    assert result.loc[0, "source_tier_verified"] == 1
    assert result.loc[0, "retrieval_history_note"] == "fetch_error=PermissionError"
    assert "fetch_error" not in str(result.loc[0, "notes"])
