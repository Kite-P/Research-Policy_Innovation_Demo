from __future__ import annotations

import pandas as pd
import pytest

from src.cnipa_r4c0_taxonomy import (
    build_evidence_state_mismatches,
    build_reviewed_h1_corpus,
    classify_diagnostic_status,
    discrepancy_overlap,
    infer_root_cause,
    stable_frame_fingerprint,
)


def manifest_and_outcomes(count: int = 94, outcome: str = "SOURCE_UNRESOLVED"):
    manifest = pd.DataFrame([{"firm_key": f"K{i}", "year": 2020} for i in range(count)])
    outcomes = manifest.copy()
    outcomes["diagnostic_outcome"] = outcome
    return manifest, outcomes


def test_all_94_terminal_outcomes_close_diagnostic_execution_but_keep_followup_open():
    manifest, outcomes = manifest_and_outcomes()
    result = classify_diagnostic_status(manifest, outcomes, 53, 53, True, True)
    assert result["targeted_diagnostic_execution_status"] == "TARGETED_DIAGNOSTIC_PILOT_COMPLETE"
    assert result["full_name_followup_status"] == "FULL_NAME_FOLLOWUP_REQUIRED"
    assert result["terminal_rows"] == 94 and result["nonterminal_rows"] == 0


@pytest.mark.parametrize(
    "terminal",
    ["SOURCE_UNRESOLVED", "TARGETED_H2_REQUIRED", "OCR_OR_MANUAL_REQUIRED", "LOCAL_CONTROL_ONLY"],
)
def test_unresolved_followup_outcomes_are_still_valid_terminal_rows(terminal):
    manifest, outcomes = manifest_and_outcomes(outcome=terminal)
    result = classify_diagnostic_status(manifest, outcomes, 53, 53, True, True)
    assert result["targeted_diagnostic_execution_status"] == "TARGETED_DIAGNOSTIC_PILOT_COMPLETE"


@pytest.mark.parametrize("blocked", ["PENDING", "NOT_ATTEMPTED", "UNKNOWN_EXECUTION_STATE"])
def test_nonterminal_or_unknown_state_blocks_execution_completion(blocked):
    manifest, outcomes = manifest_and_outcomes()
    outcomes.loc[0, "diagnostic_outcome"] = blocked
    result = classify_diagnostic_status(manifest, outcomes, 53, 53, True, True)
    assert result["targeted_diagnostic_execution_status"] == "TARGETED_DIAGNOSTIC_PILOT_INCOMPLETE"


def test_protected_hash_drift_blocks_completion_and_scope_status_never_changes():
    manifest, outcomes = manifest_and_outcomes()
    result = classify_diagnostic_status(manifest, outcomes, 53, 53, True, False)
    assert result["targeted_diagnostic_execution_status"] == "TARGETED_DIAGNOSTIC_PILOT_INCOMPLETE"
    assert result["cnipa_entity_name_scope_status"] == "CNIPA_ENTITY_NAME_NEEDS_FIX"


def test_execution_audit_and_exact_manifest_are_required():
    manifest, outcomes = manifest_and_outcomes()
    assert (
        classify_diagnostic_status(manifest, outcomes, 52, 53, True, True)[
            "targeted_diagnostic_execution_status"
        ]
        == "TARGETED_DIAGNOSTIC_PILOT_INCOMPLETE"
    )
    with pytest.raises(ValueError, match="OUTCOME_KEY_SET_MISMATCH"):
        classify_diagnostic_status(manifest, outcomes.iloc[:-1], 53, 53, True, True)


def simple_frames():
    predictions = pd.DataFrame(
        [
            {
                "firm_key": f"K{i}",
                "year": 2022,
                "diagnosis_group": "GAP",
                "subfamily": "LAYOUT",
                "risk_tier": "HIGH",
                "old_parser_revision": "r0",
                "parser_legal_name_current": "Issuer",
                "parser_legal_name_at_year_end": "Issuer",
                "parser_evidence_status": "UNKNOWN",
                "parser_previous_name": "",
                "parser_new_name": "",
                "parser_effective_date": "",
                "parser_date_precision": "unknown",
                "diagnostic_outcome": "TARGETED_H2_REQUIRED",
                "old_matched_label": "Company name",
                "old_evidence_context": "context",
                "_text_path": "x.txt",
                "_evidence_path": "x.pdf",
                "review_legal_name_at_year_end": "poison-parser-copy",
            }
            for i in range(45)
        ]
    )
    reviews = pd.DataFrame(
        [
            {
                "firm_key": f"K{i}",
                "year": 2022,
                "classification": "VALID_FULL_H1",
                "source_is_official_review": True,
                "source_is_correct_issuer_review": True,
                "source_is_correct_year_review": True,
                "source_is_full_annual_report_review": True,
                "review_legal_name_at_year_end_review": "Issuer",
                "review_change_evidence_state_review": "CONFIRMED_YEAR_END_NAME_ONLY",
                "review_previous_name_review": "",
                "review_new_name_review": "",
                "review_effective_date_review": "",
                "review_date_precision_review": "",
                "review_status_review": "PASS",
                "reviewer_evidence_excerpt_review": "independent excerpt",
            }
            for i in range(45)
        ]
    )
    provenance = pd.DataFrame(
        [
            {"firm_key": f"K{i}", "year": 2022, "pdf_sha256": "pdf", "text_sha256": "txt"}
            for i in range(45)
        ]
    )
    return predictions, reviews, provenance


