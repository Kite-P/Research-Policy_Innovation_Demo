"""Construct province-year policy continuity metrics from cleaned reports."""

from __future__ import annotations

import csv
import re
import unicodedata
from argparse import ArgumentParser
from collections import Counter
from pathlib import Path

import numpy as np
import pandas as pd

PROVINCE_KEYS = {
    "北京市": "beijing",
    "天津市": "tianjin",
    "河北省": "hebei",
    "山西省": "shanxi",
    "内蒙古自治区": "inner_mongolia",
    "辽宁省": "liaoning",
    "吉林省": "jilin",
    "黑龙江省": "heilongjiang",
    "上海市": "shanghai",
    "江苏省": "jiangsu",
    "浙江省": "zhejiang",
    "安徽省": "anhui",
    "福建省": "fujian",
    "江西省": "jiangxi",
    "山东省": "shandong",
    "河南省": "henan",
    "湖北省": "hubei",
    "湖南省": "hunan",
    "广东省": "guangdong",
    "广西壮族自治区": "guangxi",
    "海南省": "hainan",
    "重庆市": "chongqing",
    "四川省": "sichuan",
    "贵州省": "guizhou",
    "云南省": "yunnan",
    "西藏自治区": "tibet",
    "陕西省": "shaanxi",
    "甘肃省": "gansu",
    "青海省": "qinghai",
    "宁夏回族自治区": "ningxia",
    "新疆维吾尔自治区": "xinjiang",
}


def normalize_vectorization_text(text: str) -> str:
    text = unicodedata.normalize("NFKC", str(text)).lower()
    text = re.sub(r"[^\u4e00-\u9fffA-Za-z0-9]", "", text)
    return text


def _ngrams(text: str, ngram_range: tuple[int, int]) -> list[str]:
    normalized = normalize_vectorization_text(text)
    return [
        normalized[start : start + n]
        for n in range(ngram_range[0], ngram_range[1] + 1)
        for start in range(len(normalized) - n + 1)
    ]


def tfidf_matrix(
    texts: list[str],
    ngram_range: tuple[int, int] = (2, 4),
    min_df: int = 2,
) -> tuple[np.ndarray, list[str]]:
    document_ngrams = [_ngrams(text, ngram_range) for text in texts]
    document_frequency = Counter(
        term for terms in document_ngrams for term in set(terms)
    )
    vocabulary = sorted(term for term, df in document_frequency.items() if df >= min_df)
    index = {term: position for position, term in enumerate(vocabulary)}
    matrix = np.zeros((len(texts), len(vocabulary)), dtype=float)
    for row, terms in enumerate(document_ngrams):
        counts = Counter(terms)
        for term, count in counts.items():
            if term in index:
                matrix[row, index[term]] = 1.0 + np.log(count)
    if vocabulary:
        n_documents = len(texts)
        dfs = np.array([document_frequency[term] for term in vocabulary], dtype=float)
        matrix *= np.log((1.0 + n_documents) / (1.0 + dfs)) + 1.0
        norms = np.linalg.norm(matrix, axis=1, keepdims=True)
        matrix = np.divide(matrix, norms, out=np.zeros_like(matrix), where=norms != 0)
    return matrix, vocabulary


def cosine_similarity(left: np.ndarray, right: np.ndarray) -> float:
    left_norm = np.linalg.norm(left)
    right_norm = np.linalg.norm(right)
    if left_norm == 0 or right_norm == 0:
        return float("nan")
    value = float(np.dot(left, right) / (left_norm * right_norm))
    return float(np.clip(value, 0.0, 1.0))


def _load_keyword_rows(path: str | Path) -> pd.DataFrame:
    with Path(path).open("r", encoding="utf-8-sig", newline="") as handle:
        return pd.DataFrame(list(csv.DictReader(handle)))


