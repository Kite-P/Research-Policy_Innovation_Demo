from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.cnipa_annual_report_names import (  # noqa: E402
    PARSER_REVISION,
    build_canonical_change_event_roster,
    extract_annual_report_legal_name_evidence,
    is_change_related_candidate,
)
from src.cnipa_strict14_replay import (  # noqa: E402
    build_complete_row_predictions,
    build_source_manifest,
    fetch_h1_sources,
    score_events,
    score_strict_rows,
    strict14_keys,
    validate_h1_document,
    verify_ground_truth_fingerprints,
)
from src.historical_province_sources import CNINFOAnnualReportClient, SourceBlocked  # noqa: E402

OUT = ROOT / "results/cnipa_preflight/strict14_v3_replay_20261001"
LEGAL = ROOT / "results/cnipa_legal_name_recovery"
EXPECTED_RAW_HASHES = {
    "pilot_change_row_ground_truth.csv": (
        "81eb18d82611ce7bddf7d9895ed57237026b9b5d97b0dd258dda7d0ba266d342"
    ),
    "pilot_change_event_ground_truth.csv": (
        "e1900a01fff61610e1325623ec59870d9063a14c6925e4075639855745d5e174"
    ),
    "pilot_change_evidence_state_ground_truth.csv": (
        "523b1a31640f29ffe9be9b003e8e44afc514f08e0e028aef2a126817b7a31cf3"
    ),
}


class ExactURLSession(requests.Session):
    """Allow one GET per exact pre-existing manifest URL and no redirects."""

    def __init__(self, urls: set[str]):
        super().__init__()
        self.urls = urls
        self.requested: list[str] = []
        self.responses: list[requests.Response] = []

    def request(self, method: str, url: str, **kwargs):
        if method.upper() != "GET" or url not in self.urls or url in self.requested:
            raise RuntimeError("STRICT14_NETWORK_ALLOWLIST_VIOLATION")
        self.requested.append(url)
        kwargs["allow_redirects"] = False
        response = super().request(method, url, **kwargs)
        self.responses.append(response)
        return response


def _hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _json(path: Path, payload: dict[str, object]) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8"
    )


def _event_records(
    candidate_rows: pd.DataFrame, h2_audit: pd.DataFrame
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, str]]:
    canonical_rows = []
    for item in candidate_rows.to_dict("records"):
        canonical_rows.append(
            {
                "firm_key": item["firm_key"],
                "year": item["year"],
                "legal_name_previous": item.get("parser_legal_name_previous", ""),
                "legal_name_new": item.get("parser_legal_name_new", ""),
                "change_effective_date": item.get("parser_change_effective_date", ""),
                "date_precision": item.get("parser_date_precision", "unknown"),
                "change_evidence_tier": item.get(
                    "change_evidence_tier", item.get("evidence_tier", "")
                ),
                "change_evidence_url": item.get("source_url", ""),
                "change_announcement_id": item.get("change_announcement_id", ""),
            }
        )
    events, mapping = build_canonical_change_event_roster(canonical_rows)
    event_frame = pd.DataFrame(events)
    if not event_frame.empty:
        event_frame = event_frame.rename(
            columns={
                "previous_legal_name": "parser_previous_legal_name",
                "new_legal_name": "parser_new_legal_name",
                "effective_date": "parser_effective_date",
                "date_precision": "parser_date_precision",
                "evidence_tier": "evidence_tier",
                "evidence_url": "source_url",
                "announcement_id": "source_announcement_id",
            }
        )
    carry = []
    for row in h2_audit.fillna("").to_dict("records"):
        if (
            row.get("status") != "RESOLVED_H2"
            or not row.get("notice_url")
            or not row.get("announcement_id")
            or not re.fullmatch(r"[0-9a-fA-F]{64}", str(row.get("notice_pdf_sha256", "")))
            or int(float(row.get("notice_pdf_bytes") or 0)) <= 0
        ):
            continue
        event_key = hashlib.sha256(
            f"{row['firm_key']}|{row['year']}|{row['announcement_id']}".encode()
        ).hexdigest()[:20]
        carry.append(
            {
                "event_id": f"H2-{event_key}",
                "firm_key": row["firm_key"],
                "year": int(row["year"]),
                "parser_previous_legal_name": row.get("previous_legal_name", ""),
                "parser_new_legal_name": row.get("new_legal_name", ""),
                "parser_effective_date": row.get("change_effective_date", "")
                or (
                    str(row["year"]) if str(row.get("date_precision", "")).lower() == "year" else ""
                ),
                "parser_date_precision": row.get("date_precision", "unknown"),
                "evidence_tier": "H2",
                "source_url": row["notice_url"],
                "source_announcement_id": str(row["announcement_id"]),
                "notice_pdf_sha256": row["notice_pdf_sha256"],
                "notice_pdf_bytes": int(float(row["notice_pdf_bytes"])),
                "source_status": "RESOLVED_H2",
            }
        )
    h2 = pd.DataFrame(carry)
    if not h2.empty:
        # Existing verified notice evidence may corroborate a same firm/year parser row,
        # but never changes its parser-produced H1 values.
        event_frame = pd.concat([event_frame, h2], ignore_index=True, sort=False)
    if not event_frame.empty:
        event_frame = event_frame.drop_duplicates(
            ["firm_key", "year", "evidence_tier"], keep="first"
        )
    return event_frame, h2, mapping


