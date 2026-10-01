"""Bounded offline/online diagnostic runner for the frozen R4A Pilot."""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import subprocess
import time
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import pandas as pd
import requests

from scripts import diagnose_cnipa_full_gaps_20260930 as r4a
from scripts import run_cninfo_legal_name_recovery_20260929 as canonical
from src.cnipa_annual_report_names import PARSER_REVISION as CURRENT_PARSER_REVISION
from src.cnipa_annual_report_names import extract_annual_report_legal_name_evidence
from src.cnipa_r4b2_audit import (
    MAX_INDEX_PAGES_PER_FIRM_YEAR,
    RequestAuditLog,
    classify_index_result,
    validate_r4b2_offline_gate,
)
from src.historical_province_sources import (
    CNINFO_ANNOUNCEMENT_QUERY_URL,
    CNINFO_STATIC_BASE_URL,
    CNINFOAnnualReportClient,
    SourceBlocked,
    match_annual_report_title,
)

ROOT = Path(__file__).resolve().parents[1]
DIAGNOSIS_DIR = ROOT / "results/cnipa_full_gap_diagnosis"
MANIFEST_PATH = DIAGNOSIS_DIR / "diagnostic_pilot_manifest.csv"
GAP_ROSTER_PATH = DIAGNOSIS_DIR / "full_gap_roster.csv"
STALE_ROSTER_PATH = DIAGNOSIS_DIR / "stale_success_risk.csv"
R4A_SUMMARY_PATH = DIAGNOSIS_DIR / "diagnosis_summary.json"
RUN_DIR = DIAGNOSIS_DIR / "r4b_20260930"
R4B2_RUN_DIR = RUN_DIR / "r4b2_20261001"
UNIVERSE_PATH = ROOT / "data/processed/real_company_universe_enriched.parquet"
TARGET_MANIFEST_PATH = ROOT / "results/real_financial_full/target_manifest.csv"
AUDIT_PATH = ROOT / "results/cnipa_preflight/entity_name_audit.csv"
FULL_DIR = ROOT / "results/cnipa_legal_name_recovery"
FULL_CACHE_DIR = FULL_DIR / "cache"
FULL_STATUS_PATH = FULL_DIR / "full_status.csv"
FULL_STATE_PATH = FULL_DIR / "full_run_state.json"
ENTITY_COVERAGE_PATH = ROOT / "results/cnipa_preflight/entity_year_name_coverage.csv"
EXPECTED_MANIFEST_SHA256 = "30C47523292A96F19EDF889ACDD0851B26887B08D60B91F06E14EF2D9420F78C"
EXPECTED_FRAME_FINGERPRINT = "8e26547eda6d24ff78af39e8bf652128809d57b67414655495fba50b130bc2fb"
EXPECTED_KEY_FINGERPRINT = "96D4FF6735B18707129CE2C4F485F0D22C3547F28A0A9DAF1C164330F4757861"
CHECKPOINT_PATH = RUN_DIR / "checkpoint.json"
ALLOWED_HOSTS = {"static.cninfo.com.cn", "www.cninfo.com.cn", "cninfo.com.cn"}
REVIEW_FIELDS = (
    "review_legal_name_at_year_end",
    "review_change_evidence_state",
    "review_previous_name",
    "review_new_name",
    "review_effective_date",
    "review_date_precision",
    "source_is_official",
    "source_is_correct_issuer",
    "source_is_correct_year",
    "source_is_full_annual_report",
    "reviewer_evidence_excerpt",
    "review_notes",
)


class RequestCapReached(RuntimeError):
    """The run reached its hard HTTP request ceiling."""


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _allowed_cninfo_url(url: str) -> bool:
    parsed = urlparse(str(url))
    return parsed.scheme == "https" and parsed.hostname in ALLOWED_HOSTS


def plan_acquisition_action(
    action: str, source_url: str, content_persisted: bool
) -> dict[str, str]:
    url = str(source_url or "").strip()
    if action == "REFETCH_EXACT_H1_URL":
        if not _allowed_cninfo_url(url):
            raise ValueError("ACTION_SCOPE_VIOLATION")
        return {"mode": "EXACT_H1", "url": url}
    if action == "TARGETED_CNINFO_INDEX_LOOKUP":
        return {"mode": "INDEX_LOOKUP", "url": ""}
    if action == "MANUAL_SOURCE_REVIEW":
        if url and not content_persisted:
            if not _allowed_cninfo_url(url):
                raise ValueError("ACTION_SCOPE_VIOLATION")
            return {"mode": "EXACT_H1_FOR_MANUAL_REVIEW", "url": url}
        return {"mode": "LOCAL_ONLY", "url": ""}
    if action == "NO_NETWORK_NEGATIVE_CONTROL":
        return {"mode": "LOCAL_ONLY", "url": ""}
    raise ValueError("ACTION_SCOPE_VIOLATION")


def validate_index_candidate(
    candidate: dict[str, Any], *, stock_code: str, report_year: int
) -> bool:
    candidate_code = str(candidate.get("stock_code", "")).strip().zfill(6)
    title = str(candidate.get("title", ""))
    return bool(
        candidate_code == str(stock_code).strip().zfill(6)
        and int(candidate.get("report_year", -1)) == int(report_year)
        and match_annual_report_title(title) == int(report_year)
        and str(candidate.get("announcement_id", "")).strip()
        and str(candidate.get("source_type", "")) == "official_annual_report"
        and str(candidate.get("source_tier", "")) == "H1"
        and _allowed_cninfo_url(str(candidate.get("source_url", "")))
    )


class RequestGuard:
    """Persisted serial request budget, rate limit, allowlist, and source-block stop."""

    def __init__(
        self,
        *,
        state: dict[str, Any],
        persist,
        min_interval: float = 1.0,
        max_requests: int = 120,
        clock=time.time,
        monotonic=None,
        sleep=time.sleep,
        audit_log: RequestAuditLog | None = None,
        counter_key: str = "request_count",
    ) -> None:
        if min_interval < 1.0 or max_requests > 120 or max_requests < 1:
            raise ValueError("INVALID_REQUEST_GUARD_LIMITS")
        self.state = state
        self.persist = persist
        self.min_interval = min_interval
        self.max_requests = max_requests
        self.clock = monotonic or clock
        self.sleep = sleep
        self.audit_log = audit_log
        self.counter_key = counter_key

    def perform(self, transport, method: str, url: str, *, audit_context=None, **kwargs):
        if not _allowed_cninfo_url(url):
            raise ValueError("NETWORK_HOST_NOT_ALLOWED")
        if self.state.get("source_blocked"):
            raise SourceBlocked("SOURCE_BLOCKED_STOP_IS_ACTIVE")
        if int(self.state.get(self.counter_key, 0)) >= self.max_requests:
            self.state["stop_reason"] = "REQUEST_CAP_REACHED"
            self.persist()
            raise RequestCapReached("HTTP_REQUEST_HARD_CAP_REACHED")
        last_request = self.state.get("last_request_at")
        if last_request is not None:
            delay = self.min_interval - (self.clock() - float(last_request))
            if delay > 0:
                self.sleep(delay)
        attempt_number = int(self.state.get(self.counter_key, 0)) + 1
        self.state[self.counter_key] = attempt_number
        self.state["last_request_at"] = self.clock()
        self.state["pending_request"] = {"method": method.upper(), "url": url}
        if self.counter_key == "request_count":
            self.state.setdefault("request_history", []).append(
                {"attempt": attempt_number, "method": method.upper(), "url": url}
            )
        started_at = datetime.now().astimezone().isoformat(timespec="seconds")
        self.persist()
        try:
            response = transport(method, url, **kwargs)
        except Exception as exc:
            self.state["pending_request"] = None
            pre_dispatch_error = isinstance(exc, TypeError) and (
                "multiple values for keyword argument" in str(exc)
            )
            if pre_dispatch_error:
                self.state["pre_dispatch_or_local_error_count"] = int(
                    self.state.get("pre_dispatch_or_local_error_count", 0)
                ) + 1
            else:
                self.state["request_outcome_unknown"] = True
                self.state["transport_exception_count"] = int(
                    self.state.get("transport_exception_count", 0)
                ) + 1
            self._audit_attempt(
                audit_context, attempt_number, method, url, started_at,
                transport_called=not pre_dispatch_error, response_received=False, http_status=None,
                exception_type=type(exc).__name__, exception_message_short=str(exc),
                source_blocked=False,
            )
            self.persist()
            raise
        self.state["response_received_count"] = int(
            self.state.get("response_received_count", 0)
        ) + 1
        status = int(response.status_code)
        content = getattr(response, "content", b"")
        is_pdf = bytes(content[:5]) == b"%PDF-"
        body = "" if is_pdf else str(getattr(response, "text", ""))[:10000].lower()
        challenge = any(
            token in body
            for token in (
                "验证码",
                "图形验证",
                "请完成验证",
                "访问验证",
                "安全验证",
                "captcha",
                "login required",
                "请登录",
                "登录后查看",
                "访问受限",
                "请求过于频繁",
            )
        )
        self.state["pending_request"] = None
        if status in {401, 403, 429} or challenge:
            self.state["source_block_count"] = int(
                self.state.get("source_block_count", 0)
            ) + 1
            self.state.update(
                source_blocked=True,
                stop_reason="SOURCE_BLOCKED",
                blocked_url=url,
                blocked_domain=urlparse(url).hostname,
                blocked_http_status=status,
            )
            self._audit_attempt(
                audit_context, attempt_number, method, url, started_at,
                transport_called=True, response_received=True, http_status=status,
                exception_type="", exception_message_short="", source_blocked=True,
            )
            self.persist()
            raise SourceBlocked(f"HTTP_{status}" if status in {401, 403, 429} else "CHALLENGE")
        self.state["last_http_status"] = status
        if self.counter_key == "request_count":
            self.state["request_history"][-1]["http_status"] = status
        self._audit_attempt(
            audit_context, attempt_number, method, url, started_at,
            transport_called=True, response_received=True, http_status=status,
            exception_type="", exception_message_short="", source_blocked=False,
        )
        self.persist()
        return response

    def _audit_attempt(
        self, context, sequence, method, url, started_at, *, transport_called,
        response_received, http_status, exception_type, exception_message_short,
        source_blocked,
    ) -> None:
        if self.audit_log is None:
            return
        context = context or {}
        self.audit_log.record(
            sequence=sequence,
            firm_key=context.get("firm_key", ""),
            year=context.get("year", 0),
            action=context.get("action", ""),
            method=method,
            url=url,
            attempt_started_at=started_at,
            transport_called=transport_called,
            response_received=response_received,
            http_status=http_status,
            exception_type=exception_type,
            exception_message_short=exception_message_short,
            source_blocked=source_blocked,
            index_page=context.get("index_page"),
            budget_consumed=True,
        )