def _theme_vectors(texts: list[str], keywords: pd.DataFrame) -> np.ndarray:
    categories = sorted(keywords["category"].dropna().unique())
    vectors = np.zeros((len(texts), len(categories)), dtype=float)
    for row, text in enumerate(texts):
        for column, category in enumerate(categories):
            terms = keywords.loc[keywords["category"] == category, "term"]
            vectors[row, column] = sum(text.count(term) for term in terms)
        total = vectors[row].sum()
        if total:
            vectors[row] /= total
    return vectors


def _province_key(province: str) -> str:
    return PROVINCE_KEYS.get(province, province)


def _expanding_continuity(ordered: pd.DataFrame) -> dict[int, float]:
    values: dict[int, float] = {}
    for year in sorted(ordered["report_year"].unique()):
        eligible = ordered[ordered["report_year"] <= year].copy()
        matrix, _ = tfidf_matrix(eligible["industry_text_clean"].tolist())
        for position, row in eligible.iterrows():
            if int(row["report_year"]) != int(year):
                continue
            previous = eligible.index[
                eligible["province"].eq(row["province"])
                & eligible["report_year"].eq(int(row["report_year"]) - 1)
            ]
            if len(previous) == 1:
                current_pos = eligible.index.get_loc(position)
                previous_pos = eligible.index.get_loc(int(previous[0]))
                values[int(position)] = cosine_similarity(matrix[current_pos], matrix[previous_pos])
    return values


def build_policy_metrics(
    clean: pd.DataFrame,
    keywords: pd.DataFrame,
    source_manifest: pd.DataFrame | None = None,
) -> pd.DataFrame:
    required = {
        "province",
        "report_year",
        "industry_text_clean",
        "full_text_clean",
        "full_text_chars",
        "industry_text_chars",
        "industry_text_share",
        "keyword_hits_total",
    }
    missing = required - set(clean.columns)
    if missing:
        raise ValueError(f"missing clean corpus columns: {sorted(missing)}")
    ordered = clean.sort_values(["province", "report_year"]).reset_index(drop=True)
    if source_manifest is not None:
        source_lookup = source_manifest.set_index("policy_id")
    else:
        source_lookup = None
    industry_matrix, _ = tfidf_matrix(ordered["industry_text_clean"].tolist())
    full_matrix, _ = tfidf_matrix(ordered["full_text_clean"].tolist())
    theme_matrix = _theme_vectors(ordered["industry_text_clean"].tolist(), keywords)
    expanding_values = _expanding_continuity(ordered)
    records: list[dict[str, object]] = []
    for position, row in ordered.iterrows():
        previous_position = None
        same_province = ordered["province"].eq(row["province"])
        previous_year = int(row["report_year"]) - 1
        matches = ordered.index[same_province & ordered["report_year"].eq(previous_year)]
        if len(matches) == 1:
            previous_position = int(matches[0])
        available = previous_position is not None
        first_year = ordered.loc[same_province, "report_year"].min()
        flags = [] if available else [
            "first_year_missing" if row["report_year"] == first_year else "missing_previous_year"
        ]
        industry_metric = (
            cosine_similarity(industry_matrix[position], industry_matrix[previous_position])
            if available
            else float("nan")
        )
        full_metric = (
            cosine_similarity(full_matrix[position], full_matrix[previous_position])
            if available
            else float("nan")
        )
        theme_metric = (
            cosine_similarity(theme_matrix[position], theme_matrix[previous_position])
            if available
            else float("nan")
        )
        if available and any(
            pd.isna(value) for value in (industry_metric, full_metric, theme_metric)
        ):
            flags.append("empty_vector")
        if available:
            current_industry_log = np.log1p(float(row["industry_text_chars"]))
            previous_row = ordered.loc[previous_position]
            previous_industry_log = np.log1p(float(previous_row["industry_text_chars"]))
            current_full_log = np.log1p(float(row["full_text_chars"]))
            previous_full_log = np.log1p(float(previous_row["full_text_chars"]))
            pair_controls = {
                "pair_mean_log_industry_chars": (current_industry_log + previous_industry_log) / 2,
                "abs_log_industry_length_change": abs(current_industry_log - previous_industry_log),
                "pair_mean_log_full_chars": (current_full_log + previous_full_log) / 2,
                "abs_log_full_length_change": abs(current_full_log - previous_full_log),
            }
        else:
            pair_controls = {
                "pair_mean_log_industry_chars": np.nan,
                "abs_log_industry_length_change": np.nan,
                "pair_mean_log_full_chars": np.nan,
                "abs_log_full_length_change": np.nan,
            }
        if source_lookup is not None and "policy_id" in ordered.columns:
            current_source = source_lookup.loc[row["policy_id"]]
            previous_source = source_lookup.loc[previous_row["policy_id"]] if available else None
            source_current = int(current_source["source_tier"])
            source_previous = (
                int(previous_source["source_tier"]) if previous_source is not None else np.nan
            )
            source_max = max(source_current, source_previous) if available else np.nan
            source_changed = int(source_current != source_previous) if available else np.nan
            both_direct = int(source_current <= 2 and source_previous <= 2) if available else np.nan
        else:
            source_current = source_previous = source_max = np.nan
            source_changed = both_direct = np.nan
        records.append(
            {
                "province": row["province"],
                "province_key": _province_key(str(row["province"])),
                "year": int(row["report_year"]),
                "policy_continuity_tfidf": industry_metric,
                "policy_continuity_tfidf_expanding": expanding_values.get(position, float("nan")),
                "policy_continuity_full_tfidf": full_metric,
                "policy_continuity_theme": theme_metric,
                "policy_full_text_chars": int(row["full_text_chars"]),
                "policy_industry_text_chars": int(row["industry_text_chars"]),
                "policy_industry_text_share": float(row["industry_text_share"]),
                "policy_keyword_hits": int(row["keyword_hits_total"]),
                "previous_year_available": available,
                "metric_quality_flag": ";".join(flags) if flags else "ok",
                "source_tier_current": source_current,
                "source_tier_previous": source_previous,
                "source_tier_max": source_max,
                "source_tier_changed": source_changed,
                "both_direct_official": both_direct,
                **pair_controls,
            }
        )
    return pd.DataFrame(records).sort_values(["province", "year"]).reset_index(drop=True)


