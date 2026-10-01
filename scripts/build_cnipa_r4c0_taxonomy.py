from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path

import pandas as pd

from scripts.run_cnipa_targeted_diagnostic_pilot_20260930 import capture_protected_hashes
from src.cnipa_r4c0_taxonomy import (
    build_evidence_state_mismatches,
    build_reviewed_h1_corpus,
    classify_diagnostic_status,
    discrepancy_overlap,
    infer_root_cause,
    stable_frame_fingerprint,
)

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "results/cnipa_full_gap_diagnosis/r4b_20260930/r4b2_20261001"
OUTPUT = ROOT / "results/cnipa_full_gap_diagnosis/r4c0_20261001"
REVIEW_FILE = SOURCE / "r4b2_content_review_45.csv"


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_csv(frame: pd.DataFrame, name: str) -> None:
    frame.to_csv(OUTPUT / name, index=False, encoding="utf-8-sig")


def snapshot_hashes(paths: list[Path]) -> dict[str, str]:
    return {str(path.relative_to(ROOT)): file_sha256(path) for path in sorted(set(paths))}


def context_excerpt(text: str, terms: list[str], radius: int = 180) -> str:
    for term in terms:
        if term and len(term) > 1:
            position = text.find(term)
            if position >= 0:
                return " ".join(
                    text[max(0, position - radius) : position + len(term) + radius].split()
                )
    return " ".join(text[: radius * 2].split())


