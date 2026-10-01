"""Offline closure and deterministic taxonomy helpers for CNIPA R4C0."""

from __future__ import annotations

import hashlib
import json
from collections import Counter

import pandas as pd

TERMINAL_OUTCOMES = {
    "TARGETED_H2_REQUIRED",
    "SOURCE_IDENTITY_PROBLEM",
    "OCR_OR_MANUAL_REQUIRED",
    "INDEX_COMPLETE_RESULT_SET_NO_VALID_REPORT",
    "INDEX_PAGE_CAP_REACHED_UNRESOLVED",
    "SOURCE_UNRESOLVED",
    "LOCAL_CONTROL_ONLY",
    "SOURCE_REVIEW_PASS",
}
BLOCKING_OUTCOMES = {"PENDING", "NOT_ATTEMPTED", "UNKNOWN_EXECUTION_STATE", ""}
CNIPA_SCOPE_STATUS = "CNIPA_ENTITY_NAME_NEEDS_FIX"
FOLLOWUP_TERMINAL_OUTCOMES = TERMINAL_OUTCOMES - {"SOURCE_REVIEW_PASS", "LOCAL_CONTROL_ONLY"}


def stable_frame_fingerprint(frame: pd.DataFrame, columns: list[str]) -> str:
    """Hash a frame independent of row order, with explicit null and type-safe values."""
    payload = []
    for row in frame[columns].fillna("").astype(str).to_dict(orient="records"):
        payload.append([row[column] for column in columns])
    payload.sort()
    canonical = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def classify_diagnostic_status(
    manifest: pd.DataFrame,
    outcomes: pd.DataFrame,
    request_audit_count: int,
    expected_request_count: int,
    provenance_complete: bool,
    protected_inputs_unchanged: bool,
) -> dict[str, str | int]:
    """Separate execution completion from any remaining substantive follow-up."""
    keys = ["firm_key", "year"]
    if not set(keys).issubset(manifest.columns) or not set(keys + ["diagnostic_outcome"]).issubset(
        outcomes.columns
    ):
        raise ValueError("DIAGNOSTIC_KEY_OR_OUTCOME_COLUMNS_MISSING")
    manifest_keys = list(map(tuple, manifest[keys].astype(str).to_numpy()))
    outcome_keys = list(map(tuple, outcomes[keys].astype(str).to_numpy()))
    if len(set(manifest_keys)) != len(manifest_keys):
        raise ValueError("MANIFEST_DUPLICATE_KEYS")
    if len(set(outcome_keys)) != len(outcome_keys):
        raise ValueError("OUTCOME_DUPLICATE_KEYS")
    if set(manifest_keys) != set(outcome_keys):
        raise ValueError("OUTCOME_KEY_SET_MISMATCH")
    values = outcomes.diagnostic_outcome.fillna("").astype(str)
    terminal = values.isin(TERMINAL_OUTCOMES)
    nonterminal = values.isin(BLOCKING_OUTCOMES) | ~values.isin(TERMINAL_OUTCOMES)
    complete = (
        len(manifest) == 94
        and terminal.all()
        and not nonterminal.any()
        and request_audit_count == expected_request_count
        and provenance_complete
        and protected_inputs_unchanged
    )
    execution = (
        "TARGETED_DIAGNOSTIC_PILOT_COMPLETE" if complete else "TARGETED_DIAGNOSTIC_PILOT_INCOMPLETE"
    )
    followup = "FULL_NAME_FOLLOWUP_COMPLETE"
    if not complete or values.isin(FOLLOWUP_TERMINAL_OUTCOMES).any():
        followup = "FULL_NAME_FOLLOWUP_REQUIRED"
    return {
        "targeted_diagnostic_execution_status": execution,
        "full_name_followup_status": followup,
        "terminal_rows": int(terminal.sum()),
        "nonterminal_rows": int(len(values) - terminal.sum()),
        "cnipa_entity_name_scope_status": CNIPA_SCOPE_STATUS,
    }