def write_policy_metrics(
    clean_path: str | Path,
    keyword_path: str | Path,
    parquet_path: str | Path,
    dta_path: str | Path,
    manifest_path: str | Path | None = "metadata/policy_source_manifest.csv",
) -> pd.DataFrame:
    clean = pd.read_parquet(clean_path)
    keywords = _load_keyword_rows(keyword_path)
    manifest = pd.read_csv(manifest_path) if manifest_path else None
    metrics = build_policy_metrics(clean, keywords, manifest)
    Path(parquet_path).parent.mkdir(parents=True, exist_ok=True)
    Path(dta_path).parent.mkdir(parents=True, exist_ok=True)
    metrics.to_parquet(parquet_path, index=False)
    stata_metrics = metrics.rename(
        columns={"policy_continuity_tfidf_expanding": "policy_cont_tfidf_exp"}
    )
    stata_metrics.to_stata(dta_path, write_index=False, version=118)
    return metrics


if __name__ == "__main__":
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("--clean", default="data/processed/policy_reports_clean.parquet")
    parser.add_argument("--keywords", default="metadata/policy_industry_keywords.csv")
    parser.add_argument("--parquet", default="data/processed/province_year_policy_metrics.parquet")
    parser.add_argument("--dta", default="data/processed/province_year_policy_metrics.dta")
    parser.add_argument("--manifest", default="metadata/policy_source_manifest.csv")
    args = parser.parse_args()
    write_policy_metrics(args.clean, args.keywords, args.parquet, args.dta, args.manifest)
