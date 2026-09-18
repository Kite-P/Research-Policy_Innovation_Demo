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
    "上海市": "shanghai",
    "广东省": "guangdong",
    "江苏省": "jiangsu",
    "浙江省": "zhejiang",
    "四川省": "sichuan",
    "湖北省": "hubei",
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


def build_policy_metrics(clean: pd.DataFrame, keywords: pd.DataFrame) -> pd.DataFrame:
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
    industry_matrix, _ = tfidf_matrix(ordered["industry_text_clean"].tolist())
    full_matrix, _ = tfidf_matrix(ordered["full_text_clean"].tolist())
    theme_matrix = _theme_vectors(ordered["industry_text_clean"].tolist(), keywords)
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
        records.append(
            {
                "province": row["province"],
                "province_key": _province_key(str(row["province"])),
                "year": int(row["report_year"]),
                "policy_continuity_tfidf": industry_metric,
                "policy_continuity_full_tfidf": full_metric,
                "policy_continuity_theme": theme_metric,
                "policy_full_text_chars": int(row["full_text_chars"]),
                "policy_industry_text_chars": int(row["industry_text_chars"]),
                "policy_industry_text_share": float(row["industry_text_share"]),
                "policy_keyword_hits": int(row["keyword_hits_total"]),
                "previous_year_available": available,
                "metric_quality_flag": ";".join(flags) if flags else "ok",
            }
        )
    return pd.DataFrame(records).sort_values(["province", "year"]).reset_index(drop=True)


def write_policy_metrics(
    clean_path: str | Path,
    keyword_path: str | Path,
    parquet_path: str | Path,
    dta_path: str | Path,
) -> pd.DataFrame:
    clean = pd.read_parquet(clean_path)
    keywords = _load_keyword_rows(keyword_path)
    metrics = build_policy_metrics(clean, keywords)
    Path(parquet_path).parent.mkdir(parents=True, exist_ok=True)
    Path(dta_path).parent.mkdir(parents=True, exist_ok=True)
    metrics.to_parquet(parquet_path, index=False)
    metrics.to_stata(dta_path, write_index=False, version=118)
    return metrics


if __name__ == "__main__":
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("--clean", default="data/processed/policy_reports_clean.parquet")
    parser.add_argument("--keywords", default="metadata/policy_industry_keywords.csv")
    parser.add_argument("--parquet", default="data/processed/province_year_policy_metrics.parquet")
    parser.add_argument("--dta", default="data/processed/province_year_policy_metrics.dta")
    args = parser.parse_args()
    write_policy_metrics(args.clean, args.keywords, args.parquet, args.dta)