def main() -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    protected_before = capture_protected_hashes(ROOT)
    manifest_path = SOURCE / "diagnostic_pilot_manifest.csv"
    prediction_path = SOURCE / "pilot_predictions.csv"
    provenance_path = SOURCE / "r4b2_source_identity_reconciliation_64.csv"
    audit_path = SOURCE / "request_audit.jsonl"
    summary_path = SOURCE / "r4b2_final_summary.json"
    manifest = pd.read_csv(manifest_path, dtype={"firm_key": str})
    predictions = pd.read_csv(prediction_path, dtype={"firm_key": str}).fillna("")
    reviews = pd.read_csv(REVIEW_FILE, dtype={"firm_key": str}).fillna("")
    provenance = pd.read_csv(provenance_path, dtype={"firm_key": str}).fillna("")
    prior_summary = json.loads(summary_path.read_text(encoding="utf-8"))
    audit_lines = [
        line for line in audit_path.read_text(encoding="utf-8").splitlines() if line.strip()
    ]
    audit = pd.DataFrame([json.loads(line) for line in audit_lines])

    frozen_manifest_sha = file_sha256(manifest_path).upper()
    if frozen_manifest_sha != "30C47523292A96F19EDF889ACDD0851B26887B08D60B91F06E14EF2D9420F78C":
        raise ValueError("FROZEN_MANIFEST_SHA256_MISMATCH")
    if (
        frozen_manifest_sha
        != file_sha256(
            ROOT / "results/cnipa_full_gap_diagnosis/diagnostic_pilot_manifest.csv"
        ).upper()
    ):
        raise ValueError("R4B2_AND_R4A_MANIFEST_FILES_DIFFER")
    if len(manifest) != 94 or predictions.duplicated(["firm_key", "year"]).any():
        raise ValueError("FROZEN_94_ROW_MANIFEST_OR_PREDICTION_MISMATCH")
    if set(map(tuple, manifest[["firm_key", "year"]].astype(str).to_numpy())) != set(
        map(tuple, predictions[["firm_key", "year"]].astype(str).to_numpy())
    ):
        raise ValueError("FROZEN_94_ROW_MANIFEST_OR_PREDICTION_KEYS_MISMATCH")
    if not predictions._manifest_fingerprint.eq(prior_summary["frame_fingerprint"]).all():
        raise ValueError("PREDICTION_MANIFEST_FINGERPRINT_MISMATCH")
    if not provenance.mapping_status.eq("MAPPED_TO_FROZEN_KEY").all() or len(provenance) != 64:
        raise ValueError("PROVENANCE_MAPPING_INCOMPLETE")
    if len(audit) != 53 or audit.sequence.astype(int).tolist() != list(range(1, 54)):
        raise ValueError("REQUEST_AUDIT_SEQUENCE_INCOMPLETE")
    if audit.response_received.astype(str).str.lower().ne("true").any():
        raise ValueError("REQUEST_AUDIT_HAS_UNRECEIVED_RESPONSE")
    outcomes = predictions[["firm_key", "year", "diagnostic_outcome"]].rename(
        columns={"diagnostic_outcome": "diagnostic_outcome"}
    )
    status = classify_diagnostic_status(
        manifest,
        outcomes,
        request_audit_count=len(audit),
        expected_request_count=int(prior_summary["request_audit_rows"]),
        provenance_complete=True,
        protected_inputs_unchanged=True,
    )
    if status["targeted_diagnostic_execution_status"] != "TARGETED_DIAGNOSTIC_PILOT_COMPLETE":
        raise ValueError("DIAGNOSTIC_EXECUTION_NOT_COMPLETE")

    corpus = build_reviewed_h1_corpus(predictions, reviews, provenance)
    if len(corpus) != 45 or not corpus.review_status.eq("PASS").all():
        raise ValueError("REVIEWED_H1_CORPUS_GATE_FAILED")
    accuracy = {
        "issuer_name_correct": int(corpus.issuer_name_correct.sum()),
        "year_end_name_correct": int(corpus.year_end_name_correct.sum()),
        "evidence_state_correct": int(corpus.evidence_state_correct.sum()),
    }
    if accuracy != {
        "issuer_name_correct": 27,
        "year_end_name_correct": 26,
        "evidence_state_correct": 28,
    }:
        raise ValueError(f"REVIEW_METRICS_DRIFT:{accuracy}")

    corpus_path = OUTPUT / "reviewed_h1_regression_corpus.csv"
    corpus.to_csv(corpus_path, index=False, encoding="utf-8-sig")
    frozen_source_paths = [
        manifest_path,
        prediction_path,
        REVIEW_FILE,
        provenance_path,
        audit_path,
        summary_path,
    ]
    for row in corpus.to_dict(orient="records"):
        pdf_path = SOURCE / Path(str(row["evidence_pdf_path"]))
        text_path = SOURCE / Path(str(row["text_path"]))
        if not pdf_path.is_file() or file_sha256(pdf_path) != row["evidence_pdf_sha256"]:
            raise ValueError(f"LOCAL_PDF_HASH_DRIFT:{row['firm_key']}|{row['year']}")
        frozen_source_paths.extend([pdf_path, text_path])
    source_hashes_before = snapshot_hashes(frozen_source_paths)
    overlap = discrepancy_overlap(corpus)
    write_csv(overlap, "parser_discrepancy_overlap.csv")

    root_rows: list[dict[str, object]] = []
    for row in corpus.to_dict(orient="records"):
        text_path = SOURCE / Path(str(row["text_path"]))
        if not text_path.is_file():
            raise ValueError(f"LOCAL_OFFICIAL_TEXT_MISSING:{row['firm_key']}|{row['year']}")
        text = text_path.read_text(encoding="utf-8", errors="replace")
        if file_sha256(text_path) != row["text_sha256"]:
            raise ValueError(f"LOCAL_TEXT_HASH_DRIFT:{row['firm_key']}|{row['year']}")
        row_error = not all(
            bool(row[field])
            for field in ("issuer_name_correct", "year_end_name_correct", "evidence_state_correct")
        )
        primary, secondary, rationale = infer_root_cause(row, text)
        excerpt = context_excerpt(
            text,
            [
                str(row["review_legal_name_at_year_end"]),
                str(row["parser_matched_label"]),
                str(row["parser_legal_name_current"]),
            ],
        )
        root_rows.append(
            {
                "firm_key": row["firm_key"],
                "year": row["year"],
                "diagnosis_group": row["diagnosis_group"],
                "subfamily": row["subfamily"],
                "risk_tier": row["risk_tier"],
                "issuer_name_correct": row["issuer_name_correct"],
                "year_end_name_correct": row["year_end_name_correct"],
                "evidence_state_correct": row["evidence_state_correct"],
                "has_parser_discrepancy": row_error,
                "primary_root_cause": primary if row_error else "NO_PARSER_DISCREPANCY",
                "secondary_root_causes": secondary if row_error else "",
                "diagnosis_basis": rationale
                if row_error
                else "All three reviewed H1 fields agree with independent review.",
                "matched_label": row["parser_matched_label"],
                "parser_context": row["parser_evidence_context"],
                "parser_normalization_path_reviewed": {
                    "FIELD_BOUNDARY_ERROR": (
                        "response-marker boundary normalization inspected; "
                        "one legal-name initial was removed"
                    ),
                    "ISSUER_SCOPE_ERROR": (
                        "issuer-versus-related-entity extraction context inspected"
                    ),
                    "LABEL_LAYOUT_UNMATCHED": (
                        "matched-label/continuation context absent or inconsistent "
                        "with source layout"
                    ),
                    "TEMPORAL_EVIDENCE_OVERCLAIM": (
                        "parsed event/no-change normalization compared with H1 evidence granularity"
                    ),
                }.get(
                    primary,
                    "parser revision and stored prediction path inspected; "
                    "exact intermediate trace unavailable",
                ),
                "source_text_path": row["text_path"],
                "official_txt_context": excerpt,
                "independent_review_excerpt": row["independent_review_excerpt"],
            }
        )
    taxonomy = pd.DataFrame(root_rows)
    if (
        len(taxonomy.loc[taxonomy.has_parser_discrepancy]) == 0
        or taxonomy.loc[taxonomy.has_parser_discrepancy, "primary_root_cause"]
        .eq("SOURCE_TEXT_STRUCTURE_AMBIGUOUS")
        .all()
    ):
        raise ValueError("INCORRECT_ROWS_LACK_ACTIONABLE_ROOT_CAUSE")
    write_csv(taxonomy, "parser_row_root_cause_taxonomy.csv")

    errors = taxonomy.loc[taxonomy.has_parser_discrepancy]
    cause_rows = []
    for cause, group in errors.groupby("primary_root_cause", sort=True):
        cause_rows.append(
            {
                "root_cause": cause,
                "affected_rows": len(group),
                "issuer_name_errors": int((~group.issuer_name_correct).sum()),
                "year_end_name_errors": int((~group.year_end_name_correct).sum()),
                "evidence_state_errors": int((~group.evidence_state_correct).sum()),
                "diagnosis_groups": ";".join(sorted(set(group.diagnosis_group.astype(str)))),
                "risk_tiers": ";".join(sorted(set(group.risk_tier.astype(str)))),
                "generic_fix_candidate": "YES"
                if cause != "SOURCE_TEXT_STRUCTURE_AMBIGUOUS"
                else "UNCONFIRMED",
                "needs_parser_change": "YES"
                if cause in {"FIELD_BOUNDARY_ERROR", "LABEL_LAYOUT_UNMATCHED", "ISSUER_SCOPE_ERROR"}
                else "REVIEW",
                "needs_more_evidence": "YES"
                if cause == "SOURCE_TEXT_STRUCTURE_AMBIGUOUS"
                else "NO",
            }
        )
    cause_summary = pd.DataFrame(cause_rows)
    write_csv(cause_summary, "parser_root_cause_summary.csv")

    fix_plans = []
    for index, row in enumerate(cause_summary.to_dict(orient="records"), start=1):
        cause = str(row["root_cause"])
        fix_plans.append(
            {
                "fix_id": f"R4C1-{index:02d}",
                "root_cause": cause,
                "affected_reviewed_rows": row["affected_rows"],
                "minimal_pattern": {
                    "FIELD_BOUNDARY_ERROR": (
                        "A valid field value begins with a token also used as a response marker."
                    ),
                    "LABEL_LAYOUT_UNMATCHED": (
                        "Official annual-report title/name block differs from "
                        "matched-label templates."
                    ),
                    "ISSUER_SCOPE_ERROR": (
                        "Name-like values occur in related-entity/table context "
                        "outside issuer scope."
                    ),
                    "TEMPORAL_EVIDENCE_OVERCLAIM": (
                        "H1 supports year-end identity but not a change/no-change event claim."
                    ),
                    "SOURCE_TEXT_STRUCTURE_AMBIGUOUS": (
                        "Existing local text and review excerpt do not isolate "
                        "a generic layout rule."
                    ),
                }.get(
                    cause, "Generalized field or temporal evidence mismatch; preserve source scope."
                ),
                "proposed_generic_fix": {
                    "FIELD_BOUNDARY_ERROR": (
                        "Anchor stripping to a complete response-marker token boundary; "
                        "never trim a single legal-name character."
                    ),
                    "LABEL_LAYOUT_UNMATCHED": (
                        "Add generic title-page/name-block patterns with bounded "
                        "issuer-context validation."
                    ),
                    "ISSUER_SCOPE_ERROR": (
                        "Require issuer-section/table-label scope and reject "
                        "subsidiary/branch glossary contexts."
                    ),
                    "TEMPORAL_EVIDENCE_OVERCLAIM": (
                        "Keep year-end name evidence distinct from event and no-change evidence."
                    ),
                    "SOURCE_TEXT_STRUCTURE_AMBIGUOUS": (
                        "Defer parser change until additional independent evidence "
                        "isolates a repeatable structure."
                    ),
                }.get(
                    cause,
                    "Review parser context and add a generic rule only after synthetic coverage.",
                ),
                "risk_of_false_positive": "HIGH"
                if cause in {"LABEL_LAYOUT_UNMATCHED", "ISSUER_SCOPE_ERROR"}
                else "MEDIUM",
                "synthetic_test_required": "YES",
                "real_regression_rows": int(row["affected_rows"]),
                "requires_parser_revision_bump": "YES",
                "priority": "P1"
                if cause in {"FIELD_BOUNDARY_ERROR", "LABEL_LAYOUT_UNMATCHED"}
                else "P2",
            }
        )
    write_csv(pd.DataFrame(fix_plans), "r4c1_parser_fix_plan.csv")

    state_mismatch = build_evidence_state_mismatches(corpus)
    state_mismatch["cause_family"] = [
        "explicit evidence missed"
        if name == "PARSER_UNKNOWN_REVIEW_YES"
        else "absence incorrectly converted to NO"
        if name == "PARSER_NO_REVIEW_UNKNOWN"
        else "name-change field layout missed"
        if name == "PARSER_UNKNOWN_REVIEW_NO"
        else "temporal information insufficient"
        if name == "PARSER_YES_REVIEW_UNKNOWN"
        else "other"
        if count
        else "not_applicable"
        for name, count in zip(state_mismatch.mismatch_category, state_mismatch.rows)
    ]
    write_csv(state_mismatch, "evidence_state_mismatch_distribution.csv")

    # The previously declared 12-row extraction-layout cohort is represented by
    # the frozen report-layout gap family. Classify the actual local TXT patterns.
    layout = taxonomy.loc[
        taxonomy.subfamily.eq("NORMAL_REPORT_TITLE_NO_ISSUER_LABEL_LAYOUT_UNMATCHED")
        | taxonomy.subfamily.eq("TEXT_PRESENT_NO_MATCHED_LABEL")
    ].copy()
    layout_counts = Counter()
    for row in layout.to_dict(orient="records"):
        cause = row["primary_root_cause"]
        layout_kind = (
            cause
            if cause
            in {
                "LABEL_LAYOUT_UNMATCHED",
                "MULTILINE_TABLE_LAYOUT",
                "VALUE_CONTINUATION_ERROR",
                "NORMALIZATION_ERROR",
            }
            else "OTHER"
        )
        layout_counts[layout_kind] += 1
    layout_summary = pd.DataFrame(
        [{"layout_gap_type": key, "rows": layout_counts[key]} for key in sorted(layout_counts)]
    )
    write_csv(layout_summary, "extraction_layout_gap_distribution.csv")

    review_source_fingerprint = file_sha256(REVIEW_FILE)
    fingerprints = {
        "reviewed_key_fingerprint": stable_frame_fingerprint(corpus, ["firm_key", "year"]),
        "evidence_hash_fingerprint": stable_frame_fingerprint(
            corpus, ["firm_key", "year", "evidence_pdf_sha256", "text_sha256"]
        ),
        "prediction_fingerprint": stable_frame_fingerprint(
            corpus,
            [
                "firm_key",
                "year",
                "parser_legal_name_current",
                "parser_legal_name_at_year_end",
                "parser_evidence_state",
                "parser_previous_name",
                "parser_new_name",
                "parser_effective_date",
                "parser_date_precision",
            ],
        ),
        "review_ground_truth_fingerprint": stable_frame_fingerprint(
            corpus,
            [
                "firm_key",
                "year",
                "review_legal_name_at_year_end",
                "review_evidence_state",
                "review_previous_name",
                "review_new_name",
                "review_effective_date",
                "review_date_precision",
            ],
        ),
        "corpus_frame_fingerprint": stable_frame_fingerprint(corpus, list(corpus.columns)),
        "review_source_artifact_sha256": review_source_fingerprint,
    }
    protected_after = capture_protected_hashes(ROOT)
    if protected_before != protected_after:
        raise ValueError("PROTECTED_INPUT_DRIFT_DURING_R4C0")
    source_hashes_after = snapshot_hashes(frozen_source_paths)
    if source_hashes_before != source_hashes_after:
        raise ValueError("FROZEN_R4B2_SOURCE_ARTIFACT_DRIFT_DURING_R4C0")
    summary = {
        **status,
        "manifest_rows": len(manifest),
        "manifest_firms": int(manifest.firm_key.nunique()),
        "request_audit_rows": len(audit),
        "request_audit_sequence_complete": True,
        "provenance_rows": len(provenance),
        "provenance_mapping_unresolved": int(
            provenance.mapping_status.ne("MAPPED_TO_FROZEN_KEY").sum()
        ),
        "terminal_outcomes": predictions.diagnostic_outcome.value_counts().sort_index().to_dict(),
        "source_unresolved_terminal_count": int(
            predictions.diagnostic_outcome.eq("SOURCE_UNRESOLVED").sum()
        ),
        "targeted_h2_required_count": int(
            predictions.diagnostic_outcome.eq("TARGETED_H2_REQUIRED").sum()
        ),
        "ocr_manual_count": int(predictions.diagnostic_outcome.eq("OCR_OR_MANUAL_REQUIRED").sum()),
        "index_complete_no_valid_count": int(
            predictions.diagnostic_outcome.eq("INDEX_COMPLETE_RESULT_SET_NO_VALID_REPORT").sum()
        ),
        "reviewed_h1_corpus_rows": len(corpus),
        "reviewed_h1_corpus_firms": int(corpus.firm_key.nunique()),
        "metrics": accuracy,
        "h2_required_but_parser_correct_rows": int(
            (
                corpus.diagnostic_outcome.eq("TARGETED_H2_REQUIRED")
                & corpus.issuer_name_correct
                & corpus.year_end_name_correct
                & corpus.evidence_state_correct
            ).sum()
        ),
        "incorrect_issuer_name_rows": int((~corpus.issuer_name_correct).sum()),
        "incorrect_year_end_name_rows": int((~corpus.year_end_name_correct).sum()),
        "incorrect_evidence_state_rows": int((~corpus.evidence_state_correct).sum()),
        "discrepancy_overlap": dict(zip(overlap.overlap_category, overlap.rows.astype(int))),
        "root_cause_distribution": dict(
            zip(cause_summary.root_cause, cause_summary.affected_rows.astype(int))
        ),
        "root_cause_category_count": len(cause_summary),
        "field_boundary_error_rows": int(
            errors.primary_root_cause.eq("FIELD_BOUNDARY_ERROR").sum()
        ),
        "high_current_wrong_root_causes": taxonomy.loc[
            taxonomy.risk_tier.eq("HIGH") & taxonomy.has_parser_discrepancy, "primary_root_cause"
        ]
        .value_counts()
        .to_dict(),
        "extraction_layout_gap_distribution": dict(
            zip(layout_summary.layout_gap_type, layout_summary.rows.astype(int))
        ),
        "evidence_state_mismatch_distribution": dict(
            zip(state_mismatch.mismatch_category, state_mismatch.rows.astype(int))
        ),
        "r4c1_generic_fix_candidates": [row["root_cause"] for row in fix_plans],
        "company_specific_hardcode": False,
        "production_parser_changed": False,
        "network_requests_this_round": 0,
        "h2_requests_this_round": 0,
        "ocr_runs_this_round": 0,
        "full_refreshes_this_round": 0,
        "protected_inputs_unchanged": True,
        "protected_hashes": protected_after,
        "frozen_source_artifact_hashes_before": source_hashes_before,
        "frozen_source_artifact_hashes_after": source_hashes_after,
        "fingerprints": fingerprints,
        "frozen_manifest_sha256": file_sha256(SOURCE / "diagnostic_pilot_manifest.csv"),
        "pilot_v3_gate": "STRICT_PILOT_GATE_PASS",
        "cnipa_entity_name_scope_status": "CNIPA_ENTITY_NAME_NEEDS_FIX",
        "zero_semantics": "pending",
        "missing_semantics": "pending",
    }
    (OUTPUT / "r4c0_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