def _run_frozen45() -> dict[str, object]:
    corpus_path = (
        ROOT / "results/cnipa_full_gap_diagnosis/r4c0_20261001/reviewed_h1_regression_corpus.csv"
    )
    corpus = pd.read_csv(corpus_path, keep_default_na=False)
    evidence_roots = [
        ROOT / "results/cnipa_full_gap_diagnosis/r4b_20260930",
        ROOT / "results/cnipa_full_gap_diagnosis/r4b_20260930/r4b2_20261001",
    ]
    records = []
    for row in corpus.to_dict("records"):
        relative = Path(str(row["text_path"]))
        text_path = next(
            (
                candidate / relative
                for candidate in evidence_roots
                if (candidate / relative).is_file()
                and _hash(candidate / relative) == str(row["text_sha256"])
            ),
            None,
        )
        if text_path is None:
            raise FileNotFoundError(
                f"FROZEN45_EVIDENCE_TEXT_MISSING:{row['firm_key']}|{row['year']}"
            )
        text = text_path.read_text(encoding="utf-8")
        parsed = extract_annual_report_legal_name_evidence(
            text,
            expected_year=int(row["year"]),
            source_report_title="",
            source_report_year=int(row["year"]),
            source_is_official=str(row["source_is_official"]).lower() == "true",
            source_is_correct_issuer=str(row["source_is_correct_issuer"]).lower() == "true",
            source_is_correct_year=str(row["source_is_correct_year"]).lower() == "true",
            source_is_full_annual_report=str(row["source_is_full_annual_report"]).lower() == "true",
        )
        records.append((row, parsed))
    issuer = sum(
        str(r["review_legal_name_at_year_end"]) == str(p["legal_name_current_in_report"])
        for r, p in records
    )
    year_end = sum(
        str(r["review_legal_name_at_year_end"]) == str(p["legal_name_at_year_end"])
        for r, p in records
    )
    evidence = sum(str(r["review_evidence_state"]) == str(p["evidence_status"]) for r, p in records)
    prior25 = corpus.loc[
        corpus.issuer_name_correct.astype(str).str.lower().isin({"true", "1"})
        & corpus.year_end_name_correct.astype(str).str.lower().isin({"true", "1"})
        & corpus.evidence_state_correct.astype(str).str.lower().isin({"true", "1"})
    ]
    prior_regressions = 0
    for row in prior25.to_dict("records"):
        record, parsed = next(
            (r, p)
            for r, p in records
            if r["firm_key"] == row["firm_key"] and int(r["year"]) == int(row["year"])
        )
        if (
            str(row["review_legal_name_at_year_end"]) != str(parsed["legal_name_current_in_report"])
            or str(row["review_legal_name_at_year_end"]) != str(parsed["legal_name_at_year_end"])
            or str(row["review_evidence_state"]) != str(parsed["evidence_status"])
        ):
            prior_regressions += 1
    return {
        "issuer_correct": issuer,
        "year_end_correct": year_end,
        "evidence_state_correct": evidence,
        "denominator": len(corpus),
        "prior_correct25_denominator": len(prior25),
        "prior_correct25_regressions": prior_regressions,
    }


