"""Request and bounded-index audit primitives for the R4B2 diagnostic epoch."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

R4B_HISTORICAL_GUARDED_ATTEMPTS = 120
R4B2_ADDITIONAL_GUARDED_ATTEMPT_CAP = 120
MAX_INDEX_PAGES_PER_FIRM_YEAR = 4
R4B2_MANIFEST_SHA256 = "30C47523292A96F19EDF889ACDD0851B26887B08D60B91F06E14EF2D9420F78C"
R4B2_FRAME_FINGERPRINT = "8e26547eda6d24ff78af39e8bf652128809d57b67414655495fba50b130bc2fb"
R4B2_KEY_FINGERPRINT = "96D4FF6735B18707129CE2C4F485F0D22C3547F28A0A9DAF1C164330F4757861"


def validate_r4b2_offline_gate(summary, mapping, source_reviews, content_reviews) -> bool:
    """Fail closed unless the frozen offline evidence/review gate is complete."""
    expected_counts = {
        "VALID_FULL_H1": 27,
        "ANNUAL_REPORT_SUMMARY": 2,
        "WRONG_ISSUER": 1,
    }
    action_field = (
        "planned_action"
        if "planned_action" in source_reviews.columns
        else "acquisition_action"
        if "acquisition_action" in source_reviews.columns
        else None
    )
    actions = source_reviews[action_field] if action_field else []
    checks = (
        str(summary.get("manifest_sha256", "")).upper() == R4B2_MANIFEST_SHA256,
        str(summary.get("frame_fingerprint", "")).lower() == R4B2_FRAME_FINGERPRINT,
        str(summary.get("key_fingerprint", "")).upper() == R4B2_KEY_FINGERPRINT,
        int(summary.get("offline_network_requests", -1)) == 0,
        int(summary.get("r4b2_guarded_attempts", -1)) == 0,
        int(summary.get("mapped_to_frozen_keys", -1)) == 30,
        int(summary.get("mapping_unresolved", -1)) == 0,
        int(summary.get("valid_full_h1_count", -1)) == 27,
        all(
            int(summary.get("source_identity_distribution", {}).get(key, 0))
            == expected_counts.get(key, 0)
            for key in (
                "VALID_FULL_H1",
                "ANNUAL_REPORT_SUMMARY",
                "WRONG_ISSUER",
                "WRONG_YEAR",
                "NON_ANNUAL_REPORT",
                "SOURCE_IDENTITY_UNRESOLVED",
            )
        ),
        len(mapping) == 30
        and mapping.mapping_status.eq("MAPPED_TO_FROZEN_KEY").all(),
        len(source_reviews) == 30
        and source_reviews.classification.value_counts().to_dict()
        == expected_counts,
        len(content_reviews) == 27
        and content_reviews.review_status_review.eq("PASS").all(),
        not any("H2" in str(action).upper() for action in actions),
    )
    if not all(checks):
        raise ValueError("R4B2_OFFLINE_GATE_FAILED")
    return True


def build_provenance_mapping(
    predictions, frozen_manifest, evidence_root: Path
) -> list[dict[str, object]]:
    """Map acquired evidence from its recorded key/path/hash, never parsed names."""
    required_prediction_fields = {
        "firm_key",
        "year",
        "_evidence_path",
        "pdf_sha256",
    }
    if missing := required_prediction_fields.difference(predictions.columns):
        raise ValueError(f"MAPPING_UNRESOLVED:MISSING_COLUMNS:{sorted(missing)}")
    if not {"firm_key", "year"}.issubset(frozen_manifest.columns):
        raise ValueError("MAPPING_UNRESOLVED:FROZEN_MANIFEST_KEY_COLUMNS_MISSING")

    frozen_keys = {
        (str(row.firm_key), str(row.year))
        for row in frozen_manifest[["firm_key", "year"]].itertuples(index=False)
    }
    evidence_root = Path(evidence_root).resolve()
    rows: list[dict[str, object]] = []
    seen_keys: set[tuple[str, str]] = set()
    acquired = predictions.loc[predictions["pdf_sha256"].astype(str).ne("")]
    for record in acquired.to_dict(orient="records"):
        firm_key, year = str(record["firm_key"]), str(record["year"])
        key = (firm_key, year)
        relative_path = str(record.get("_evidence_path", "")).strip()
        expected_pdf_hash = str(record.get("pdf_sha256", "")).strip().lower()
        if key not in frozen_keys:
            raise ValueError(f"MAPPING_UNRESOLVED:KEY_OUTSIDE_FROZEN_MANIFEST:{firm_key}|{year}")
        if key in seen_keys:
            raise ValueError(f"MAPPING_UNRESOLVED:DUPLICATE_ACQUISITION_KEY:{firm_key}|{year}")
        if not relative_path or not expected_pdf_hash:
            raise ValueError(f"MAPPING_UNRESOLVED:MISSING_PATH_OR_HASH:{firm_key}|{year}")
        pdf_path = (evidence_root / relative_path).resolve()
        if not pdf_path.is_relative_to(evidence_root) or not pdf_path.is_file():
            raise ValueError(f"MAPPING_UNRESOLVED:EVIDENCE_PATH_INVALID:{firm_key}|{year}")
        text_path = pdf_path.with_suffix(".txt")
        if not text_path.is_file():
            raise ValueError(f"MAPPING_UNRESOLVED:TEXT_MISSING:{firm_key}|{year}")
        actual_pdf_hash = hashlib.sha256(pdf_path.read_bytes()).hexdigest()
        if actual_pdf_hash != expected_pdf_hash:
            raise ValueError(f"MAPPING_UNRESOLVED:PDF_HASH_MISMATCH:{firm_key}|{year}")
        seen_keys.add(key)
        rows.append(
            {
                "firm_key": firm_key,
                "year": year,
                "frozen_manifest_key": f"{firm_key}|{year}",
                "evidence_relative_path": relative_path.replace("\\", "/"),
                "pdf_sha256": actual_pdf_hash,
                "text_sha256": hashlib.sha256(text_path.read_bytes()).hexdigest(),
                "source_url_requested": str(record.get("source_url_requested", "")),
                "source_url_final": str(record.get("source_url_final", "")),
                "source_title": str(record.get("source_title", "")),
                "source_announcement_id": str(record.get("source_announcement_id", "")),
                "planned_action": str(record.get("planned_action", "")),
                "acquisition_action": str(record.get("acquisition_action", "")),
                "old_r4b_http_status": str(record.get("http_status", "")),
                "mapping_source": "pilot_predictions_key_path_hash",
                "mapping_status": "MAPPED_TO_FROZEN_KEY",
                "mapping_notes": (
                    "Direct acquisition-row key and persisted path/hash; "
                    "parser output not used."
                ),
            }
        )
    return rows


def classify_source_identity(
    *,
    official: bool,
    correct_issuer: bool,
    correct_year: bool,
    full_annual_report: bool,
    source_title: str,
    source_text: str = "",
) -> str:
    """Assign one source class from independent source-review facts."""
    if not official:
        return "SOURCE_IDENTITY_UNRESOLVED"
    if not correct_issuer:
        return "WRONG_ISSUER"
    if not correct_year:
        return "WRONG_YEAR"
    if not full_annual_report:
        evidence_label = f"{source_title} {source_text}"
        if "摘要" in evidence_label:
            return "ANNUAL_REPORT_SUMMARY"
        if "年度报告" not in evidence_label:
            return "NON_ANNUAL_REPORT"
        return "SOURCE_IDENTITY_UNRESOLVED"
    return "VALID_FULL_H1"


def cumulative_guarded_attempts(r4b_attempts: int, r4b2_attempts: int) -> int:
    if int(r4b_attempts) != R4B_HISTORICAL_GUARDED_ATTEMPTS:
        raise ValueError("R4B_HISTORICAL_ATTEMPTS_MUST_REMAIN_IMMUTABLE")
    if not 0 <= int(r4b2_attempts) <= R4B2_ADDITIONAL_GUARDED_ATTEMPT_CAP:
        raise ValueError("R4B2_ATTEMPT_CAP_EXCEEDED")
    return int(r4b_attempts) + int(r4b2_attempts)


def classify_index_result(
    pages_requested: int,
    api_total_pages: int,
    valid_candidate_count: int,
    *,
    page_cap: int = MAX_INDEX_PAGES_PER_FIRM_YEAR,
) -> str:
    if pages_requested < 0 or api_total_pages < 0 or valid_candidate_count < 0:
        raise ValueError("INDEX_AUDIT_COUNTS_MUST_BE_NONNEGATIVE")
    if valid_candidate_count:
        return "INDEX_VALID_REPORT_FOUND"
    if api_total_pages <= pages_requested:
        return "INDEX_COMPLETE_RESULT_SET_NO_VALID_REPORT"
    if pages_requested >= page_cap:
        return "INDEX_PAGE_CAP_REACHED_UNRESOLVED"
    return "INDEX_LOOKUP_INCOMPLETE"


def _safe_endpoint(url: str) -> tuple[str, str]:
    parsed = urlsplit(str(url))
    host = parsed.hostname or ""
    pairs = parse_qsl(parsed.query, keep_blank_values=True)
    sensitive_tokens = ("token", "password", "cookie", "secret")
    safe_pairs = [
        (
            key,
            "[REDACTED]"
            if any(token in key.lower() for token in sensitive_tokens)
            else value,
        )
        for key, value in pairs
    ]
    endpoint = urlunsplit((parsed.scheme, host, parsed.path, urlencode(safe_pairs), ""))
    return host, endpoint


class RequestAuditLog:
    """Append a single terminal JSONL record for each guarded transport attempt."""

    def __init__(self, path: Path, *, epoch: str = "R4B2") -> None:
        self.path = Path(path)
        self.epoch = epoch

    def record(
        self,
        *,
        sequence: int,
        firm_key: str,
        year: int,
        action: str,
        method: str,
        url: str,
        index_page: int | None = None,
        attempt_started_at: str,
        transport_called: bool,
        response_received: bool,
        http_status: int | None,
        exception_type: str,
        exception_message_short: str,
        source_blocked: bool,
        budget_consumed: bool,
    ) -> dict[str, object]:
        host, endpoint = _safe_endpoint(url)
        if response_received:
            terminal = "HTTP_RESPONSE"
        elif transport_called:
            terminal = "TRANSPORT_EXCEPTION"
        else:
            terminal = "PRE_DISPATCH_OR_LOCAL_ERROR"
        row: dict[str, object] = {
            "epoch": self.epoch,
            "sequence": int(sequence),
            "firm_key": str(firm_key),
            "year": int(year),
            "action": str(action),
            "method": str(method).upper(),
            "host": host,
            "index_page": index_page,
            "endpoint_or_url": endpoint,
            "attempt_started_at": str(attempt_started_at),
            "transport_called": bool(transport_called),
            "response_received": bool(response_received),
            "http_status": http_status,
            "exception_type": str(exception_type),
            "exception_message_short": str(exception_message_short)[:240],
            "source_blocked": bool(source_blocked),
            "budget_consumed": bool(budget_consumed),
            "terminal_outcome": terminal,
            "recorded_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8", newline="\n") as stream:
            stream.write(json.dumps(row, ensure_ascii=False, allow_nan=False) + "\n")
            stream.flush()
        return row