def build_reviewed_h1_corpus(
    predictions: pd.DataFrame,
    reviews: pd.DataFrame,
    source_provenance: pd.DataFrame,
) -> pd.DataFrame:
    """Join independently reviewed H1 values to predictions and evidence hashes."""
    keys = ["firm_key", "year"]
    for frame, label in (
        (predictions, "PREDICTIONS"),
        (reviews, "REVIEWS"),
        (source_provenance, "PROVENANCE"),
    ):
        if not set(keys).issubset(frame.columns):
            raise ValueError(f"{label}_KEY_COLUMNS_MISSING")
        if frame.duplicated(keys).any():
            raise ValueError(f"{label}_DUPLICATE_KEYS")
    valid = reviews.loc[reviews.classification.eq("VALID_FULL_H1")].copy()
    if len(valid) != 45 or not valid.review_status_review.eq("PASS").all():
        raise ValueError("INDEPENDENT_REVIEW_GATE_FAILED")
    for column in (
        "source_is_official_review",
        "source_is_correct_issuer_review",
        "source_is_correct_year_review",
        "source_is_full_annual_report_review",
    ):
        if not valid[column].map(lambda value: str(value).lower() == "true").all():
            raise ValueError(f"SOURCE_REVIEW_GATE_FAILED:{column}")
    pred = predictions.drop(
        columns=[
            c
            for c in predictions.columns
            if c.startswith("review_")
            or c in {"review_status", "reviewer_evidence_excerpt", "review_notes"}
            or c in {"pdf_sha256", "text_sha256"}
        ],
        errors="ignore",
    )
    joined = valid.merge(
        pred, on=keys, how="left", validate="one_to_one", suffixes=("_review", "_parser")
    )
    if joined.parser_evidence_status.isna().any():
        raise ValueError("PREDICTION_KEY_MISSING")
    joined = joined.merge(
        source_provenance[keys + ["pdf_sha256", "text_sha256"]],
        on=keys,
        how="left",
        validate="one_to_one",
    )
    if joined.pdf_sha256.isna().any() or joined.text_sha256.isna().any():
        raise ValueError("EVIDENCE_HASH_MISSING")
    out = (
        pd.DataFrame(
            {
                "firm_key": joined.firm_key.astype(str),
                "year": joined.year.astype(int),
                "diagnosis_group": joined.diagnosis_group.fillna(""),
                "subfamily": joined.subfamily.fillna(""),
                "risk_tier": joined.risk_tier.fillna(""),
                "source_classification": joined.classification.fillna(""),
                "evidence_pdf_sha256": joined.pdf_sha256.astype(str),
                "evidence_pdf_path": joined["_evidence_path"].fillna(""),
                "text_sha256": joined.text_sha256.astype(str),
                "old_parser_revision": joined.old_parser_revision.fillna(""),
                "parser_legal_name_current": joined.parser_legal_name_current.fillna(""),
                "parser_legal_name_at_year_end": joined.parser_legal_name_at_year_end.fillna(""),
                "parser_evidence_state": joined.parser_evidence_status.fillna(""),
                "parser_previous_name": joined.parser_previous_name.fillna(""),
                "parser_new_name": joined.parser_new_name.fillna(""),
                "parser_effective_date": joined.parser_effective_date.fillna(""),
                "parser_date_precision": joined.parser_date_precision.fillna(""),
                "review_legal_name_at_year_end": joined.review_legal_name_at_year_end_review.fillna(
                    ""
                ),
                "review_evidence_state": joined.review_change_evidence_state_review.fillna(""),
                "review_previous_name": joined.review_previous_name_review.fillna(""),
                "review_new_name": joined.review_new_name_review.fillna(""),
                "review_effective_date": joined.review_effective_date_review.fillna(""),
                "review_date_precision": joined.review_date_precision_review.fillna(""),
                "review_status": joined.review_status_review.fillna(""),
                "source_is_official": joined.source_is_official_review,
                "source_is_correct_issuer": joined.source_is_correct_issuer_review,
                "source_is_correct_year": joined.source_is_correct_year_review,
                "source_is_full_annual_report": joined.source_is_full_annual_report_review,
                "issuer_name_correct": joined.parser_legal_name_current.fillna("").eq(
                    joined.review_legal_name_at_year_end_review.fillna("")
                ),
                "year_end_name_correct": joined.parser_legal_name_at_year_end.fillna("").eq(
                    joined.review_legal_name_at_year_end_review.fillna("")
                ),
                "evidence_state_correct": joined.parser_evidence_status.fillna("").eq(
                    joined.review_change_evidence_state_review.fillna("")
                ),
                "diagnostic_outcome": joined.diagnostic_outcome.fillna(""),
                "parser_matched_label": joined.old_matched_label.fillna(""),
                "parser_evidence_context": joined.old_evidence_context.fillna(""),
                "independent_review_excerpt": joined.reviewer_evidence_excerpt_review.fillna(""),
                "text_path": joined._text_path.fillna(""),
            }
        )
        .sort_values(keys, kind="stable")
        .reset_index(drop=True)
    )
    if out[keys].duplicated().any() or len(out) != 45:
        raise ValueError("REVIEWED_CORPUS_NOT_EXACTLY_45_UNIQUE_KEYS")
    return out


def discrepancy_overlap(corpus: pd.DataFrame) -> pd.DataFrame:
    flags = ["issuer_name_correct", "year_end_name_correct", "evidence_state_correct"]
    labels = {
        (True, True, True): "ALL_THREE_CORRECT",
        (False, True, True): "ISSUER_ONLY_WRONG",
        (True, False, True): "YEAR_END_ONLY_WRONG",
        (True, True, False): "EVIDENCE_ONLY_WRONG",
        (False, False, True): "ISSUER_AND_YEAR_END_WRONG",
        (False, True, False): "ISSUER_AND_EVIDENCE_WRONG",
        (True, False, False): "YEAR_END_AND_EVIDENCE_WRONG",
        (False, False, False): "ALL_THREE_WRONG",
    }
    counts = Counter(
        labels[tuple(bool(v) for v in row)]
        for row in corpus[flags].itertuples(index=False, name=None)
    )
    result = pd.DataFrame(
        [{"overlap_category": label, "rows": counts[label]} for label in labels.values()]
    )
    if int(result.rows.sum()) != len(corpus):
        raise ValueError("DISCREPANCY_OVERLAP_NOT_EXHAUSTIVE")
    return result