def verify_resume_fingerprints(checkpoint: dict[str, Any], manifest_fingerprint: str) -> None:
    if checkpoint.get("manifest_fingerprint") != manifest_fingerprint:
        raise ValueError("RESUME_MANIFEST_FINGERPRINT_MISMATCH")


def should_skip_completed_row(
    result: dict[str, Any], manifest_fingerprint: str, evidence_root
) -> bool:
    if not result.get("completed") or result.get("manifest_fingerprint") != manifest_fingerprint:
        return False
    evidence_path = str(result.get("evidence_path", ""))
    expected_hash = str(result.get("evidence_sha256", ""))
    if not evidence_path or not expected_hash:
        return bool(result.get("terminal_without_evidence"))
    path = (evidence_root / evidence_path).resolve()
    root = evidence_root.resolve()
    if root not in path.parents or not path.is_file():
        return False
    return sha256_bytes(path.read_bytes()) == expected_hash


def build_review_template(predictions: pd.DataFrame) -> pd.DataFrame:
    template = predictions[["firm_key", "year"]].copy()
    for column in REVIEW_FIELDS:
        template[column] = ""
    template["review_status"] = "PENDING"
    return template


def load_or_create_independent_review(predictions: pd.DataFrame, review_path: Path) -> pd.DataFrame:
    if not review_path.is_file():
        return build_review_template(predictions)
    reviews = pd.read_csv(review_path, dtype=str, keep_default_na=False)
    keys = ["firm_key", "year"]
    if reviews.duplicated(keys).any() or predictions.duplicated(keys).any():
        raise ValueError("DUPLICATE_INDEPENDENT_REVIEW_KEY")
    predicted_keys = set(zip(predictions.firm_key.astype(str), predictions.year.astype(str)))
    review_keys = set(zip(reviews.firm_key.astype(str), reviews.year.astype(str)))
    if review_keys != predicted_keys:
        raise ValueError("INDEPENDENT_REVIEW_KEY_SET_MISMATCH")
    return reviews


def calculate_source_grounded_metrics(
    predictions: pd.DataFrame, reviews: pd.DataFrame
) -> dict[str, Any]:
    prediction_review_fields = [
        column
        for column in predictions.columns
        if column.startswith("review_") or column.startswith("source_is_")
    ]
    predictions = predictions.drop(columns=prediction_review_fields, errors="ignore")
    merged = predictions.merge(
        reviews, on=["firm_key", "year"], how="outer", validate="one_to_one", indicator=True
    )
    if not merged._merge.eq("both").all():
        raise ValueError("PREDICTION_REVIEW_KEY_SET_MISMATCH")
    source_valid = (
        merged.review_status.eq("PASS")
        & merged.source_is_official.map(_bool)
        & merged.source_is_correct_issuer.map(_bool)
        & merged.source_is_correct_year.map(_bool)
        & merged.source_is_full_annual_report.map(_bool)
    )
    excluded = {
        status: int(merged.review_status.eq(status).sum())
        for status in ("LOCAL_CONTROL_ONLY", "SOURCE_UNRESOLVED", "SOURCE_BLOCKED")
    }
    excluded["OTHER_OR_PENDING"] = int((~source_valid & ~merged.review_status.isin(excluded)).sum())
    denominator = merged.loc[source_valid]

    def accuracy(left: str, right: str) -> float | None:
        if denominator.empty:
            return None
        return float(
            denominator[left]
            .fillna("")
            .astype(str)
            .eq(denominator[right].fillna("").astype(str))
            .mean()
        )

    return {
        "review_denominator": len(denominator),
        "parser_issuer_name_accuracy": accuracy(
            "parser_legal_name_current", "review_legal_name_at_year_end"
        ),
        "parser_year_end_name_accuracy": accuracy(
            "parser_legal_name_at_year_end", "review_legal_name_at_year_end"
        ),
        "parser_evidence_state_accuracy": accuracy(
            "parser_evidence_status", "review_change_evidence_state"
        ),
        "excluded_counts": excluded,
    }


def classify_diagnostic_outcome(row: dict[str, Any]) -> str:
    if row.get("review_status") != "PASS":
        return "UNRESOLVED"
    if not all(
        row.get(field) is True
        for field in (
            "source_is_official",
            "source_is_correct_issuer",
            "source_is_correct_year",
            "source_is_full_annual_report",
        )
    ):
        return "SOURCE_IDENTITY_PROBLEM"
    if row.get("next_action") == "TARGETED_H2_REQUIRED":
        return "TEMPORAL_EVIDENCE_REQUIRED"
    parser_matches = str(row.get("parser_legal_name_at_year_end", "")) == str(
        row.get("review_legal_name_at_year_end", "")
    ) and str(row.get("parser_evidence_status", "")) == str(
        row.get("review_change_evidence_state", "")
    )
    if not parser_matches:
        return "CURRENT_PARSER_STILL_WRONG"
    old_matches = str(row.get("old_legal_name_at_year_end", "")) == str(
        row.get("review_legal_name_at_year_end", "")
    ) and str(row.get("old_evidence_status", "")) == str(
        row.get("review_change_evidence_state", "")
    )
    return "UNCHANGED_CORRECT" if old_matches else "CORRECTED_BY_CURRENT_PARSER"


def recommend_repair_mode(mechanisms: set[str]) -> str:
    if len(mechanisms) != 1:
        return "MORE_DIAGNOSTIC_REQUIRED"
    return {
        "PARSER_LAYOUT_GAP": "PARSER_FIX_REQUIRED",
        "SOURCE_WRONG_REPORT": "TARGETED_INDEX_THEN_H1",
        "TEXT_EXTRACTION_PROBLEM": "EXACT_H1_REFETCH_REPARSE",
        "ISSUER_FIELD_ABSENT": "MANUAL_REVIEW_REQUIRED",
        "SCANNED_OR_NON_TEXT_PDF": "OCR_OR_MANUAL_REQUIRED",
        "NO_TRUE_TEMPORAL_PROBLEM": "NO_REPAIR_NEEDED",
        "TARGETED_H2_REQUIRED": "TARGETED_H2_REQUIRED",
        "H1_SUFFICIENT_ALREADY": "NO_REPAIR_NEEDED",
        "SOURCE_INSUFFICIENT": "MORE_DIAGNOSTIC_REQUIRED",
        "OTHER": "MORE_DIAGNOSTIC_REQUIRED",
    }.get(next(iter(mechanisms)), "MORE_DIAGNOSTIC_REQUIRED")


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8"
    )
    temporary.replace(path)