def test_corpus_requires_exactly_45_independent_full_h1_reviews_and_unique_keys():
    predictions, reviews, provenance = simple_frames()
    corpus = build_reviewed_h1_corpus(predictions, reviews, provenance)
    assert len(corpus) == 45
    assert corpus.firm_key.nunique() == 45
    assert corpus.review_status.eq("PASS").all()
    assert corpus.source_classification.eq("VALID_FULL_H1").all()
    assert corpus.source_is_official.astype(str).str.lower().eq("true").all()
    assert corpus.parser_legal_name_current.eq("Issuer").all()
    assert corpus.review_legal_name_at_year_end.eq("Issuer").all()
    assert not corpus.review_legal_name_at_year_end.eq("poison-parser-copy").any()


def test_corpus_fingerprint_is_deterministic_and_order_independent():
    predictions, reviews, provenance = simple_frames()
    corpus = build_reviewed_h1_corpus(predictions, reviews, provenance)
    columns = ["firm_key", "year", "evidence_pdf_sha256", "review_legal_name_at_year_end"]
    assert stable_frame_fingerprint(corpus, columns) == stable_frame_fingerprint(
        corpus.sample(frac=1, random_state=4), columns
    )


def test_overlap_matrix_is_mutually_exclusive_and_exhaustive():
    flags = [(True, True, True), (False, True, True), (True, False, True), (False, False, False)]
    corpus = pd.DataFrame(
        flags * 11 + flags[:1],
        columns=["issuer_name_correct", "year_end_name_correct", "evidence_state_correct"],
    )
    overlap = discrepancy_overlap(corpus)
    assert len(overlap) == 8
    assert overlap.rows.sum() == len(corpus)
    assert overlap.loc[overlap.overlap_category.eq("ALL_THREE_CORRECT"), "rows"].item() == 12


def test_generic_field_boundary_case_and_h2_correctness_are_not_conflated():
    cause = infer_root_cause(
        {
            "review_legal_name_at_year_end": "无某股份有限公司",
            "parser_legal_name_current": "某股份有限公司",
            "parser_evidence_state": "UNKNOWN",
            "review_evidence_state": "CONFIRMED_YEAR_END_NAME_ONLY",
        },
        "TXT contains complete legal name",
    )
    assert cause[0] == "FIELD_BOUNDARY_ERROR"
    assert "RESPONSE_MARKER_STRIPPING_ERROR" in cause[1]
    corpus = pd.DataFrame(
        [
            {
                "issuer_name_correct": True,
                "year_end_name_correct": True,
                "evidence_state_correct": True,
            }
        ]
    )
    assert (
        discrepancy_overlap(corpus).query("overlap_category == 'ALL_THREE_CORRECT'").rows.item()
        == 1
    )


def test_frozen_repository_corpus_recomputes_expected_metrics_and_all_error_rows_have_causes():
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    source = root / "results/cnipa_full_gap_diagnosis/r4b_20260930/r4b2_20261001"
    predictions = pd.read_csv(source / "pilot_predictions.csv", dtype={"firm_key": str}).fillna("")
    reviews = pd.read_csv(source / "r4b2_content_review_45.csv", dtype={"firm_key": str}).fillna("")
    provenance = pd.read_csv(
        source / "r4b2_source_identity_reconciliation_64.csv", dtype={"firm_key": str}
    ).fillna("")
    corpus = build_reviewed_h1_corpus(predictions, reviews, provenance)
    assert (
        int(corpus.issuer_name_correct.sum()),
        int(corpus.year_end_name_correct.sum()),
        int(corpus.evidence_state_correct.sum()),
    ) == (27, 26, 28)
    overlap = discrepancy_overlap(corpus)
    assert overlap.rows.sum() == 45
    assert overlap.loc[overlap.overlap_category.eq("ALL_THREE_CORRECT"), "rows"].item() == 25

    taxonomy = []
    for row in corpus.to_dict(orient="records"):
        text_path = source / row["text_path"]
        text = text_path.read_text(encoding="utf-8", errors="replace")
        root_cause = infer_root_cause(row, text)[0]
        wrong = not all(
            bool(row[field])
            for field in ("issuer_name_correct", "year_end_name_correct", "evidence_state_correct")
        )
        if wrong:
            taxonomy.append(root_cause)
    assert len(taxonomy) == 20
    assert set(taxonomy) >= {"FIELD_BOUNDARY_ERROR", "ISSUER_SCOPE_ERROR", "LABEL_LAYOUT_UNMATCHED"}
    assert all(taxonomy.count(cause) > 0 for cause in set(taxonomy))

    state_rows = corpus.loc[~corpus.evidence_state_correct]
    state_distribution = build_evidence_state_mismatches(corpus)
    assert state_distribution.rows.sum() == len(state_rows) == 17
    assert state_distribution.set_index("mismatch_category").rows.to_dict() == {
        "LEGAL_NAME_EXTRACTION_FAILED -> CONFIRMED_YEAR_END_NAME_ONLY": 14,
        "CONFIRMED_NO_CHANGE -> CONFIRMED_YEAR_END_NAME_ONLY": 2,
        "CONFIRMED_YEAR_END_NAME_ONLY -> CONFIRMED_NAME_CHANGE": 1,
    }
    assert state_distribution.set_index("cause_family").rows.to_dict() == {
        "explicit evidence missed": 14,
        "absence incorrectly converted to NO": 2,
        "change-event evidence underextracted": 1,
    }


def test_root_cause_classification_does_not_depend_on_firm_identifier():
    row = {
        "review_legal_name_at_year_end": "无某股份有限公司",
        "parser_legal_name_current": "某股份有限公司",
        "parser_evidence_state": "UNKNOWN",
        "review_evidence_state": "CONFIRMED_YEAR_END_NAME_ONLY",
    }
    first = infer_root_cause({**row, "firm_key": "SSE:000000"})
    second = infer_root_cause({**row, "firm_key": "SZSE:999999"})
    assert first == second