def infer_root_cause(row: dict[str, object], text: str = "") -> tuple[str, str, str]:
    """Assign a reviewable generic cause from parser fields and local evidence context."""
    review_name = str(row.get("review_legal_name_at_year_end", ""))
    parsed = str(row.get("parser_legal_name_current", ""))
    context = " ".join(
        str(row.get(field, ""))
        for field in (
            "parser_matched_label",
            "parser_evidence_context",
            "independent_review_excerpt",
        )
    )
    source = f"{context} {text}"
    if review_name.startswith("无") and parsed == review_name[1:]:
        return (
            "FIELD_BOUNDARY_ERROR",
            "RESPONSE_MARKER_STRIPPING_ERROR",
            "合法名称首字被响应标记边界规则裁掉；独立审查摘录与 TXT 保留完整名称",
        )
    if (
        parsed
        and parsed != review_name
        and any(token in parsed for token in ("子公司", "有限公司", "清算注销"))
    ):
        if parsed in source or "子公司名称" in source or "分公司" in source:
            return (
                "ISSUER_SCOPE_ERROR",
                "MULTILINE_TABLE_LAYOUT",
                "提取上下文含关联主体/表格项而非发行人名称；以独立审查摘录核对",
            )
    if str(row.get("review_evidence_state", "")) == "CONFIRMED_YEAR_END_NAME_ONLY":
        if (
            row.get("parser_evidence_state") == "CONFIRMED_NO_CHANGE"
            or row.get("parser_previous_name")
            or row.get("parser_new_name")
        ):
            return (
                "TEMPORAL_EVIDENCE_OVERCLAIM",
                "",
                "H1 仅支持年末名称，解析输出额外给出无变更或变更事件信息",
            )
        if row.get("parser_evidence_state") in {"UNKNOWN", "LEGAL_NAME_EXTRACTION_FAILED"}:
            if "公司的中文名称" in source or "公司名称" in source:
                return (
                    "LABEL_LAYOUT_UNMATCHED",
                    "",
                    "独立摘录与 TXT 有明确发行人名称字段，但解析结果未命中该版式",
                )
            return (
                "LABEL_LAYOUT_UNMATCHED",
                "",
                "独立审查确认年末名称；本地 TXT 与解析标签上下文指向未覆盖的标签/标题版式",
            )
    if not parsed and row.get("review_evidence_state"):
        if "年度报告" in source and any(x in source for x in ("公司名称", "公司的中文名称")):
            return (
                "LABEL_LAYOUT_UNMATCHED",
                "",
                "官方报告正文包含发行人名称，但当前匹配标签/邻接结构未抽取",
            )
        return (
            "MULTILINE_TABLE_LAYOUT",
            "VALUE_CONTINUATION_ERROR",
            "名称证据跨行/表格布局与现有字段值边界不匹配",
        )
    if row.get("parser_evidence_state") in {
        "CONFIRMED_YEAR_END_NAME_ONLY",
        "CONFIRMED_NO_CHANGE",
    } and not row.get("evidence_state_correct"):
        return "TEMPORAL_EVIDENCE_OVERCLAIM", "", "H1 证据粒度不足以支持解析器输出的更强变更状态"
    if not row.get("year_end_name_correct") and row.get("parser_effective_date"):
        return (
            "TEMPORAL_EVIDENCE_OVERCLAIM",
            "",
            "解析器的变更日期/名称时序与独立 H1 年末名称证据不一致",
        )
    return (
        "SOURCE_TEXT_STRUCTURE_AMBIGUOUS",
        "",
        "现有 parser context、官方 TXT 和独立审查摘录不足以支持更窄的通用根因",
    )


def build_evidence_state_mismatches(corpus: pd.DataFrame) -> pd.DataFrame:
    counts: Counter[tuple[str, str, str]] = Counter()
    for row in corpus.loc[~corpus.evidence_state_correct].to_dict(orient="records"):
        parser = str(row["parser_evidence_state"])
        review = str(row["review_evidence_state"])
        if parser == "LEGAL_NAME_EXTRACTION_FAILED" and review == "CONFIRMED_YEAR_END_NAME_ONLY":
            cause = "explicit evidence missed"
        elif parser == "CONFIRMED_NO_CHANGE" and review == "CONFIRMED_YEAR_END_NAME_ONLY":
            cause = "absence incorrectly converted to NO"
        elif parser == "CONFIRMED_YEAR_END_NAME_ONLY" and review == "CONFIRMED_NAME_CHANGE":
            cause = "change-event evidence underextracted"
        else:
            cause = "other"
        counts[(parser, review, cause)] += 1
    return pd.DataFrame(
        [
            {
                "mismatch_category": f"{parser} -> {review}",
                "parser_state": parser,
                "review_state": review,
                "rows": count,
                "cause_family": cause,
            }
            for (parser, review, cause), count in sorted(counts.items())
        ]
    )