def _write_300365_diagnosis(sources: list[dict[str, object]]) -> None:
    flag_labels = (
        "公司名称在报告期内是否变更",
        "报告期内公司名称是否变更",
        "公司名称是否发生变更",
        "公司名称是否变更",
        "报告期内公司名称变更情况",
    )
    diagnosis: dict[str, object] = {
        "parser_revision": PARSER_REVISION,
        "root_cause_family": "ISSUER_SCOPE_ERROR",
        "generic_issue": (
            "A global label/definition search can confuse the issuer name with a branch "
            "name defined outside the issuer-information section. The current parser uses "
            "issuer-section scope; no issuer-specific rule was added."
        ),
        "label_matching_or_continuation_window": (
            "Not the observed cause: the issuer legal-name label and value occur on the "
            "same extracted text line within the issuer-information section."
        ),
        "reports": [],
    }
    for source in sources:
        if str(source.get("stock_code", "")) != "300365":
            continue
        text_path = Path(str(source["text_path"]))
        lines = text_path.read_text(encoding="utf-8").splitlines()
        issuer_heading = next(
            (
                i + 1
                for i, line in enumerate(lines)
                if line.strip() == "第二节 公司简介和主要财务指标"
            ),
            None,
        )
        legal_label = next(
            (
                (i + 1, line.strip())
                for i, line in enumerate(lines)
                if "公司的中文名称" in line and (issuer_heading is None or i + 1 >= issuer_heading)
            ),
            (None, ""),
        )
        branch_definition = next(
            ((i + 1, line.strip()) for i, line in enumerate(lines) if "成都分公司" in line),
            (None, ""),
        )
        found_flags = [label for label in flag_labels if any(label in line for line in lines)]
        diagnosis["reports"].append(
            {
                "year": int(source["year"]),
                "source_url": source["source_url"],
                "pdf_sha256": source["pdf_sha256"],
                "text_sha256": hashlib.sha256(text_path.read_bytes()).hexdigest(),
                "issuer_section": "第二节 公司简介和主要财务指标",
                "issuer_section_line": issuer_heading,
                "legal_name_field_label": "公司的中文名称",
                "legal_name_field_line": legal_label[0],
                "legal_name_field_text": legal_label[1],
                "change_flag_labels_found": found_flags,
                "change_flag_interpretation": (
                    "UNKNOWN is correct because no issuer-level name-change disclosure field "
                    "was found; absence is not evidence of NO."
                ),
                "branch_definition_line": branch_definition[0],
                "branch_definition_text": branch_definition[1],
                "branch_name_scope": "释义/术语定义，不是发行人法人名称字段",
            }
        )
    (OUT / "strict14_300365_root_cause_diagnosis.json").write_text(
        json.dumps(diagnosis, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def _safe_source_provenance(sources: list[dict[str, object]]) -> pd.DataFrame:
    rows = []
    for source in sources:
        row = {key: value for key, value in source.items() if key not in {"text", "pdf_bytes"}}
        pdf_path = Path(str(source.get("pdf_path", "")))
        text_path = Path(str(source.get("text_path", "")))
        row["pdf_byte_count"] = (
            pdf_path.stat().st_size if pdf_path.is_file() else int(source.get("pdf_bytes", 0) or 0)
        )
        row["text_sha256"] = (
            hashlib.sha256(text_path.read_bytes()).hexdigest() if text_path.is_file() else ""
        )
        row["text_extraction_status"] = (
            "EXTRACTED" if text_path.is_file() and text_path.stat().st_size else "FAILED"
        )
        rows.append(row)
    return pd.DataFrame(rows)


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    gt_paths = {name: LEGAL / name for name in EXPECTED_RAW_HASHES}
    for name, path in gt_paths.items():
        if _hash(path) != EXPECTED_RAW_HASHES[name]:
            raise RuntimeError(f"FROZEN_GT_RAW_HASH_MISMATCH:{name}")
    row_gt = pd.read_csv(
        gt_paths["pilot_change_row_ground_truth.csv"],
        dtype={"firm_key": str},
        keep_default_na=False,
    )
    event_gt = pd.read_csv(
        gt_paths["pilot_change_event_ground_truth.csv"],
        dtype={"firm_key": str},
        keep_default_na=False,
    )
    evidence_gt = pd.read_csv(
        gt_paths["pilot_change_evidence_state_ground_truth.csv"],
        dtype={"firm_key": str},
        keep_default_na=False,
    )
    keys, key_fingerprint = strict14_keys(row_gt, evidence_gt)
    binding = json.loads((LEGAL / "pilot_strict_gate_v3_summary.json").read_text(encoding="utf-8"))
    fingerprints = verify_ground_truth_fingerprints(row_gt, event_gt, evidence_gt, binding)
    statuses = [
        pd.read_csv(LEGAL / "pilot_status.csv", dtype={"firm_key": str}, keep_default_na=False),
        pd.read_csv(LEGAL / "full_status.csv", dtype={"firm_key": str}, keep_default_na=False),
    ]
    manifest = build_source_manifest(keys, statuses)
    pd.DataFrame(manifest).to_csv(
        OUT / "strict14_source_manifest.csv", index=False, encoding="utf-8-sig"
    )

    session = ExactURLSession({str(row["source_url"]) for row in manifest})
    existing_provenance_path = OUT / "source_provenance.csv"
    sources = []
    fetched = None
    prior_network_request_count = 0
    # Resume only from the exact artifacts created by the already completed one-GET-per-URL
    # run. Validate recorded URL, PDF hash, extracted text and identity again; never refetch.
    if existing_provenance_path.is_file():
        previous = pd.read_csv(
            existing_provenance_path, dtype={"firm_key": str}, keep_default_na=False
        )
        prev_by_key = {
            (str(row.firm_key), int(row.year)): row._asdict()
            for row in previous.itertuples(index=False)
        }
        for record in manifest:
            key = (str(record["firm_key"]), int(record["year"]))
            saved = prev_by_key.get(key)
            if not saved or str(saved.get("source_url", "")) != str(record["source_url"]):
                raise RuntimeError("SAVED_STRICT14_SOURCE_PROVENANCE_INCOMPLETE")
            pdf_path, text_path = Path(str(saved["pdf_path"])), Path(str(saved["text_path"]))
            pdf_bytes = pdf_path.read_bytes()
            text = text_path.read_text(encoding="utf-8")
            valid = hashlib.sha256(pdf_bytes).hexdigest() == str(saved["pdf_sha256"])
            check = validate_h1_document(record, pdf_bytes, text)
            if not valid or not check["valid"]:
                raise RuntimeError("SAVED_STRICT14_SOURCE_VALIDATION_FAILED")
            sources.append(
                {
                    **record,
                    **saved,
                    **check,
                    "pdf_path": str(pdf_path),
                    "text_path": str(text_path),
                    "retrieval": "NETWORK",
                }
            )
        prior_network_request_count = (
            int(previous.retrieval.astype(str).eq("NETWORK").sum())
            if "retrieval" in previous
            else len(sources)
        )
        _safe_source_provenance(sources).to_csv(
            existing_provenance_path, index=False, encoding="utf-8-sig"
        )
        fetched = {
            "local_reused_count": 0,
            "h1_get_count": len(sources),
            "source_block_count": 0,
            "stopped_reason": "",
        }
    else:
        client = CNINFOAnnualReportClient(
            OUT / "http_client_cache", request_spacing=1.2, retries=0, session=session
        )

        def fetch_one(url: str) -> dict[str, object]:
            try:
                text, metadata = client.extract_pdf_text_with_metadata(url)
                response = session.responses[-1]
                return {
                    **metadata,
                    "http_status": response.status_code,
                    "pdf_bytes": response.content,
                    "text": text,
                }
            except SourceBlocked:
                raise
            except Exception as error:
                response = session.responses[-1]
                return {
                    "http_status": response.status_code,
                    "pdf_bytes": response.content,
                    "text": "",
                    "extraction_error": f"{type(error).__name__}:{error}",
                }

        fetched = fetch_h1_sources(manifest, fetch_one, OUT / "h1_sources", max_gets=14)
        sources = fetched.pop("sources")
        prior_network_request_count = len(session.requested)
        # Persist source metadata, never duplicate full extracted text in the provenance table.
        _safe_source_provenance(sources).to_csv(
            existing_provenance_path, index=False, encoding="utf-8-sig"
        )
    if (
        fetched["stopped_reason"]
        or len(sources) != 14
        or not all(bool(row.get("valid")) for row in sources)
    ):
        failures = []
        for row in sources:
            if not row.get("valid"):
                failures.append(
                    {
                        "firm_key": row.get("firm_key"),
                        "year": row.get("year"),
                        "metric": "H1_SOURCE",
                        "failure_family": row.get(
                            "reason", row.get("extraction_error", "INVALID_H1")
                        ),
                        "source_evidence_available": True,
                        "diagnosis": "Exact official source failed H1 validation; replay stopped.",
                    }
                )
        pd.DataFrame(failures).to_csv(
            OUT / "strict14_v3_failures.csv", index=False, encoding="utf-8-sig"
        )
        _json(
            OUT / "strict14_v3_summary.json",
            {
                "status": "H1_SOURCE_VALIDATION_FAILED",
                "parser_revision": PARSER_REVISION,
                "strict14_count": len(keys),
                "strict14_key_fingerprint": key_fingerprint,
                **fetched,
                "network_request_count": len(session.requested),
                "h2_request_count": 0,
            },
        )
        return 0

    _write_300365_diagnosis(sources)
    parsed_rows = []
    for source in sources:
        text = Path(str(source["text_path"])).read_text(encoding="utf-8")
        parsed = extract_annual_report_legal_name_evidence(
            text,
            expected_year=int(source["year"]),
            source_report_title=str(source["source_report_title"]),
            source_report_year=int(source["year"]),
            source_is_official=True,
            source_is_correct_issuer=True,
            source_is_correct_year=True,
            source_is_full_annual_report=True,
        )
        has_change = bool(
            parsed["company_name_change_flag"] == "YES"
            or parsed["legal_name_previous"]
            or parsed["legal_name_new"]
        )
        parsed_rows.append(
            {
                "firm_key": source["firm_key"],
                "year": int(source["year"]),
                "source_url": source["source_url"],
                "source_announcement_id": source.get("source_announcement_id", ""),
                **{f"parser_{key}": value for key, value in parsed.items()},
                "parser_change_flag": parsed["company_name_change_flag"],
                "change_evidence_tier": "H1" if has_change else "",
                "change_evidence_url": source["source_url"] if has_change else "",
                "change_evidence_source": "verified_exact_h1" if has_change else "",
                "change_announcement_id": source.get("source_announcement_id", "")
                if has_change
                else "",
            }
        )
    complete = build_complete_row_predictions(keys, pd.DataFrame(parsed_rows))
    complete.to_csv(OUT / "strict14_v3_row_predictions.csv", index=False, encoding="utf-8-sig")
    complete.to_csv(OUT / "strict14_v3_predictions.csv", index=False, encoding="utf-8-sig")

    def is_candidate(row: pd.Series) -> bool:
        item = row.to_dict()
        item.update(
            {
                "company_name_change_flag": item.get("parser_company_name_change_flag", ""),
                "legal_name_previous": item.get("parser_legal_name_previous", ""),
                "legal_name_new": item.get("parser_legal_name_new", ""),
                "evidence_status": item.get("parser_evidence_status", ""),
                "failure_reason": item.get("parser_failure_reason", ""),
                "evidence_context": item.get("parser_evidence_context", ""),
            }
        )
        return is_change_related_candidate(item)

    candidate_mask = complete.apply(is_candidate, axis=1)
    candidates = complete.loc[candidate_mask].copy()
    h2_audit = pd.read_csv(
        LEGAL / "pilot_name_change_h2_audit.csv", dtype={"firm_key": str}, keep_default_na=False
    )
    event_roster, h2_carry, row_event_mapping = _event_records(candidates, h2_audit)
    candidates["parser_event_id"] = [
        row_event_mapping.get(f"{row.firm_key}|{int(row.year)}", "")
        for row in candidates.itertuples(index=False)
    ]
    candidates.to_csv(OUT / "strict14_v3_candidate_rows.csv", index=False, encoding="utf-8-sig")
    event_roster.to_csv(OUT / "strict14_v3_event_roster.csv", index=False, encoding="utf-8-sig")
    row_scores = score_strict_rows(complete, row_gt, evidence_gt)
    mapped_event_status = (
        event_roster.set_index("event_id").event_verification_status.to_dict()
        if not event_roster.empty and "event_verification_status" in event_roster
        else {}
    )
    row_scores["unresolved_candidate_count"] = int(
        sum(
            not mapped_event_status.get(event_id, "") == "VERIFIED"
            for event_id in candidates.parser_event_id
        )
    )
    # Event IDs are regenerated from current predictions, so compare independently by issuer key.
    event_predictions = event_roster.rename(
        columns={
            "parser_previous_legal_name": "parser_previous_legal_name",
            "parser_new_legal_name": "parser_new_legal_name",
            "parser_effective_date": "parser_effective_date",
            "parser_date_precision": "parser_date_precision",
        }
    )
    event_scores = score_events(event_predictions, event_gt)
    frozen45 = _run_frozen45()
    h2_gt = event_gt.loc[
        event_gt.source_evidence_tier.astype(str).str.contains("H2", case=False)
    ].copy()
    carried_h2_keys = (
        set(zip(h2_carry.firm_key.astype(str), h2_carry.year.astype(int)))
        if not h2_carry.empty
        else set()
    )
    h2_gt["_event_year"] = pd.to_numeric(
        h2_gt.review_effective_date.astype(str).str[:4], errors="coerce"
    )
    unresolved_h2 = h2_gt.loc[
        [
            (str(row["firm_key"]), int(row["_event_year"])) not in carried_h2_keys
            if pd.notna(row["_event_year"])
            else True
            for _, row in h2_gt.iterrows()
        ]
    ]
    summary = {
        "parser_revision": PARSER_REVISION,
        "strict14_count": len(keys),
        "strict14_key_fingerprint": key_fingerprint,
        "source_local_reused": fetched["local_reused_count"],
        "source_reacquired": fetched["h1_get_count"],
        "h1_get_count": fetched["h1_get_count"],
        "invalid_h1_count": 0,
        "source_block_count": fetched["source_block_count"],
        "h2_request_count": 0,
        "h2_valid_carry_count": len(h2_carry),
        "h2_replay_evidence_unavailable_event_count": len(unresolved_h2),
        "candidate_rows": len(candidates),
        "row_evaluation_denominator": 14,
        **row_scores,
        **event_scores,
        "strict_gate_status": "STRICT_PILOT_GATE_PASS"
        if (
            row_scores["evidence_state_correct"] == 14
            and row_scores["year_end_correct"] == 14
            and all(
                event_scores[key] == 1.0
                for key in (
                    "event_old_accuracy",
                    "event_new_accuracy",
                    "event_date_accuracy",
                    "event_date_precision_accuracy",
                )
            )
            and row_scores["unresolved_candidate_count"] == 0
            and event_scores["unresolved_event_count"] == 0
            and len(h2_carry) >= len(unresolved_h2)
            and len(sources) == 14
        )
        else "STRICT_PILOT_GATE_NEEDS_FIX",
        "ground_truth_fingerprints": fingerprints,
        "ground_truth_raw_hashes": EXPECTED_RAW_HASHES,
        "ground_truth_unchanged": True,
        "full_data_changed": False,
        "network_request_count": prior_network_request_count,
        "h2_network_request_count": 0,
        "patent_system_accessed": False,
        "frozen45": frozen45,
    }
    _json(OUT / "strict14_v3_summary.json", summary)
    if (
        summary["strict_gate_status"] != "STRICT_PILOT_GATE_PASS"
        or frozen45["denominator"] != 45
        or any(
            frozen45[k] != 45
            for k in ("issuer_correct", "year_end_correct", "evidence_state_correct")
        )
        or frozen45["prior_correct25_regressions"]
    ):
        failures = []
        for _, row in complete.iterrows():
            truth = row_gt.loc[
                (row_gt.firm_key == row.firm_key) & (row_gt.year.astype(int) == int(row.year))
            ]
            truth = truth.iloc[0]
            evidence_truth = evidence_gt.loc[
                (evidence_gt.firm_key == row.firm_key)
                & (evidence_gt.year.astype(int) == int(row.year))
            ].iloc[0]
            if row.get("parser_change_flag") != evidence_truth.review_expected_parser_flag:
                failures.append(
                    {
                        "firm_key": row.firm_key,
                        "year": int(row.year),
                        "metric": "evidence_state",
                        "v2_historical_value": "",
                        "v3_value": row.get("parser_change_flag"),
                        "review_value": evidence_truth.review_expected_parser_flag,
                        "failure_family": "PARSER_EVIDENCE_STATE_MISMATCH",
                        "source_evidence_available": True,
                        "diagnosis": (
                            "Current parser output disagrees with frozen evidence-state review."
                        ),
                    }
                )
            if str(row.get("parser_legal_name_at_year_end", "")) != str(
                truth.review_legal_name_at_year_end
            ):
                failures.append(
                    {
                        "firm_key": row.firm_key,
                        "year": int(row.year),
                        "metric": "year_end_legal_name",
                        "v2_historical_value": "",
                        "v3_value": row.get("parser_legal_name_at_year_end"),
                        "review_value": truth.review_legal_name_at_year_end,
                        "failure_family": "YEAR_END_NAME_MISMATCH",
                        "source_evidence_available": True,
                        "diagnosis": "Current parser output disagrees with frozen year-end review.",
                    }
                )
        # Event-level audit uses the six frozen events only after prediction roster creation.
        pred_events = event_roster.copy()
        if not pred_events.empty:
            pred_events["_score_year"] = (
                pred_events.parser_effective_date.fillna("").astype(str).str[:4]
            )
            fallback = (
                pd.to_numeric(
                    pred_events.get("year", pd.Series(index=pred_events.index, dtype=float)),
                    errors="coerce",
                )
                .astype("Int64")
                .astype(str)
                .replace("<NA>", "")
            )
            pred_events.loc[pred_events._score_year.isin({"", "nan", "None"}), "_score_year"] = (
                fallback.loc[pred_events._score_year.isin({"", "nan", "None"})]
            )
        carried_keys = (
            set(
                zip(
                    h2_carry.firm_key.astype(str),
                    pd.to_numeric(h2_carry.year, errors="coerce").astype("Int64"),
                )
            )
            if not h2_carry.empty
            else set()
        )
        for _, event in event_gt.iterrows():
            event_year = str(event.review_effective_date)[:4]
            match = (
                pred_events.loc[
                    pred_events.firm_key.astype(str).eq(str(event.firm_key))
                    & pred_events._score_year.astype(str).eq(event_year)
                ]
                if not pred_events.empty
                else pd.DataFrame()
            )
            if match.empty:
                is_h2_unavailable = (
                    str(event.source_evidence_tier).upper() == "H2"
                    and (str(event.firm_key), int(event_year)) not in carried_keys
                )
                failures.append(
                    {
                        "firm_key": event.firm_key,
                        "year": event_year,
                        "metric": "event_roster",
                        "v2_historical_value": "",
                        "v3_value": "",
                        "review_value": "",
                        "failure_family": "H2_REPLAY_EVIDENCE_UNAVAILABLE"
                        if is_h2_unavailable
                        else "EVENT_PREDICTION_UNRESOLVED",
                        "source_evidence_available": not is_h2_unavailable,
                        "diagnosis": (
                            "No current-v3 prediction event matched the frozen event identity key."
                        ),
                    }
                )
                continue
            prediction = match.iloc[0]
            for metric, pred_col, review_col in (
                ("event_old_name", "parser_previous_legal_name", "review_previous_legal_name"),
                ("event_new_name", "parser_new_legal_name", "review_new_legal_name"),
                ("event_effective_date", "parser_effective_date", "review_effective_date"),
                ("event_date_precision", "parser_date_precision", "review_date_precision"),
            ):
                predicted_value = str(prediction.get(pred_col, "") or "")
                reviewed_value = str(event.get(review_col, "") or "")
                if predicted_value.strip() != reviewed_value.strip():
                    failures.append(
                        {
                            "firm_key": event.firm_key,
                            "year": event_year,
                            "metric": metric,
                            "v2_historical_value": "",
                            "v3_value": predicted_value,
                            "review_value": reviewed_value,
                            "failure_family": "EVENT_FIELD_MISMATCH",
                            "source_evidence_available": True,
                            "diagnosis": (
                                "Current-v3 event field disagrees with frozen "
                                "independent event review."
                            ),
                        }
                    )
        pd.DataFrame(failures).to_csv(
            OUT / "strict14_v3_failures.csv", index=False, encoding="utf-8-sig"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