def _atomic_bytes(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_bytes(payload)
    temporary.replace(path)


def _record_pdf_provenance(prediction: dict[str, Any], root: Path, pdf_path: Path) -> None:
    """Record durable PDF identity before attempting text extraction."""
    relative = pdf_path.relative_to(root)
    prediction["_evidence_path"] = str(relative)
    prediction["_evidence_sha256"] = str(prediction.get("pdf_sha256", ""))
    prediction["_text_path"] = str(relative.with_suffix(".txt"))


def capture_protected_hashes(root: Path = ROOT) -> dict[str, str]:
    summary = json.loads((root / R4A_SUMMARY_PATH.relative_to(ROOT)).read_text(encoding="utf-8"))
    expected = summary["protected_file_sha256_before"]
    actual: dict[str, str] = {}
    for relative, expected_hash in expected.items():
        if relative == "cnipa_full_cache_tree":
            actual[relative] = r4a._hash_cache_tree(
                root / "results/cnipa_legal_name_recovery/cache"
            )["sha256"]
            continue
        path = root / Path(relative)
        if not path.is_file():
            raise ValueError(f"PROTECTED_INPUT_MISSING:{relative}")
        actual[relative] = sha256_file(path)
        if actual[relative].lower() != str(expected_hash).lower():
            raise ValueError(f"R4A_PROTECTED_HASH_DRIFT:{relative}")
    if actual.get("cnipa_full_cache_tree", "").lower() != expected["cnipa_full_cache_tree"].lower():
        raise ValueError("R4A_FULL_CACHE_TREE_DRIFT")
    additional = {
        "results/cnipa_full_gap_diagnosis/full_gap_roster.csv",
        "results/cnipa_full_gap_diagnosis/gap_family_summary.csv",
        "results/cnipa_full_gap_diagnosis/stale_success_risk.csv",
        "results/cnipa_full_gap_diagnosis/stale_success_risk_summary.csv",
        "results/cnipa_full_gap_diagnosis/diagnostic_pilot_manifest.csv",
        "results/cnipa_full_gap_diagnosis/baseline_summary.json",
        "results/cnipa_full_gap_diagnosis/diagnosis_summary.json",
        "results/real_financial_full/target_manifest.csv",
        "data/processed/real_company_universe_enriched.parquet",
    }
    for relative in sorted(additional):
        path = root / relative
        if not path.is_file():
            raise ValueError(f"R4A_ARTIFACT_MISSING:{relative}")
        actual[relative] = sha256_file(path)
    return actual


class GuardedSession(requests.Session):
    def __init__(self, guard: RequestGuard) -> None:
        super().__init__()
        self.guard = guard
        self.audit_context: dict[str, Any] = {}

    def request(self, method, url, **kwargs):
        audit_context = kwargs.pop("_r4b2_audit_context", self.audit_context)
        kwargs["allow_redirects"] = False
        return self.guard.perform(
            super().request, method, url, audit_context=audit_context, **kwargs
        )


def query_targeted_annual_report(
    client: CNINFOAnnualReportClient, *, stock_code: str, report_year: int
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    code = str(stock_code).strip().zfill(6)
    row_key = f"{getattr(client, 'r4b2_firm_key', '')}|{int(report_year)}"
    prior_pages = int(getattr(client, "r4b2_index_pages_used", {}).get(row_key, 0))
    session = getattr(client, "session", None)
    if isinstance(session, GuardedSession):
        session.audit_context = {
            "firm_key": getattr(client, "r4b2_firm_key", ""),
            "year": int(report_year),
            "action": "TARGETED_CNINFO_STOCK_CATALOG",
            "index_page": None,
        }
    org_id = client.stock_catalog().get(code)
    if not org_id:
        return [], []
    params = {
        "pageNum": 1,
        "pageSize": 30,
        "column": "szse",
        "tabName": "fulltext",
        "plate": "",
        "stock": f"{code},{org_id}",
        "searchkey": f"{int(report_year)}年年度报告",
        "secid": "",
        "category": "category_ndbg_szsh",
        "trade": "",
        "seDate": f"{int(report_year) + 1}-01-01~{int(report_year) + 2}-12-31",
        "sortName": "",
        "sortType": "",
        "isHLtitle": "true",
    }
    candidates: list[dict[str, Any]] = []
    audit_rows: list[dict[str, Any]] = []
    if prior_pages >= MAX_INDEX_PAGES_PER_FIRM_YEAR:
        audit_rows.append(
            {
                "event_type": "INDEX_PAGINATION_SUMMARY",
                "pages_requested": prior_pages,
                "pages_requested_this_call": 0,
                "page_cap": MAX_INDEX_PAGES_PER_FIRM_YEAR,
                "api_total_pages": None,
                "announcements_seen": 0,
                "candidate_titles_seen": "",
                "valid_candidate_count": 0,
                "index_terminal_state": "INDEX_PAGE_CAP_REACHED_UNRESOLVED",
            }
        )
        return candidates, audit_rows
    page = prior_pages + 1
    total_pages = 0
    titles_seen: list[str] = []
    pages_requested = prior_pages
    pages_requested_this_call = 0
    while page <= MAX_INDEX_PAGES_PER_FIRM_YEAR:
        params["pageNum"] = page
        session = getattr(client, "session", None)
        if isinstance(session, GuardedSession):
            session.audit_context = {
                "firm_key": getattr(client, "r4b2_firm_key", ""),
                "year": int(report_year),
                "action": "TARGETED_CNINFO_INDEX_LOOKUP",
                "index_page": page,
            }
        response = client._request("POST", CNINFO_ANNOUNCEMENT_QUERY_URL, data=params)
        pages_requested += 1
        pages_requested_this_call += 1
        if hasattr(client, "r4b2_index_pages_used"):
            client.r4b2_index_pages_used[row_key] = pages_requested
        payload = response.json()
        announcements = payload.get("announcements") or []
        total_pages = int(payload.get("totalpages") or 0)
        for item in announcements:
            title = re.sub(r"<[^>]+>", "", str(item.get("announcementTitle", ""))).strip()
            titles_seen.append(title)
            title_year = match_annual_report_title(title)
            audit_rows.append(
                {
                    "announcement_id": str(item.get("announcementId") or ""),
                    "title": title,
                    "announcement_time": item.get("announcementTime"),
                    "candidate_report_year": title_year,
                }
            )
            adjunct = str(item.get("adjunctUrl") or "").strip()
            if title_year != int(report_year) or not adjunct:
                continue
            candidate = {
                "stock_code": str(item.get("secCode") or code).zfill(6),
                "report_year": title_year,
                "title": title,
                "announcement_id": str(item.get("announcementId") or ""),
                "announcement_time": item.get("announcementTime"),
                "source_url": CNINFO_STATIC_BASE_URL + adjunct.lstrip("/"),
                "source_type": "official_annual_report",
                "source_tier": "H1",
                "org_id": str(item.get("orgId") or org_id),
            }
            if validate_index_candidate(candidate, stock_code=code, report_year=int(report_year)):
                candidates.append(candidate)
        if candidates or page >= total_pages:
            break
        page += 1
    index_terminal = classify_index_result(
        pages_requested, total_pages, len(candidates), page_cap=MAX_INDEX_PAGES_PER_FIRM_YEAR
    )
    audit_rows.append(
        {
            "event_type": "INDEX_PAGINATION_SUMMARY",
            "pages_requested": pages_requested,
            "pages_requested_this_call": pages_requested_this_call,
            "page_cap": MAX_INDEX_PAGES_PER_FIRM_YEAR,
            "api_total_pages": total_pages,
            "announcements_seen": sum(
                1 for item in audit_rows if item.get("event_type") != "INDEX_PAGINATION_SUMMARY"
            ),
            "candidate_titles_seen": " | ".join(titles_seen),
            "valid_candidate_count": len(candidates),
            "index_terminal_state": index_terminal,
        }
    )
    candidates.sort(key=lambda row: int(row.get("announcement_time") or 0), reverse=True)
    return candidates, audit_rows


def _text_from_pdf_bytes(pdf_bytes: bytes) -> str:
    executable = shutil.which("pdftotext")
    if not executable:
        raise RuntimeError("PDFTOTEXT_NOT_AVAILABLE")
    result = subprocess.run(
        [executable, "-layout", "-", "-"],
        input=pdf_bytes,
        capture_output=True,
        timeout=180,
        check=False,
    )
    if result.returncode:
        raise RuntimeError(f"PDFTOTEXT_EXIT_{result.returncode}")
    text = result.stdout.decode("utf-8", errors="replace")
    if len(text.strip()) < 100:
        raise ValueError("TEXT_EXTRACTION_EMPTY_OR_SHORT")
    return text


def _short_independent_excerpt(text: str, stock_code: str) -> str:
    lines = [re.sub(r"\s+", " ", line).strip() for line in text.splitlines() if line.strip()]
    chosen: list[str] = []
    for line in lines[:120]:
        if "年度报告" in line or stock_code in line:
            chosen.append(line)
            if len(chosen) >= 2:
                break
    name_label = re.compile(r"(?:公司的中文名称|公司中文名称|公司名称)\s*[:：|｜]?\s*(.*)")
    for index, line in enumerate(lines):
        match = name_label.search(line)
        if match:
            value = match.group(1).strip()
            if not value and index + 1 < len(lines):
                value = lines[index + 1].strip()
            chosen.append(f"名称栏目：{line[:100]} {value[:80]}".strip())
            break
    return "；".join(chosen)[:260]


def _key_fingerprint(keys: set[tuple[str, int]]) -> str:
    payload = "\n".join(f"{firm_key}|{year}" for firm_key, year in sorted(keys))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def acquisition_columns() -> list[str]:
    return [
        "firm_key",
        "year",
        "diagnosis_group",
        "subfamily",
        "risk_tier",
        "original_reason",
        "planned_action",
        "old_status",
        "old_coverage_status",
        "old_parser_revision",
        "old_legal_name_current",
        "old_legal_name_at_year_end",
        "old_change_flag",
        "old_matched_label",
        "old_evidence_context",
        "acquisition_action",
        "acquisition_status",
        "source_url_requested",
        "source_url_final",
        "source_title",
        "source_announcement_id",
        "source_report_year",
        "http_status",
        "pdf_bytes",
        "pdf_sha256",
        "text_chars",
        "source_is_official",
        "source_is_correct_issuer",
        "source_is_correct_year",
        "source_is_full_annual_report",
        "current_parser_revision",
        "parser_legal_name_current",
        "parser_legal_name_at_year_end",
        "parser_change_flag",
        "parser_previous_name",
        "parser_new_name",
        "parser_effective_date",
        "parser_date_precision",
        "parser_evidence_status",
        "review_legal_name_at_year_end",
        "review_change_evidence_state",
        "review_previous_name",
        "review_new_name",
        "review_effective_date",
        "review_date_precision",
        "review_status",
        "reviewer_evidence_excerpt",
        "review_notes",
        "diagnostic_outcome",
        "next_action",
    ]


def _bool(value: Any) -> bool:
    if value is None or pd.isna(value):
        return False
    return str(value).strip().lower() in {"1", "true", "yes", "y"}


def _stock_code(row: pd.Series) -> str:
    raw = _value(row, "stock_code", "code", "security_code", default="")
    if not raw:
        parts = str(row.firm_key).split(":")
        raw = parts[1] if len(parts) > 1 else ""
    return str(raw).split(".")[0].zfill(6)


def _value(row: pd.Series, *names: str, default: Any = "") -> Any:
    for name in names:
        if name in row and not pd.isna(row[name]):
            return row[name]
    return default


def _merge_inputs(manifest: pd.DataFrame) -> pd.DataFrame:
    gaps = pd.read_csv(GAP_ROSTER_PATH, dtype=str, keep_default_na=False)
    stale = pd.read_csv(STALE_ROSTER_PATH, dtype=str, keep_default_na=False)
    frame = manifest.copy()
    for extra in (gaps, stale):
        extra["year"] = pd.to_numeric(extra["year"], errors="coerce").astype("Int64")
        extra = extra.drop_duplicates(["firm_key", "year"])
        payload = [c for c in extra.columns if c not in {"firm_key", "year"}]
        renamed = extra[["firm_key", "year", *payload]].rename(
            columns={column: f"__incoming_{column}" for column in payload}
        )
        frame = frame.merge(
            renamed,
            on=["firm_key", "year"],
            how="left",
            validate="one_to_one",
        )
        for column in payload:
            incoming = f"__incoming_{column}"
            if column not in frame:
                frame[column] = frame[incoming]
            else:
                existing = frame[column].replace("", pd.NA)
                frame[column] = existing.combine_first(frame[incoming])
            frame.drop(columns=incoming, inplace=True)
    return frame


def _parser_fields(text: str, row: pd.Series) -> dict[str, Any]:
    parsed = extract_annual_report_legal_name_evidence(
        text,
        expected_year=int(row.year),
        source_report_title=str(_value(row, "source_title", "source_report_title", default="")),
    )
    if hasattr(parsed, "to_dict"):
        parsed = parsed.to_dict()
    parsed = dict(parsed or {})
    aliases = {
        "parser_legal_name_current": ("legal_name_current_in_report",),
        "parser_legal_name_at_year_end": ("legal_name_at_year_end",),
        "parser_change_flag": ("company_name_change_flag",),
        "parser_previous_name": ("legal_name_previous",),
        "parser_new_name": ("legal_name_new",),
        "parser_effective_date": ("change_effective_date",),
        "parser_date_precision": ("date_precision",),
        "parser_evidence_status": ("evidence_status", "status"),
    }
    output: dict[str, Any] = {"current_parser_revision": CURRENT_PARSER_REVISION}
    for target, choices in aliases.items():
        output[target] = next((parsed[k] for k in choices if k in parsed), "")
    return output


def _fetch_pdf(
    session: GuardedSession, url: str, *, audit_context: dict[str, Any] | None = None
) -> tuple[bytes, int]:
    response = session.get(
        url, timeout=60, _r4b2_audit_context=audit_context or session.audit_context
    )
    status = int(response.status_code)
    response.raise_for_status()
    payload = response.content
    if not payload.startswith(b"%PDF-") or len(payload) < 1024:
        raise ValueError("INVALID_OR_SHORT_PDF_RESPONSE")
    return payload, status


def _ensure_output_root(root: Path) -> Path:
    resolved = root.resolve()
    if DIAGNOSIS_DIR.resolve() not in resolved.parents:
        raise ValueError("DIAGNOSTIC_OUTPUT_OUTSIDE_IGNORED_RESULTS")
    resolved.mkdir(parents=True, exist_ok=True)
    return resolved


def initialize_run(root: Path = RUN_DIR) -> tuple[pd.DataFrame, dict[str, Any], dict[str, str]]:
    root = _ensure_output_root(root)
    manifest = pd.read_csv(MANIFEST_PATH, dtype={"firm_key": str}, keep_default_na=False)
    universe = pd.read_parquet(UNIVERSE_PATH)
    full_status = pd.read_csv(FULL_STATUS_PATH, dtype={"firm_key": str})
    primary = set(
        zip(
            full_status.firm_key.astype(str),
            pd.to_numeric(full_status.year).astype(int),
            strict=True,
        )
    )
    validation = validate_frozen_manifest(manifest, primary, expected_rows=94, expected_firms=86)
    raw_sha = sha256_file(MANIFEST_PATH).upper()
    if (
        raw_sha != EXPECTED_MANIFEST_SHA256
        or validation["key_fingerprint"].upper() != EXPECTED_KEY_FINGERPRINT
        or canonical._frame_fingerprint(manifest) != EXPECTED_FRAME_FINGERPRINT
    ):
        raise ValueError("FROZEN_R4A_MANIFEST_DRIFT_STOP")
    checkpoint = root / "checkpoint.json"
    if checkpoint.exists():
        state = json.loads(checkpoint.read_text(encoding="utf-8"))
        verify_resume_fingerprints(state, EXPECTED_FRAME_FINGERPRINT)
        snapshot = state.get("protected_hashes_before", {})
        prior_predictions = root / "pilot_predictions.csv"
        transport_bug_confirmed = False
        if prior_predictions.exists():
            prior = pd.read_csv(prior_predictions, dtype=str, keep_default_na=False)
            transport_bug = prior.acquisition_status.str.contains(
                "multiple values for keyword argument 'allow_redirects'", regex=False
            )
            no_responses = prior.http_status.eq("") & prior.pdf_sha256.eq("")
            if len(prior) and transport_bug.all() and no_responses.all():
                transport_bug_confirmed = True
                state.update(
                    processed_keys={},
                    request_count=0,
                    source_blocked=False,
                    last_completed=None,
                    recovery_note=(
                        "Prior transport TypeError occurred before HTTP dispatch; "
                        "zero network requests sent."
                    ),
                )
                _atomic_json(checkpoint, state)
        if not transport_bug_confirmed:
            snapshot = capture_protected_hashes()
            if state.get("protected_hashes_before") != snapshot:
                raise ValueError("PROTECTED_BASELINE_CHANGED_SINCE_CHECKPOINT")
    else:
        snapshot = capture_protected_hashes()
        state = {
            "manifest_fingerprint": EXPECTED_FRAME_FINGERPRINT,
            "manifest_sha256": raw_sha,
            "key_fingerprint": validation["key_fingerprint"],
            "processed_keys": {},
            "request_count": 0,
            "source_blocked": False,
            "last_completed": None,
            "protected_hashes_before": snapshot,
            "started_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        }
        _atomic_bytes(root / "diagnostic_pilot_manifest.csv", MANIFEST_PATH.read_bytes())
        _atomic_json(root / "baseline_snapshot.json", {"protected_hashes_before": snapshot})
        _atomic_json(checkpoint, state)
    _ = universe  # loaded and validated as a required protected input
    return _merge_inputs(manifest), state, snapshot


def assert_r4b2_offline_gate(root: Path = R4B2_RUN_DIR) -> None:
    if root.resolve() != R4B2_RUN_DIR.resolve():
        raise ValueError("R4B2_OUTPUT_EPOCH_MISMATCH")
    required = {
        "summary": root / "r4b2_pre_network_summary.json",
        "mapping": root / "r4b_source_identity_reconciliation.csv",
        "sources": root / "r4b2_source_review_30.csv",
        "reviews": root / "r4b2_content_review_27.csv",
    }
    if not all(path.is_file() for path in required.values()):
        raise ValueError("R4B2_OFFLINE_GATE_ARTIFACT_MISSING")
    validate_r4b2_offline_gate(
        json.loads(required["summary"].read_text(encoding="utf-8")),
        pd.read_csv(required["mapping"], dtype=str, keep_default_na=False),
        pd.read_csv(required["sources"], dtype=str, keep_default_na=False),
        pd.read_csv(required["reviews"], dtype=str, keep_default_na=False),
    )


def prepare_r4b2_continuation(*, root: Path = R4B2_RUN_DIR) -> dict[str, Any]:
    """Seed a fresh R4B2 epoch from verified evidence without performing requests."""
    assert_r4b2_offline_gate(root)
    if (root / "checkpoint.json").exists():
        return json.loads((root / "checkpoint.json").read_text(encoding="utf-8"))
    _, state, protected_before = initialize_run(root)
    old_predictions = pd.read_csv(
        RUN_DIR / "pilot_predictions.csv", dtype=str, keep_default_na=False
    )
    mapping = pd.read_csv(
        root / "r4b_source_identity_reconciliation.csv", dtype=str, keep_default_na=False
    )
    content = pd.read_csv(root / "r4b2_content_review_27.csv", dtype=str, keep_default_na=False)
    source_reviews = pd.read_csv(
        root / "r4b2_source_review_30.csv", dtype=str, keep_default_na=False
    )
    reviews = pd.read_csv(RUN_DIR / "pilot_source_review.csv", dtype=str, keep_default_na=False)

    mapped = mapping.set_index(["firm_key", "year"])
    for index, prediction in old_predictions.iterrows():
        key = (str(prediction.firm_key), str(prediction.year))
        if str(prediction.get("pdf_sha256", "")):
            if key not in mapped.index:
                raise ValueError(f"R4B2_EVIDENCE_NOT_IN_OFFLINE_MAPPING:{key}")
            old_pdf = RUN_DIR / str(prediction["_evidence_path"])
            if sha256_file(old_pdf) != str(prediction["pdf_sha256"]).lower():
                raise ValueError(f"R4B2_OLD_EVIDENCE_HASH_MISMATCH:{key}")
            evidence_dir = root / "evidence" / hashlib.sha256(
                f"{key[0]}|{key[1]}".encode()
            ).hexdigest()[:16]
            evidence_dir.mkdir(parents=True, exist_ok=True)
            new_pdf, new_txt = evidence_dir / "report.pdf", evidence_dir / "report.txt"
            shutil.copyfile(old_pdf, new_pdf)
            shutil.copyfile(old_pdf.with_suffix(".txt"), new_txt)
            if sha256_file(new_pdf) != str(prediction["pdf_sha256"]).lower():
                raise ValueError(f"R4B2_COPIED_EVIDENCE_HASH_MISMATCH:{key}")
            old_predictions.loc[index, "_evidence_path"] = str(new_pdf.relative_to(root))
            old_predictions.loc[index, "_text_path"] = str(new_txt.relative_to(root))
            old_predictions.loc[index, "_evidence_sha256"] = str(prediction["pdf_sha256"])
            old_predictions.loc[index, "_manifest_fingerprint"] = EXPECTED_FRAME_FINGERPRINT
            state["processed_keys"][f"{key[0]}|{key[1]}"] = {
                "completed": True,
                "manifest_fingerprint": EXPECTED_FRAME_FINGERPRINT,
                "evidence_path": str(new_pdf.relative_to(root)),
                "evidence_sha256": str(prediction["pdf_sha256"]),
            }
        elif str(prediction.get("planned_action", "")) == "NO_NETWORK_NEGATIVE_CONTROL":
            state["processed_keys"][f"{key[0]}|{key[1]}"] = {
                "completed": True,
                "manifest_fingerprint": EXPECTED_FRAME_FINGERPRINT,
                "terminal_without_evidence": True,
            }

    review_aliases = {
        "source_is_official_review": "source_is_official",
        "source_is_correct_issuer_review": "source_is_correct_issuer",
        "source_is_correct_year_review": "source_is_correct_year",
        "source_is_full_annual_report_review": "source_is_full_annual_report",
        "review_legal_name_at_year_end_review": "review_legal_name_at_year_end",
        "review_change_evidence_state_review": "review_change_evidence_state",
        "review_previous_name_review": "review_previous_name",
        "review_new_name_review": "review_new_name",
        "review_effective_date_review": "review_effective_date",
        "review_date_precision_review": "review_date_precision",
        "review_status_review": "review_status",
        "reviewer_evidence_excerpt_review": "reviewer_evidence_excerpt",
        "review_notes_review": "review_notes",
    }
    reviews_indexed = reviews.set_index(["firm_key", "year"])
    for _, row in content.iterrows():
        key = (str(row.firm_key), str(row.year))
        for source_column, target_column in review_aliases.items():
            if source_column in row.index:
                reviews_indexed.loc[key, target_column] = str(row[source_column])
    for _, row in source_reviews.iterrows():
        key = (str(row.firm_key), str(row.year))
        if key in reviews_indexed.index:
            for source_column, target_column in review_aliases.items():
                if source_column in row.index:
                    reviews_indexed.loc[key, target_column] = str(row[source_column])

    _atomic_frame(old_predictions, root / "pilot_predictions.csv")
    _atomic_frame(reviews_indexed.reset_index(), root / "pilot_source_review.csv")
    state.update(
        r4b_historical_guarded_attempts=120,
        r4b2_guarded_attempt_count=0,
        response_received_count=0,
        transport_exception_count=0,
        pre_dispatch_or_local_error_count=0,
        source_block_count=0,
        redownloaded_completed_evidence=0,
        protected_hashes_before=protected_before,
    )
    _atomic_json(root / "checkpoint.json", state)
    return state


def run_pilot(
    *, resume: bool = False, root: Path = RUN_DIR, r4b2_epoch: bool = False
) -> dict[str, Any]:
    if r4b2_epoch:
        assert_r4b2_offline_gate(root)
    root = _ensure_output_root(root)
    frame, state, protected_before = initialize_run(root)
    if state.get("source_blocked"):
        return {
            "status": "TARGETED_DIAGNOSTIC_PILOT_NEEDS_FIX",
            "reason": "SOURCE_BLOCKED",
            "request_count": state["request_count"],
        }
    audit_log = RequestAuditLog(root / "request_audit.jsonl", epoch="R4B2") if r4b2_epoch else None
    counter_key = "r4b2_guarded_attempt_count" if r4b2_epoch else "request_count"
    guard = RequestGuard(
        state=state,
        persist=lambda: _atomic_json(root / "checkpoint.json", state),
        max_requests=120,
        audit_log=audit_log,
        counter_key=counter_key,
    )
    session = GuardedSession(guard)
    client = CNINFOAnnualReportClient(
        cache_dir=root / "unused_cache_never_written",
        retries=0,
        session=session,
        request_spacing=1.0,
    )
    client.r4b2_index_pages_used = {}
    if r4b2_epoch and (root / "request_audit.jsonl").is_file():
        for line in (root / "request_audit.jsonl").read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            event = json.loads(line)
            if event.get("action") != "TARGETED_CNINFO_INDEX_LOOKUP":
                continue
            if event.get("index_page") is None:
                continue
            key = f"{event.get('firm_key', '')}|{event.get('year', '')}"
            client.r4b2_index_pages_used[key] = max(
                int(event["index_page"]), client.r4b2_index_pages_used.get(key, 0)
            )
    predictions_path = root / "pilot_predictions.csv"
    current: dict[str, dict[str, Any]] = {}
    if resume and predictions_path.exists():
        existing = pd.read_csv(predictions_path, dtype=str, keep_default_na=False)
        current = {f"{r.firm_key}|{r.year}": r.to_dict() for _, r in existing.iterrows()}
    if int(state.get(counter_key, 0)) >= 120:
        state["stop_reason"] = "REQUEST_CAP_REACHED"
        _atomic_json(root / "checkpoint.json", state)
        if not r4b2_epoch:
            return reconcile_local_evidence(root=root)
        return {
            "status": "TARGETED_DIAGNOSTIC_PILOT_NEEDS_FIX",
            "reason": "R4B2_REQUEST_CAP_REACHED",
        }
    audit_rows: list[dict[str, Any]] = []
    for _, row in frame.iterrows():
        key = f"{row.firm_key}|{int(row.year)}"
        planned = str(_value(row, "proposed_network_action", "planned_action"))
        if (
            key in current
            and not str(current[key].get("acquisition_status", "")).startswith("ERROR:")
            and should_skip_completed_row(
                state["processed_keys"].get(key, {}), EXPECTED_FRAME_FINGERPRINT, root
            )
        ):
            continue
        old_name = _value(
            row, "old_legal_name_at_year_end", "legal_name_at_year_end", "company_name"
        )
        pred: dict[str, Any] = {c: _value(row, c) for c in acquisition_columns() if c in row.index}
        pred.update(
            {
                "firm_key": str(row.firm_key),
                "year": int(row.year),
                "diagnosis_group": row.get("diagnosis_group", ""),
                "subfamily": row.get("subfamily", ""),
                "risk_tier": row.get("risk_tier", ""),
                "planned_action": planned,
                "old_legal_name_at_year_end": old_name,
                "old_evidence_status": _value(row, "old_evidence_status", "evidence_status"),
                "acquisition_action": "",
                "acquisition_status": "NOT_ATTEMPTED",
                "source_url_requested": "",
                "source_url_final": "",
                "source_title": "",
                "source_announcement_id": "",
                "source_report_year": "",
                "http_status": "",
                "pdf_bytes": 0,
                "pdf_sha256": "",
                "text_chars": 0,
                "source_is_official": False,
                "source_is_correct_issuer": False,
                "source_is_correct_year": False,
                "source_is_full_annual_report": False,
                "current_parser_revision": CURRENT_PARSER_REVISION,
                "review_status": "PENDING",
                "diagnostic_outcome": "UNRESOLVED",
                "next_action": "SOURCE_UNRESOLVED",
            }
        )
        action = plan_acquisition_action(
            planned,
            str(_value(row, "source_url", "source_url_h1", "h1_url")),
            _bool(_value(row, "pdf_content_persisted", default=False)),
        )
        pdf_payload: bytes | None = None
        candidate: dict[str, Any] = {}
        try:
            if action["mode"] in {"EXACT_H1", "EXACT_H1_FOR_MANUAL_REVIEW"}:
                pred["acquisition_action"] = action["mode"]
                pred["source_url_requested"] = action["url"]
                context = {
                    "firm_key": str(row.firm_key),
                    "year": int(row.year),
                    "action": action["mode"],
                    "index_page": None,
                }
                session.audit_context = context
                pdf_payload, status = _fetch_pdf(session, action["url"], audit_context=context)
                pred.update(
                    http_status=status,
                    pdf_bytes=len(pdf_payload),
                    pdf_sha256=sha256_bytes(pdf_payload),
                    source_url_final=action["url"],
                )
            elif action["mode"] == "INDEX_LOOKUP":
                pred["acquisition_action"] = action["mode"]
                client.r4b2_firm_key = str(row.firm_key)
                code = _stock_code(row)
                candidates, index_audit = query_targeted_annual_report(
                    client, stock_code=code, report_year=int(row.year)
                )
                audit_rows.extend(
                    {"firm_key": row.firm_key, "year": int(row.year), **item}
                    for item in index_audit
                )
                if candidates:
                    candidate = candidates[0]
                    pred.update(
                        source_title=candidate["title"],
                        source_announcement_id=candidate["announcement_id"],
                        source_report_year=candidate["report_year"],
                        source_url_requested=candidate["source_url"],
                    )
                    context = {
                        "firm_key": str(row.firm_key),
                        "year": int(row.year),
                        "action": "INDEX_CANDIDATE_H1_GET",
                        "index_page": None,
                    }
                    session.audit_context = context
                    pdf_payload, status = _fetch_pdf(
                        session, candidate["source_url"], audit_context=context
                    )
                    pred.update(
                        http_status=status,
                        pdf_bytes=len(pdf_payload),
                        pdf_sha256=sha256_bytes(pdf_payload),
                        source_url_final=candidate["source_url"],
                    )
                else:
                    pred["acquisition_status"] = "INDEX_LOOKUP_NO_VALID_ANNUAL_REPORT"
            else:
                pred["acquisition_action"] = (
                    "LOCAL_CONTROL_ONLY"
                    if planned == "NO_NETWORK_NEGATIVE_CONTROL"
                    else "LOCAL_ONLY"
                )
                pred["acquisition_status"] = pred["acquisition_action"]
                pred["review_status"] = (
                    "LOCAL_CONTROL_ONLY"
                    if planned == "NO_NETWORK_NEGATIVE_CONTROL"
                    else "SOURCE_UNRESOLVED"
                )
                pred["next_action"] = (
                    "LOCAL_NEGATIVE_CONTROL_ONLY"
                    if planned == "NO_NETWORK_NEGATIVE_CONTROL"
                    else "TARGETED_H2_REQUIRED"
                )
            if pdf_payload is not None:
                evidence_dir = root / "evidence" / hashlib.sha256(key.encode()).hexdigest()[:16]
                pdf_path = evidence_dir / "report.pdf"
                _atomic_bytes(pdf_path, pdf_payload)
                # Persist provenance as soon as the PDF is durable, even if text
                # extraction fails afterward. This keeps valid PDF evidence auditable.
                text_path = evidence_dir / "report.txt"
                _record_pdf_provenance(pred, root, pdf_path)
                text = _text_from_pdf_bytes(pdf_payload)
                _atomic_bytes(text_path, text.encode("utf-8"))
                pred["text_chars"] = len(text)
                pred["source_title"] = candidate.get(
                    "title", _value(row, "source_title", default="")
                )
                pred["source_report_year"] = candidate.get("report_year", int(row.year))
                parser = _parser_fields(text, row)
                pred.update(parser)
                pred["acquisition_status"] = "PDF_AND_TEXT_OK"
                pred["_completed"] = True
                pred["_manifest_fingerprint"] = EXPECTED_FRAME_FINGERPRINT
                # Keep source review separate until independent verification.
                pred["_review_excerpt_candidate"] = _short_independent_excerpt(
                    text, str(_value(row, "stock_code", "code", default=""))
                )
            else:
                pred["_completed"] = True
                pred["_terminal_without_evidence"] = True
                pred["_manifest_fingerprint"] = EXPECTED_FRAME_FINGERPRINT
            current[key] = pred
            state["processed_keys"][key] = {
                "completed": True,
                "manifest_fingerprint": EXPECTED_FRAME_FINGERPRINT,
                "terminal_without_evidence": bool(pred.get("_terminal_without_evidence")),
                "evidence_path": pred.get("_evidence_path", ""),
                "evidence_sha256": pred.get("_evidence_sha256", ""),
            }
            state["last_completed"] = key
            _atomic_json(root / "checkpoint.json", state)
            # Save each row atomically via temporary file replacement.
            _atomic_frame(pd.DataFrame(current.values()), predictions_path)
        except (SourceBlocked, RequestCapReached) as exc:
            state["last_error"] = str(exc)
            _atomic_json(root / "checkpoint.json", state)
            break
        except Exception as exc:
            pred["acquisition_status"] = f"ERROR:{type(exc).__name__}:{exc}"
            pred["_completed"] = True
            pred["_terminal_without_evidence"] = not bool(
                pred.get("pdf_sha256") and pred.get("_evidence_path")
            )
            pred["_manifest_fingerprint"] = EXPECTED_FRAME_FINGERPRINT
            current[key] = pred
            state["processed_keys"][key] = {
                "completed": True,
                "manifest_fingerprint": EXPECTED_FRAME_FINGERPRINT,
                "terminal_without_evidence": bool(pred["_terminal_without_evidence"]),
                "evidence_path": pred.get("_evidence_path", ""),
                "evidence_sha256": pred.get("_evidence_sha256", ""),
            }
            state["last_completed"] = key
            _atomic_json(root / "checkpoint.json", state)
            _atomic_frame(pd.DataFrame(current.values()), predictions_path)
        if pdf_payload is not None:
            audit_rows.append(
                {
                    "firm_key": row.firm_key,
                    "year": int(row.year),
                    "selected_candidate": candidate,
                    "pdf_sha256": pred["pdf_sha256"],
                    "text_chars": pred["text_chars"],
                }
            )
    predictions = pd.DataFrame(current.values())
    if len(predictions):
        predictions = predictions.sort_values(["firm_key", "year"]).reset_index(drop=True)
    if not predictions.empty and set(
        zip(predictions.firm_key.astype(str), pd.to_numeric(predictions.year).astype(int))
    ) - set(zip(frame.firm_key.astype(str), pd.to_numeric(frame.year).astype(int))):
        raise ValueError("OUTPUT_KEY_OUTSIDE_FROZEN_94")
    _atomic_frame(predictions, predictions_path)
    reviews = load_or_create_independent_review(predictions, root / "pilot_source_review.csv")
    # Completed independent reviews are not synthesized: keep template pending and distinct.
    _atomic_frame(reviews, root / "pilot_source_review_template.csv")
    _atomic_frame(pd.DataFrame(audit_rows), root / "source_acquisition_audit.csv")
    protected_after = capture_protected_hashes()
    protected_unchanged = protected_before == protected_after
    reviews_path = root / "pilot_source_review.csv"
    review_complete = False
    if reviews_path.exists():
        source_reviews = pd.read_csv(reviews_path, dtype=str, keep_default_na=False)
        review_complete = (
            len(source_reviews) == 94
            and not source_reviews.review_status.isin(
                ["PENDING", "SOURCE_UNRESOLVED", "SOURCE_BLOCKED"]
            ).any()
        )
    actions_complete = (
        len(predictions) == 94
        and not predictions.acquisition_status.str.startswith(
            ("ERROR:", "REQUEST_CAP_REACHED")
        ).any()
    )
    status = (
        "TARGETED_DIAGNOSTIC_PILOT_COMPLETE"
        if actions_complete and review_complete and protected_unchanged
        else "TARGETED_DIAGNOSTIC_PILOT_NEEDS_FIX"
    )
    summary = {
        "status": status,
        "manifest_rows": len(frame),
        "manifest_firms": frame.firm_key.nunique(),
        "manifest_sha256": EXPECTED_MANIFEST_SHA256,
        "frame_fingerprint": EXPECTED_FRAME_FINGERPRINT,
        "key_fingerprint": EXPECTED_KEY_FINGERPRINT,
        "request_count": int(state.get(counter_key, 0)),
        "r4b_historical_guarded_attempts": 120 if r4b2_epoch else None,
        "r4b2_guarded_attempts": int(state.get("r4b2_guarded_attempt_count", 0)),
        "response_received_count": int(state.get("response_received_count", 0)),
        "transport_exception_count": int(state.get("transport_exception_count", 0)),
        "pre_dispatch_or_local_error_count": int(
            state.get("pre_dispatch_or_local_error_count", 0)
        ),
        "source_block_count": int(state.get("source_block_count", 0)),
        "request_audit_rows": (
            sum(1 for _ in (root / "request_audit.jsonl").open(encoding="utf-8"))
            if (root / "request_audit.jsonl").is_file()
            else 0
        ),
        "redownloaded_completed_evidence": int(
            state.get("redownloaded_completed_evidence", 0)
        ),
        "h2_requests": 0,
        "source_blocked": bool(state.get("source_blocked")),
        "protected_inputs_unchanged": protected_unchanged,
        "output_keys_within_manifest": True,
        "protected_hashes_before": protected_before,
        "protected_hashes_after": protected_after,
    }
    _atomic_json(root / "r4b_summary.json", summary)
    return summary


def reconcile_local_evidence(*, root: Path = RUN_DIR) -> dict[str, Any]:
    """Re-parse only already-downloaded pilot TXT files; never performs network I/O."""
    root = _ensure_output_root(root)
    frame = _merge_inputs(
        pd.read_csv(MANIFEST_PATH, dtype={"firm_key": str}, keep_default_na=False)
    )
    predictions_path = root / "pilot_predictions.csv"
    predictions = pd.read_csv(predictions_path, dtype=str, keep_default_na=False)
    for index, prediction in predictions.iterrows():
        if not prediction.get("pdf_sha256"):
            if str(prediction.get("acquisition_status", "")).startswith("ERROR:"):
                predictions.loc[index, "acquisition_status"] = "REQUEST_CAP_REACHED_OR_LOCAL_ERROR"
            continue
        key = f"{prediction.firm_key}|{prediction.year}"
        directory = root / "evidence" / hashlib.sha256(key.encode()).hexdigest()[:16]
        text_path = directory / "report.txt"
        if not text_path.is_file():
            predictions.loc[index, "acquisition_status"] = "TEXT_EVIDENCE_MISSING"
            continue
        source_row = frame[
            (frame.firm_key == prediction.firm_key)
            & (frame.year.astype(str) == str(prediction.year))
        ].iloc[0]
        old_values = {
            "original_reason": _value(source_row, "reason", "failure_reason", "risk_reason"),
            "old_status": _value(source_row, "raw_status", "historical_status"),
            "old_coverage_status": _value(source_row, "coverage_status", "gap_family"),
            "old_parser_revision": _value(source_row, "parser_revision"),
            "old_legal_name_current": _value(source_row, "legal_name_current_in_report"),
            "old_legal_name_at_year_end": _value(source_row, "legal_name_at_year_end"),
            "old_change_flag": _value(source_row, "company_name_change_flag"),
            "old_matched_label": _value(source_row, "matched_label"),
            "old_evidence_context": _value(source_row, "evidence_context"),
            "source_url_requested": prediction.get("source_url_requested")
            or _value(source_row, "source_url"),
            "source_title": prediction.get("source_title")
            or _value(source_row, "source_report_title"),
            "source_announcement_id": prediction.get("source_announcement_id")
            or _value(source_row, "source_announcement_id"),
            "source_report_year": prediction.year,
        }
        for column, value in old_values.items():
            predictions.loc[index, column] = str(value)
        text = text_path.read_text(encoding="utf-8")
        parsed = _parser_fields(text, source_row)
        for column, value in parsed.items():
            predictions.loc[index, column] = str(value)
        predictions.loc[index, "text_chars"] = str(len(text))
        predictions.loc[index, "acquisition_status"] = "PDF_AND_TEXT_OK"
        predictions.loc[index, "_evidence_path"] = str((directory / "report.pdf").relative_to(root))
        predictions.loc[index, "_evidence_sha256"] = prediction.pdf_sha256
        predictions.loc[index, "_manifest_fingerprint"] = EXPECTED_FRAME_FINGERPRINT
        predictions.loc[index, "_completed"] = "True"
    for column in acquisition_columns():
        if column not in predictions:
            predictions[column] = ""
    predictions = predictions[
        acquisition_columns() + [column for column in predictions.columns if column.startswith("_")]
    ]
    _atomic_frame(predictions, predictions_path)
    _atomic_frame(build_review_template(predictions), root / "pilot_source_review_template.csv")
    state = json.loads((root / "checkpoint.json").read_text(encoding="utf-8"))
    protected_after = capture_protected_hashes()
    protected_unchanged = protected_after == state["protected_hashes_before"]
    status = "TARGETED_DIAGNOSTIC_PILOT_NEEDS_FIX"
    summary = {
        "status": status,
        "manifest_rows": 94,
        "manifest_firms": 86,
        "manifest_sha256": EXPECTED_MANIFEST_SHA256,
        "frame_fingerprint": EXPECTED_FRAME_FINGERPRINT,
        "key_fingerprint": EXPECTED_KEY_FINGERPRINT,
        "request_count": int(state.get("request_count", 0)),
        "request_cap_reached": int(state.get("request_count", 0)) >= 120,
        "source_blocked": bool(state.get("source_blocked")),
        "protected_inputs_unchanged": protected_unchanged,
        "output_keys_within_manifest": set(zip(predictions.firm_key, predictions.year)).issubset(
            set(zip(frame.firm_key.astype(str), frame.year.astype(str)))
        ),
        "acquired_pdf_rows": int(predictions.pdf_sha256.ne("").sum()),
        "review_status": "PENDING_INDEPENDENT_REVIEW",
        "protected_hashes_before": state["protected_hashes_before"],
        "protected_hashes_after": protected_after,
        "limitation": "Hard request cap reached; no further network requests are permitted.",
    }
    _atomic_json(root / "r4b_summary.json", summary)
    return summary


def build_incomplete_review_and_r4c(*, root: Path = RUN_DIR) -> dict[str, Any]:
    """Write conservative, separated review/aggregate artifacts from local evidence only."""
    root = _ensure_output_root(root)
    manifest = _merge_inputs(
        pd.read_csv(MANIFEST_PATH, dtype={"firm_key": str}, keep_default_na=False)
    )
    predictions = pd.read_csv(root / "pilot_predictions.csv", dtype=str, keep_default_na=False)
    rows: list[dict[str, Any]] = []
    for _, prediction in predictions.iterrows():
        item = {"firm_key": prediction.firm_key, "year": prediction.year}
        action = prediction.get("planned_action", "")
        review_status = "SOURCE_UNRESOLVED"
        official = issuer = correct_year = full_report = ""
        excerpt = ""
        if action == "NO_NETWORK_NEGATIVE_CONTROL":
            review_status = "LOCAL_CONTROL_ONLY"
        elif prediction.get("pdf_sha256"):
            key = f"{prediction.firm_key}|{prediction.year}"
            text_path = (
                root / "evidence" / hashlib.sha256(key.encode()).hexdigest()[:16] / "report.txt"
            )
            if text_path.is_file():
                text = text_path.read_text(encoding="utf-8")
                source_row = manifest[
                    (manifest.firm_key.astype(str) == str(prediction.firm_key))
                    & (manifest.year.astype(str) == str(prediction.year))
                ].iloc[0]
                title = str(source_row.get("source_report_title", ""))
                host_ok = _allowed_cninfo_url(str(prediction.get("source_url_final", "")))
                title_year = match_annual_report_title(title)
                observed_year = str(prediction.year) in text[:12000]
                summary_doc = "年度报告摘要" in "\n".join(text.splitlines()[:80])
                official = bool(host_ok)
                correct_year = bool(title_year == int(prediction.year) or observed_year)
                code = _stock_code(source_row)
                issuer = bool(code and code in text[:12000])
                full_report = bool(not summary_doc and len(text) >= 10000)
                excerpts = [
                    re.sub(r"\s+", " ", line).strip()
                    for line in text.splitlines()
                    if any(label in line for label in ("公司的中文名称", "公司中文名称"))
                ]
                excerpt = excerpts[0][:200] if excerpts else ""
                # Source flags are checked; legal-name/event adjudication remains open.
                review_status = "SOURCE_UNRESOLVED"
        row = {
            **item,
            "source_is_official": official,
            "source_is_correct_issuer": issuer,
            "source_is_correct_year": correct_year,
            "source_is_full_annual_report": full_report,
            "review_legal_name_at_year_end": "",
            "review_change_evidence_state": "",
            "review_previous_name": "",
            "review_new_name": "",
            "review_effective_date": "",
            "review_date_precision": "",
            "review_status": review_status,
            "reviewer_evidence_excerpt": excerpt,
            "review_notes": (
                "Independent event/name adjudication not complete; no prediction values copied."
            ),
        }
        rows.append(row)
    review_path = root / "pilot_source_review.csv"
    if not review_path.exists():
        _atomic_frame(pd.DataFrame(rows), review_path)
    reviews = load_or_create_independent_review(predictions, review_path)

    failure_rows: list[dict[str, Any]] = []
    for _, prediction in predictions.iterrows():
        if prediction.pdf_sha256:
            text_path = root / str(prediction.get("_text_path", ""))
            if not text_path.is_file():
                key = f"{prediction.firm_key}|{prediction.year}"
                text_path = (
                    root / "evidence" / hashlib.sha256(key.encode()).hexdigest()[:16] / "report.txt"
                )
            text = text_path.read_text(encoding="utf-8") if text_path.is_file() else ""
            reason = "TEXT_OK" if len(text) >= 100 else "TEXT_EXTRACTION_FAILED"
            if "年度报告摘要" in "\n".join(text.splitlines()[:80]):
                reason = "SOURCE_RETURNED_SUMMARY_NOT_FULL_REPORT"
        else:
            reason = str(prediction.acquisition_status)
        failure_rows.append(
            {
                "firm_key": prediction.firm_key,
                "year": prediction.year,
                "diagnosis_group": prediction.diagnosis_group,
                "subfamily": prediction.subfamily,
                "risk_tier": prediction.risk_tier,
                "planned_action": prediction.planned_action,
                "failure_reason": reason,
                "http_status": prediction.http_status,
                "pdf_sha256": prediction.pdf_sha256,
                "text_chars": prediction.text_chars,
            }
        )
    _atomic_frame(pd.DataFrame(failure_rows), root / "failure_decomposition.csv")

    baseline = json.loads((DIAGNOSIS_DIR / "diagnosis_summary.json").read_text(encoding="utf-8"))
    matrix: list[dict[str, Any]] = []
    for _, row in manifest.iterrows():
        tier = str(row.risk_tier)
        group = str(row.subfamily)
        label = group if tier == "NOT_APPLICABLE" else f"{group}|{tier}"
        if label not in {x["group"] for x in matrix}:
            population = (
                next(
                    (
                        count
                        for key, count in baseline.get("gap_subfamily_counts", {}).items()
                        if key.endswith(f"|{group}")
                    ),
                    0,
                )
                if str(row.diagnosis_group) == "GAP"
                else baseline.get("stale_risk_tier_counts", {}).get(tier, 0)
            )
            group_rows = manifest[(manifest.subfamily == group) & (manifest.risk_tier == tier)]
            group_keys = set(zip(group_rows.firm_key.astype(str), group_rows.year.astype(str)))
            source_rows = reviews[
                reviews.apply(
                    lambda review: (str(review.firm_key), str(review.year)) in group_keys,
                    axis=1,
                )
            ]
            source_ok = int(
                sum(
                    _bool(review.source_is_official)
                    and _bool(review.source_is_correct_issuer)
                    and _bool(review.source_is_correct_year)
                    and _bool(review.source_is_full_annual_report)
                    for _, review in source_rows.iterrows()
                )
            )
            matrix.append(
                {
                    "group": label,
                    "population_rows": int(population),
                    "pilot_rows": len(group_rows),
                    "source_success": source_ok,
                    "independent_reviewed": int(
                        reviews[
                            reviews.apply(
                                lambda r: (
                                    (str(r.firm_key), str(r.year)) in group_keys
                                    and str(r.review_status) == "PASS"
                                ),
                                axis=1,
                            )
                        ].shape[0]
                    ),
                    "old_correct": "",
                    "current_correct": "",
                    "current_wrong": "",
                    "unresolved": len(group_rows),
                    "primary_failure_mechanism": "REQUEST_CAP_OR_INDEPENDENT_REVIEW_PENDING",
                    "recommended_repair_mode": "MORE_DIAGNOSTIC_REQUIRED",
                    "repair_scope_candidate": "NO_BULK_REPAIR_AUTHORIZED",
                    "additional_pilot_required": True,
                    "confidence_note": (
                        "Pilot acquisition hit the 120-attempt cap; "
                        "evidence does not support extrapolation."
                    ),
                }
            )
    _atomic_frame(pd.DataFrame(matrix), root / "subfamily_scalability_matrix.csv")

    r4c = [
        {
            "repair_group": "STALE_HIGH_34",
            "population_rows": 34,
            "eligible_rows": 0,
            "proposed_action": "SECOND_PILOT_BEFORE_ANY_BULK_REPARSE",
            "evidence_basis": "R4B incomplete; no source-grounded adjudication denominator.",
            "requires_parser_change": "UNRESOLVED",
            "requires_h2": False,
            "requires_network": True,
            "requires_manual_review": True,
            "next_stage_priority": "P1",
        },
        {
            "repair_group": "STALE_MEDIUM_2155",
            "population_rows": 2155,
            "eligible_rows": 0,
            "proposed_action": "REFINE_SUBCLASSES_AND_RUN_SECOND_PILOT",
            "evidence_basis": "Current sample has no validated accuracy denominator.",
            "requires_parser_change": "UNRESOLVED",
            "requires_h2": False,
            "requires_network": True,
            "requires_manual_review": True,
            "next_stage_priority": "P2",
        },
        {
            "repair_group": "TEMPORAL_BOTH_NAMES_NO_PAIR_NO_DATE_349",
            "population_rows": 349,
            "eligible_rows": 0,
            "proposed_action": "LOCAL_TRAJECTORY_TRIAGE_THEN_TARGETED_H2_ONLY_IF_AUTHORIZED",
            "evidence_basis": "R4B manual subset not fully reviewed; no H2 performed.",
            "requires_parser_change": "UNRESOLVED",
            "requires_h2": "POSSIBLE",
            "requires_network": "POSSIBLE",
            "requires_manual_review": True,
            "next_stage_priority": "P1",
        },
        {
            "repair_group": "LEGAL_NAME_EXTRACTION_FAILED_238",
            "population_rows": 238,
            "eligible_rows": 0,
            "proposed_action": "SEPARATE_LAYOUT_AND_LABEL_SUBCLASSES; REFRESH ONLY AFTER PILOT",
            "evidence_basis": (
                "R4B partial text sample; parser outputs not independently adjudicated."
            ),
            "requires_parser_change": "POSSIBLE",
            "requires_h2": False,
            "requires_network": True,
            "requires_manual_review": True,
            "next_stage_priority": "P1",
        },
        {
            "repair_group": "REPORT_NOT_FOUND_444",
            "population_rows": 444,
            "eligible_rows": 0,
            "proposed_action": "BOUNDED_INDEX_DIAGNOSTIC_AFTER_NEW_REQUEST_BUDGET_AUTHORIZATION",
            "evidence_basis": "Current R4B hit hard request cap; remaining index rows unresolved.",
            "requires_parser_change": False,
            "requires_h2": False,
            "requires_network": True,
            "requires_manual_review": True,
            "next_stage_priority": "P2",
        },
        {
            "repair_group": "FETCH_TEXT_FAILURE_13",
            "population_rows": 13,
            "eligible_rows": 0,
            "proposed_action": "RECLASSIFY_WITH_LOCAL_PDF_VALIDATION_AND_TEXT_EXTRACTION",
            "evidence_basis": "R4B sample incomplete; OCR not performed.",
            "requires_parser_change": "UNRESOLVED",
            "requires_h2": False,
            "requires_network": "POSSIBLE",
            "requires_manual_review": True,
            "next_stage_priority": "P2",
        },
    ]
    _atomic_frame(pd.DataFrame(r4c), root / "r4c_repair_plan.csv")
    metrics = calculate_source_grounded_metrics(predictions, reviews)
    result = {
        "status": "TARGETED_DIAGNOSTIC_PILOT_NEEDS_FIX",
        "manifest_rows": 94,
        "manifest_firms": 86,
        "planned_action_counts": {
            str(k): int(v) for k, v in manifest.proposed_network_action.value_counts().items()
        },
        "acquired_pdf_rows": int(predictions.pdf_sha256.ne("").sum()),
        "request_count_guarded": 120,
        "source_blocked": False,
        "review_metrics": metrics,
        "why_incomplete": [
            "Hard HTTP-attempt cap reached; no additional CNINFO calls made.",
            "Some exact-H1/index actions remain unresolved.",
            "Independent legal-name and event adjudication remains pending.",
        ],
    }
    _atomic_json(root / "r4b_diagnostic_findings.json", result)
    return result


def _atomic_frame(frame: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    frame.to_csv(temp, index=False, encoding="utf-8-sig")
    temp.replace(path)


def validate_frozen_manifest(
    frame: pd.DataFrame,
    primary_keys: set[tuple[str, int]],
    *,
    expected_rows: int,
    expected_firms: int,
    expected_action_counts: dict[str, int] | None = None,
    expected_gap_subfamilies: set[str] | None = None,
    expected_stale_tiers: set[str] | None = None,
) -> dict[str, Any]:
    required = {
        "firm_key",
        "year",
        "diagnosis_group",
        "subfamily",
        "risk_tier",
        "proposed_network_action",
    }
    if not required.issubset(frame.columns):
        raise ValueError("PILOT_MANIFEST_COLUMNS_MISSING")
    normalized = frame.copy()
    normalized["firm_key"] = normalized.firm_key.astype(str)
    normalized["year"] = pd.to_numeric(normalized.year, errors="coerce")
    if normalized.year.isna().any():
        raise ValueError("PILOT_MANIFEST_INVALID_YEAR")
    normalized["year"] = normalized.year.astype(int)
    keys = list(zip(normalized.firm_key, normalized.year, strict=True))
    key_set = set(keys)
    if len(key_set) != len(frame) or not key_set.issubset(primary_keys):
        raise ValueError("DUPLICATE_OR_OUT_OF_TARGET_PILOT_KEY")
    if len(frame) != expected_rows or normalized.firm_key.nunique() != expected_firms:
        raise ValueError("FROZEN_PILOT_ROW_OR_FIRM_COUNT_MISMATCH")
    action_counts = {
        str(key): int(value)
        for key, value in normalized.proposed_network_action.value_counts().items()
    }
    if expected_action_counts is not None and action_counts != expected_action_counts:
        raise ValueError("FROZEN_PILOT_ACTION_COUNTS_MISMATCH")
    gap_subfamilies = {
        item
        for value in normalized.loc[normalized.diagnosis_group.eq("GAP"), "subfamily"].astype(str)
        for item in value.split(";")
        if item
    }
    stale_tiers = {
        item
        for value in normalized.loc[
            normalized.diagnosis_group.str.startswith("STALE"), "risk_tier"
        ].astype(str)
        for item in value.split(";")
        if item and item != "NOT_APPLICABLE"
    }
    if expected_gap_subfamilies is not None and gap_subfamilies != expected_gap_subfamilies:
        raise ValueError("FROZEN_PILOT_GAP_SUBFAMILY_MISMATCH")
    if expected_stale_tiers is not None and stale_tiers != expected_stale_tiers:
        raise ValueError("FROZEN_PILOT_STALE_TIER_MISMATCH")
    normalized_keys = {(str(firm_key), int(year)) for firm_key, year in keys}
    return {
        "rows": len(normalized),
        "firms": int(normalized.firm_key.nunique()),
        "key_fingerprint": _key_fingerprint(normalized_keys),
        "action_counts": action_counts,
        "gap_subfamilies": sorted(gap_subfamilies),
        "stale_tiers": sorted(stale_tiers),
    }


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()
    print(json.dumps(run_pilot(resume=args.resume), ensure_ascii=False, indent=2))
