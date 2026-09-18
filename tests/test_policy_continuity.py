import numpy as np
import pandas as pd
import pytest

from src.policy_continuity import (
    build_policy_metrics,
    cosine_similarity,
    normalize_vectorization_text,
    tfidf_matrix,
)


def test_identical_and_disjoint_cosine_bounds():
    matrix, _ = tfidf_matrix(["创新制造", "创新制造", "完全不同"], ngram_range=(2, 4), min_df=1)
    assert cosine_similarity(matrix[0], matrix[1]) == pytest.approx(1.0)
    assert 0 <= cosine_similarity(matrix[0], matrix[2]) < 1


def test_vectorization_normalizes_ascii_whitespace_and_punctuation():
    assert normalize_vectorization_text("ＡＢ C 1\n创新！") == "abc1创新"


def test_tfidf_empty_vector_and_missing_previous():
    matrix, vocabulary = tfidf_matrix(["", "创新"], ngram_range=(2, 4), min_df=1)
    assert vocabulary
    assert np.allclose(matrix[0], 0)
    assert np.linalg.norm(matrix[1]) == pytest.approx(1.0)


def test_metrics_are_sorted_and_first_year_missing():
    clean = pd.DataFrame(
        {
            "province": ["甲省", "甲省", "乙省", "乙省"],
            "report_year": [2019, 2020, 2019, 2020],
            "industry_text_clean": ["创新制造", "创新制造升级", "数字经济", "绿色发展"],
            "full_text_clean": ["创新制造", "创新制造升级", "数字经济", "绿色发展"],
            "full_text_chars": [4, 6, 4, 4],
            "industry_text_chars": [4, 6, 4, 4],
            "industry_text_share": [1.0] * 4,
            "keyword_hits_total": [1, 2, 1, 1],
        }
    )
    keywords = pd.DataFrame(
        {
            "term": ["创新", "制造", "数字经济", "绿色发展"],
            "category": [
                "technology_innovation",
                "manufacturing_upgrade",
                "digital_economy",
                "green_transition",
            ],
            "tier": ["core"] * 4,
        }
    )
    metrics = build_policy_metrics(clean, keywords)
    assert metrics[["province", "year"]].duplicated().sum() == 0
    assert metrics.loc[metrics.year == 2019, "policy_continuity_tfidf"].isna().all()
    assert metrics.loc[metrics.year == 2020, "previous_year_available"].all()
    assert metrics["policy_continuity_tfidf"].dropna().between(0, 1).all()


def test_expanding_metric_is_insensitive_to_future_text_changes():
    rows = []
    for province in ["甲省", "乙省"]:
        for year in range(2019, 2026):
            text = f"创新制造共同基础 {year}"
            rows.append(
                {
                    "policy_id": f"{province}_{year}",
                    "province": province,
                    "report_year": year,
                    "industry_text_clean": text,
                    "full_text_clean": text,
                    "full_text_chars": len(text),
                    "industry_text_chars": len(text),
                    "industry_text_share": 1.0,
                    "keyword_hits_total": 2,
                }
            )
    clean = pd.DataFrame(rows)
    keywords = pd.DataFrame(
        {
            "term": ["创新", "制造"],
            "category": ["technology", "manufacturing"],
            "tier": ["core", "core"],
        }
    )
    original = build_policy_metrics(clean, keywords)
    changed = clean.copy()
    changed.loc[changed["report_year"] == 2025, "industry_text_clean"] = "完全不同未来文本"
    changed_metrics = build_policy_metrics(changed, keywords)
    left = original.loc[original.year <= 2024, "policy_continuity_tfidf_expanding"]
    right = changed_metrics.loc[changed_metrics.year <= 2024, "policy_continuity_tfidf_expanding"]
    assert np.allclose(left.fillna(-1), right.fillna(-1))
