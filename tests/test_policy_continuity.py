import numpy as np
import pandas as pd
import pytest

from src.policy_continuity import (
    PROVINCE_KEYS,
    build_policy_metrics,
    cosine_similarity,
    normalize_vectorization_text,
    tfidf_matrix,
)


def test_national_policy_mapping_has_all_31_mainland_provinces():
    expected = {
        "北京市": "beijing", "天津市": "tianjin", "河北省": "hebei",
        "山西省": "shanxi", "内蒙古自治区": "inner_mongolia", "辽宁省": "liaoning",
        "吉林省": "jilin", "黑龙江省": "heilongjiang", "上海市": "shanghai",
        "江苏省": "jiangsu", "浙江省": "zhejiang", "安徽省": "anhui",
        "福建省": "fujian", "江西省": "jiangxi", "山东省": "shandong",
        "河南省": "henan", "湖北省": "hubei", "湖南省": "hunan",
        "广东省": "guangdong", "广西壮族自治区": "guangxi", "海南省": "hainan",
        "重庆市": "chongqing", "四川省": "sichuan", "贵州省": "guizhou",
        "云南省": "yunnan", "西藏自治区": "tibet", "陕西省": "shaanxi",
        "甘肃省": "gansu", "青海省": "qinghai", "宁夏回族自治区": "ningxia",
        "新疆维吾尔自治区": "xinjiang",
    }
    assert PROVINCE_KEYS == expected
    assert "香港特别行政区" not in PROVINCE_KEYS


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


def test_national_metrics_have_217_cells_186_pairs_and_source_pair_fields():
    provinces = list(PROVINCE_KEYS.items())
    clean_rows = []
    source_rows = []
    for province_index, (province, province_key) in enumerate(provinces):
        for year in range(2019, 2026):
            policy_id = f"{province_key}_{year}"
            text = f"{province}产业创新制造业数字经济绿色发展共同基础{year}"
            clean_rows.append(
                {
                    "policy_id": policy_id,
                    "province": province,
                    "report_year": year,
                    "industry_text_clean": text,
                    "full_text_clean": text,
                    "full_text_chars": len(text) + 100,
                    "industry_text_chars": len(text),
                    "industry_text_share": len(text) / (len(text) + 100),
                    "keyword_hits_total": 4,
                }
            )
            source_rows.append(
                {"policy_id": policy_id, "source_tier": 1 + (province_index + year) % 4}
            )

    keywords = pd.DataFrame(
        {
            "term": ["产业创新", "制造业", "数字经济", "绿色发展"],
            "category": ["innovation", "manufacturing", "digital", "green"],
            "tier": ["core"] * 4,
        }
    )
    metrics = build_policy_metrics(
        pd.DataFrame(clean_rows), keywords, pd.DataFrame(source_rows)
    )

    assert len(metrics) == 217
    assert metrics[["province", "year"]].drop_duplicates().shape[0] == 217
    assert metrics["province"].nunique() == 31
    assert metrics.loc[metrics.year == 2019, "policy_continuity_tfidf"].isna().sum() == 31
    primary = metrics.loc[metrics.year.between(2020, 2025), "policy_continuity_tfidf"]
    assert primary.notna().sum() == 186
    assert primary.between(0, 1).all()
    assert np.isfinite(primary).all()
    assert metrics.loc[metrics.year == 2019, "source_tier_previous"].isna().all()
    assert metrics.loc[metrics.year.between(2020, 2025), "source_tier_max"].between(1, 4).all()
    assert metrics.loc[metrics.year.between(2020, 2025), "both_direct_official"].isin([0, 1]).all()
