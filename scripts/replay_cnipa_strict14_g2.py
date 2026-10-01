from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from urllib.parse import urlparse

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.replay_cnipa_strict14_v3 import (  # noqa: E402
    EXPECTED_RAW_HASHES,
    _hash,
    _json,
    _run_frozen45,
)
from src.cnipa_annual_report_names import (  # noqa: E402
    PARSER_REVISION,
    extract_annual_report_legal_name_evidence,
    extract_company_name_change_announcement,
    is_change_related_candidate,
)
from src.cnipa_strict14_replay import (  # noqa: E402
    apply_resolved_h2_to_rows,
    build_complete_row_predictions,
    build_h2_needed_manifest,
    build_source_manifest,
    canonical_candidate_rows,
    classify_strict14_gate,
    fetch_h1_sources,
    score_events,
    score_strict_rows,
    strict14_keys,
    verify_ground_truth_fingerprints,
)
from src.historical_province_sources import (  # noqa: E402
    CNINFO_ANNOUNCEMENT_QUERY_URL,
    CNINFO_STATIC_BASE_URL,
    CNINFO_STOCK_LIST_URL,
    CNINFOAnnualReportClient,
    SourceBlocked,
)

LEGAL = ROOT / "results/cnipa_legal_name_recovery"
OUT = ROOT / "results/cnipa_preflight/strict14_g2_replay_20261001"
MAX_ATTEMPTS = 24
MAX_PDFS_PER_TARGET = 3


class RequestCapReached(RuntimeError):
    pass


class GuardedH2Session(requests.Session):
    """Allow only stock lookup, manifest-scoped H2 queries and candidate PDFs."""

    def __init__(self, targets: pd.DataFrame):
        super().__init__()
        self.targets = {
            (str(row.firm_key), int(row.year)): {
                "firm_key": str(row.firm_key),
                "stock_code": str(row.firm_key).split(":")[1].zfill(6),
                "year": int(row.year),
                "start": f"{int(row.year)}-01-01",
                "end": f"{int(row.year) + 1}-03-31",
            }
            for row in targets.itertuples(index=False)
        }
        self.current_key: tuple[str, int] | None = None
        self.attempts: list[dict[str, object]] = []
        self.pdf_count: dict[tuple[str, int], int] = {}
        self.discovery_count: dict[tuple[str, int], int] = {}
        self.pdf_payloads: dict[str, bytes] = {}
        self.rejected: list[dict[str, object]] = []
        self._catalog_seen = False

    def request(self, method, url, **kwargs):
        method = method.upper()
        data = kwargs.get("data") or {}
        target = self.targets.get(self.current_key, {})
        purpose = ""
        if method == "GET" and url == CNINFO_STOCK_LIST_URL and not self._catalog_seen:
            self._catalog_seen = True
            purpose = "stock_catalog_lookup"
        elif method == "POST" and url == CNINFO_ANNOUNCEMENT_QUERY_URL and target:
            stock = str(data.get("stock", ""))
            date_window = str(data.get("seDate", ""))
            if (
                stock.split(",", 1)[0].zfill(6) != target["stock_code"]
                or date_window != f"{target['start']}~{target['end']}"
                or data.get("searchkey") != "公司名称变更"
            ):
                self.rejected.append(
                    {
                        "method": method,
                        "url": url,
                        "firm_key": target["firm_key"],
                        "stock": stock,
                        "seDate": date_window,
                        "searchkey": data.get("searchkey"),
                        "expected": target,
                    }
                )
                raise RuntimeError(f"H2_DISCOVERY_SCOPE_VIOLATION:{self.rejected[-1]}")
            key = self.current_key
            if self.discovery_count.get(key, 0) >= 1:
                raise RuntimeError("H2_PER_TARGET_DISCOVERY_CAP_REACHED")
            self.discovery_count[key] = 1
            purpose = "targeted_name_change_discovery"
        elif method == "GET" and target:
            if (
                urlparse(url).scheme != "https"
                or urlparse(url).netloc != "static.cninfo.com.cn"
                or not url.startswith(CNINFO_STATIC_BASE_URL + "finalpage/")
                or not url.lower().endswith(".pdf")
            ):
                raise RuntimeError("H2_PDF_URL_SCOPE_VIOLATION")
            key = self.current_key
            count = self.pdf_count.get(key, 0)
            if count >= MAX_PDFS_PER_TARGET:
                raise RuntimeError("H2_PER_TARGET_PDF_CAP_REACHED")
            self.pdf_count[key] = count + 1
            purpose = "targeted_notice_pdf"
        else:
            raise RuntimeError("H2_NETWORK_ALLOWLIST_VIOLATION")
        if len(self.attempts) >= MAX_ATTEMPTS:
            raise RequestCapReached("H2_GLOBAL_REQUEST_CAP_REACHED")
        kwargs["allow_redirects"] = False
        response = super().request(method, url, **kwargs)
        record = {
            "attempt": len(self.attempts) + 1,
            "firm_key": target.get("firm_key", ""),
            "year": target.get("year", ""),
            "method": method,
            "url": url,
            "purpose": purpose,
            "http_status": int(response.status_code),
            "page": str(data.get("pageNum", "") or ""),
        }
        self.attempts.append(record)
        if purpose == "targeted_notice_pdf":
            self.pdf_payloads[url] = bytes(response.content)
        return response


def _read_gt():
    paths = {name: LEGAL / name for name in EXPECTED_RAW_HASHES}
    for name, path in paths.items():
        if _hash(path) != EXPECTED_RAW_HASHES[name]:
            raise RuntimeError(f"FROZEN_GT_RAW_HASH_MISMATCH:{name}")
    row_gt = pd.read_csv(
        paths["pilot_change_row_ground_truth.csv"], dtype={"firm_key": str}, keep_default_na=False
    )
    event_gt = pd.read_csv(
        paths["pilot_change_event_ground_truth.csv"], dtype={"firm_key": str}, keep_default_na=False
    )
    evidence_gt = pd.read_csv(
        paths["pilot_change_evidence_state_ground_truth.csv"],
        dtype={"firm_key": str},
        keep_default_na=False,
    )
    return row_gt, event_gt, evidence_gt


def _prepare_offline() -> tuple[
    pd.DataFrame, pd.DataFrame, pd.DataFrame, list[dict[str, object]], pd.DataFrame
]:
    if PARSER_REVISION != "issuer_scope_v3":
        raise RuntimeError("PARSER_REVISION_CHANGED")
    OUT.mkdir(parents=True, exist_ok=True)
    row_gt, event_gt, evidence_gt = _read_gt()
    keys, fingerprint = strict14_keys(row_gt, evidence_gt)
    binding = json.loads((LEGAL / "pilot_strict_gate_v3_summary.json").read_text(encoding="utf-8"))
    gt_fingerprints = verify_ground_truth_fingerprints(row_gt, event_gt, evidence_gt, binding)
    statuses = [
        pd.read_csv(LEGAL / "pilot_status.csv", dtype={"firm_key": str}, keep_default_na=False),
        pd.read_csv(LEGAL / "full_status.csv", dtype={"firm_key": str}, keep_default_na=False),
    ]
    manifest = build_source_manifest(keys, statuses)
    prior_manifest = pd.read_csv(
        OUT.parent / "strict14_v3_replay_20261001" / "strict14_source_manifest.csv",
        dtype={"firm_key": str},
        keep_default_na=False,
    )
    prior_map = {
        (str(row.firm_key), int(row.year)): str(row.source_url)
        for row in prior_manifest.itertuples(index=False)
    }
    if any(
        prior_map.get((str(row["firm_key"]), int(row["year"]))) != str(row["source_url"])
        for row in manifest
    ):
        raise RuntimeError("STRICT14_H1_MANIFEST_DRIFT_FROM_R4C1_G")
    provenance = pd.read_csv(
        OUT.parent / "strict14_v3_replay_20261001" / "source_provenance.csv",
        dtype={"firm_key": str},
        keep_default_na=False,
    )
    local = fetch_h1_sources(
        manifest,
        lambda _url: (_ for _ in ()).throw(RuntimeError("H1_NETWORK_FORBIDDEN")),
        OUT / "h1_sources",
        max_gets=0,
        local_records=provenance.to_dict("records"),
    )
    if (
        local["h1_get_count"] != 0
        or local["local_reused_count"] != 14
        or len(local["sources"]) != 14
    ):
        raise RuntimeError("STRICT14_H1_LOCAL_REUSE_GATE_FAILED")
    pd.DataFrame(local["sources"]).to_csv(
        OUT / "strict14_h1_reuse_audit.csv", index=False, encoding="utf-8-sig"
    )
    _json(
        OUT / "h1_reuse_summary.json",
        {
            "h1_reused": local["local_reused_count"],
            "h1_get_count": local["h1_get_count"],
            "source_block_count": local["source_block_count"],
            "strict14_key_fingerprint": fingerprint,
        },
    )
    parsed: list[dict[str, object]] = []
    for source in local["sources"]:
        text = Path(str(source["text_path"])).read_text(encoding="utf-8")
        values = extract_annual_report_legal_name_evidence(
            text,
            expected_year=int(source["year"]),
            source_report_title=str(source["source_report_title"]),
            source_report_year=int(source["year"]),
            source_is_official=True,
            source_is_correct_issuer=True,
            source_is_correct_year=True,
            source_is_full_annual_report=True,
        )
        parsed.append(
            {
                "firm_key": source["firm_key"],
                "year": int(source["year"]),
                "source_url": source["source_url"],
                "source_report_title": source["source_report_title"],
                "source_announcement_id": source.get("source_announcement_id", ""),
                "source_pdf_sha256": source["pdf_sha256"],
                "source_text_sha256": source["text_sha256"],
                **{f"parser_{key}": value for key, value in values.items()},
                "parser_change_flag": values["company_name_change_flag"],
                "parser_change_evidence_tier": "H1"
                if values["company_name_change_flag"] == "YES"
                else "",
                "parser_change_evidence_source": "verified_exact_h1"
                if values["company_name_change_flag"] == "YES"
                else "",
                "parser_change_evidence_url": source["source_url"]
                if values["company_name_change_flag"] == "YES"
                else "",
                "parser_change_announcement_id": source.get("source_announcement_id", "")
                if values["company_name_change_flag"] == "YES"
                else "",
            }
        )
    h1_predictions = build_complete_row_predictions(keys, pd.DataFrame(parsed))
    h1_predictions.to_csv(
        OUT / "strict14_h1_only_row_predictions.csv", index=False, encoding="utf-8-sig"
    )
    h1_candidates = canonical_candidate_rows(h1_predictions, set(keys))
    h1_candidates.to_csv(
        OUT / "strict14_h1_only_canonical_candidates.csv", index=False, encoding="utf-8-sig"
    )
    old_h2 = pd.read_csv(
        LEGAL / "pilot_name_change_h2_audit.csv", dtype={"firm_key": str}, keep_default_na=False
    ).to_dict("records")
    legacy_candidates = pd.read_csv(
        LEGAL / "pilot_change_candidate_rows.csv", dtype={"firm_key": str}, keep_default_na=False
    ).to_dict("records")
    h2_manifest = build_h2_needed_manifest(h1_predictions, old_h2, legacy_candidates)
    h2_manifest.to_csv(OUT / "strict14_h2_needed_manifest.csv", index=False, encoding="utf-8-sig")
    h1_scores = score_strict_rows(h1_predictions, row_gt, evidence_gt)
    old_candidates = h1_predictions.apply(
        lambda row: is_change_related_candidate(
            {
                **row.to_dict(),
                "company_name_change_flag": row.get("parser_company_name_change_flag", ""),
                "legal_name_previous": row.get("parser_legal_name_previous", ""),
                "legal_name_new": row.get("parser_legal_name_new", ""),
                "evidence_status": row.get("parser_evidence_status", ""),
                "failure_reason": row.get("parser_failure_reason", ""),
                "evidence_context": row.get("parser_evidence_context", ""),
            }
        ),
        axis=1,
    )
    diagnosis = {
        "parser_revision": PARSER_REVISION,
        "strict14_key_fingerprint": fingerprint,
        "gt_fingerprints_verified_unchanged": gt_fingerprints,
        "h1_reused": 14,
        "h1_get_count": 0,
        "r4c1_g_semantics": {
            "h2_updates_row_predictions": False,
            "candidate_uses_adjacent_year_name_change": False,
            "prior_evidence_state_correct": 2,
            "prior_year_end_correct": 13,
            "classification": "H1_ONLY_NON_EQUIVALENT_REPLAY_RESULT",
        },
        "canonical_semantics": {
            "candidate_builder": "_build_pilot_change_candidate_rows",
            "adjacent_year_name_change_enabled": True,
            "row_fusion_before_scoring": True,
        },
        "old_h1_only_candidate_count": int(old_candidates.sum()),
        "canonical_candidate_count_before_h2": len(h1_candidates),
        "canonical_adjacent_candidate_count": int(
            h1_candidates.get("adjacent_year_name_change", pd.Series(dtype=bool)).sum()
        ),
        "h1_only_evidence_state_correct": h1_scores["evidence_state_correct"],
        "h1_only_year_end_correct": h1_scores["year_end_correct"],
        "h2_manifest_rows": len(h2_manifest),
        "h2_manifest_independent_of_gt_answers": True,
        "existing_valid_h2_carry_count": int(h2_manifest.existing_h2_status.eq("RESOLVED_H2").sum())
        if len(h2_manifest)
        else 0,
    }
    _json(OUT / "strict14_replay_equivalence_diagnosis.json", diagnosis)
    _json(
        OUT / "offline_prepared.json",
        {
            "parser_revision": PARSER_REVISION,
            "strict14_key_fingerprint": fingerprint,
            "source_url_hash_pairs": [
                {
                    "firm_key": row["firm_key"],
                    "year": row["year"],
                    "source_url": row["source_url"],
                    "pdf_sha256": row["pdf_sha256"],
                    "text_sha256": row["text_sha256"],
                }
                for row in local["sources"]
            ],
            "h2_manifest_sha256": _hash(OUT / "strict14_h2_needed_manifest.csv"),
        },
    )
    h1_predictions.to_pickle(OUT / "h1_predictions.pkl")
    return h1_predictions, row_gt, event_gt, old_h2, h2_manifest


def _load_offline():
    prepared = json.loads((OUT / "offline_prepared.json").read_text(encoding="utf-8"))
    if (
        prepared["parser_revision"] != PARSER_REVISION
        or _hash(OUT / "strict14_h2_needed_manifest.csv") != prepared["h2_manifest_sha256"]
    ):
        raise RuntimeError("OFFLINE_MANIFEST_CHANGED_AFTER_REVIEW")
    row_gt, event_gt, evidence_gt = _read_gt()
    keys, fingerprint = strict14_keys(row_gt, evidence_gt)
    if fingerprint != prepared["strict14_key_fingerprint"]:
        raise RuntimeError("STRICT14_KEYS_DRIFT")
    h1_predictions = pd.read_pickle(OUT / "h1_predictions.pkl")
    for source in prepared["source_url_hash_pairs"]:
        match = h1_predictions.loc[
            h1_predictions.firm_key.astype(str).eq(str(source["firm_key"]))
            & pd.to_numeric(h1_predictions.year).eq(int(source["year"]))
        ].iloc[0]
        if (
            str(match.source_url) != source["source_url"]
            or str(match.source_pdf_sha256) != source["pdf_sha256"]
            or str(match.source_text_sha256) != source["text_sha256"]
        ):
            raise RuntimeError("STRICT14_H1_SOURCE_HASH_DRIFT")
    old_h2 = pd.read_csv(
        LEGAL / "pilot_name_change_h2_audit.csv", dtype={"firm_key": str}, keep_default_na=False
    ).to_dict("records")
    manifest = pd.read_csv(
        OUT / "strict14_h2_needed_manifest.csv", dtype={"firm_key": str}, keep_default_na=False
    )
    return h1_predictions, row_gt, event_gt, evidence_gt, keys, old_h2, manifest


def _run_h2_network(
    manifest: pd.DataFrame, offline_h2: list[dict[str, object]]
) -> tuple[list[dict[str, object]], GuardedH2Session, bool]:
    session = GuardedH2Session(manifest)
    client = CNINFOAnnualReportClient(
        OUT / "h2_cache", request_spacing=1.0, retries=0, session=session
    )
    records: dict[tuple[str, int], dict[str, object]] = {}
    prior_state_path = OUT / "h2_network_state.json"
    prior_audit_path = OUT / "h2_guard_audit.json"
    prior_state = (
        json.loads(prior_state_path.read_text(encoding="utf-8"))
        if prior_state_path.is_file()
        else {}
    )
    prior_audit = (
        json.loads(prior_audit_path.read_text(encoding="utf-8"))
        if prior_audit_path.is_file()
        else {}
    )
    session.attempts.extend(prior_audit.get("attempts", []))
    session.rejected.extend(prior_audit.get("rejected", []))
    for attempt in session.attempts:
        key = (str(attempt.get("firm_key", "")), int(attempt.get("year", -1) or -1))
        if attempt.get("purpose") == "targeted_name_change_discovery":
            session.discovery_count[key] = session.discovery_count.get(key, 0) + 1
        elif attempt.get("purpose") == "targeted_notice_pdf":
            session.pdf_count[key] = session.pdf_count.get(key, 0) + 1
    for old_record in prior_state.get("h2_records", []):
        key = (str(old_record.get("firm_key", "")), int(old_record.get("year", -1) or -1))
        records[key] = old_record
    original = pd.read_csv(
        LEGAL / "pilot_name_change_h2_audit.csv", dtype={"firm_key": str}, keep_default_na=False
    ).to_dict("records")
    for needed in manifest.to_dict("records"):
        key = (str(needed["firm_key"]), int(needed["year"]))
        carry = next(
            (
                record
                for record in original
                if str(record.get("firm_key")) == key[0]
                and int(float(record.get("year", -1))) == key[1]
                and str(record.get("status")) == "RESOLVED_H2"
            ),
            None,
        )
        if (
            carry
            and bool(needed.get("exact_h2_url_available"))
            and str(carry.get("previous_legal_name")) == str(needed["previous_legal_name"])
            and str(carry.get("new_legal_name")) == str(needed["new_legal_name"])
        ):
            records[key] = {
                **carry,
                "retrieval_mode": "H2_LOCAL_CARRY",
                "company_name_change_flag": carry.get("company_name_change_flag", "YES"),
                "evidence_status": carry.get("evidence_status", "CONFIRMED_NAME_CHANGE"),
                "notice_title": carry.get("notice_title", ""),
                "notice_pdf_sha256": carry.get("notice_pdf_sha256", ""),
                "notice_pdf_bytes": int(float(carry.get("notice_pdf_bytes", 0) or 0)),
                "notice_url": carry.get("notice_url", ""),
                "announcement_id": carry.get("announcement_id", ""),
                "previous_legal_name": needed["previous_legal_name"],
                "new_legal_name": needed["new_legal_name"],
                "legal_name_at_year_end": needed["new_legal_name"],
                "date_precision": carry.get("date_precision", "year"),
                "change_effective_date": carry.get("change_effective_date", ""),
                "temporal_match_uncertain": int(
                    float(carry.get("temporal_match_uncertain", 1) or 0)
                ),
            }
            continue
        if not bool(needed.get("requires_h2_discovery")):
            continue
        if session.discovery_count.get(key, 0) >= 1:
            continue
        session.current_key = key
        try:
            notices = client.list_company_name_change_announcements(
                key[0].split(":")[1], f"{key[1]}-01-01", f"{key[1] + 1}-03-31"
            )
        except (SourceBlocked, RequestCapReached, RuntimeError) as exc:
            records[key] = {
                **needed,
                "status": (
                    "SOURCE_BLOCKED"
                    if isinstance(exc, SourceBlocked)
                    else "H2_REQUEST_CAP_REACHED"
                    if isinstance(exc, RequestCapReached)
                    else "H2_GUARD_STOP"
                ),
                "failure_reason": str(exc),
                "retrieval_mode": "H2_TARGETED_DISCOVERY",
            }
            _json(
                OUT / "h2_guard_audit.json",
                {
                    "attempts": session.attempts,
                    "total_attempts": len(session.attempts),
                    "rejected": session.rejected,
                    "source_blocked": isinstance(exc, SourceBlocked),
                    "pdf_count": {
                        f"{key[0]}|{key[1]}": value for key, value in session.pdf_count.items()
                    },
                    "discovery_count": {
                        f"{key[0]}|{key[1]}": value
                        for key, value in session.discovery_count.items()
                    },
                },
            )
            return list(records.values()), session, isinstance(exc, SourceBlocked)
        resolved = None
        failures: list[str] = []
        for notice in notices:
            try:
                text, metadata = client.extract_pdf_text_with_metadata(str(notice["source_url"]))
            except SourceBlocked as exc:
                records[key] = {
                    **needed,
                    "status": "SOURCE_BLOCKED",
                    "failure_reason": str(exc),
                    "retrieval_mode": "H2_TARGETED_NOTICE",
                }
                _json(
                    OUT / "h2_guard_audit.json",
                    {
                        "attempts": session.attempts,
                        "total_attempts": len(session.attempts),
                        "rejected": session.rejected,
                        "source_blocked": True,
                        "pdf_count": {
                            f"{key[0]}|{key[1]}": value for key, value in session.pdf_count.items()
                        },
                        "discovery_count": {
                            f"{key[0]}|{key[1]}": value
                            for key, value in session.discovery_count.items()
                        },
                    },
                )
                return list(records.values()), session, True
            except (OSError, RuntimeError, ValueError, TimeoutError, RequestCapReached) as exc:
                failures.append(f"{type(exc).__name__}:{str(exc)[:160]}")
                if isinstance(exc, RequestCapReached):
                    break
                continue
            evidence = extract_company_name_change_announcement(
                text,
                expected_year=key[1],
                previous_legal_name=str(needed["previous_legal_name"]),
                new_legal_name=str(needed["new_legal_name"]),
                announcement_date=str(notice.get("announcement_date", "")),
            )
            pdf = session.pdf_payloads[str(notice["source_url"])]
            stem = hashlib.sha256(f"{key[0]}|{key[1]}|{notice['source_url']}".encode()).hexdigest()[
                :24
            ]
            pdf_path, text_path = (
                OUT / "h2_sources" / f"{stem}.pdf",
                OUT / "h2_sources" / f"{stem}.txt",
            )
            pdf_path.parent.mkdir(parents=True, exist_ok=True)
            pdf_path.write_bytes(pdf)
            text_path.write_text(text, encoding="utf-8")
            source = {
                **needed,
                **evidence,
                "status": evidence.get("evidence_status", ""),
                "notice_title": str(notice.get("title", "")),
                "notice_url": str(notice["source_url"]),
                "announcement_id": str(notice.get("announcement_id", "")),
                "notice_pdf_sha256": metadata["pdf_sha256"],
                "notice_pdf_bytes": metadata["pdf_bytes"],
                "retrieval_mode": "H2_BOUNDED_NETWORK",
                "http_status": metadata["http_status"],
                "extraction_method": metadata["extraction_method"],
                "text_chars": metadata["text_chars"],
                "pdf_path": str(pdf_path),
                "text_path": str(text_path),
                "previous_legal_name": needed["previous_legal_name"],
                "new_legal_name": needed["new_legal_name"],
            }
            if evidence.get("evidence_status") in {"CONFIRMED_NAME_CHANGE", "CONFIRMED_NO_CHANGE"}:
                source["status"] = "RESOLVED_H2"
                resolved = source
                break
            failures.append(f"{notice.get('title', '')}:PAIR_NOT_CONFIRMED")
        records[key] = resolved or {
            **needed,
            "status": "H2_SOURCE_UNAVAILABLE",
            "failure_reason": ";".join(failures) or "no_notice_confirmed_expected_name_pair",
            "retrieval_mode": "H2_BOUNDED_NETWORK",
            "discovery_notice_count": len(notices),
        }
    pd.DataFrame(session.attempts).to_csv(
        OUT / "h2_request_audit.csv", index=False, encoding="utf-8-sig"
    )
    _json(
        OUT / "h2_guard_audit.json",
        {
            "attempts": session.attempts,
            "total_attempts": len(session.attempts),
            "rejected": session.rejected,
            "source_blocked": False,
            "pdf_count": {f"{key[0]}|{key[1]}": value for key, value in session.pdf_count.items()},
            "discovery_count": {
                f"{key[0]}|{key[1]}": value for key, value in session.discovery_count.items()
            },
        },
    )
    rows = list(records.values())
    pd.DataFrame(rows).to_csv(OUT / "strict14_h2_evidence.csv", index=False, encoding="utf-8-sig")
    _write_notice_fetch_audit(session, rows)
    return rows, session, False


def _write_notice_fetch_audit(session: GuardedH2Session, records: list[dict[str, object]]) -> None:
    resolved_by_url = {
        str(row.get("notice_url", "")): row for row in records if row.get("notice_url")
    }
    details = []
    for attempt in session.attempts:
        if attempt.get("purpose") != "targeted_notice_pdf":
            continue
        key = f"{attempt['firm_key']}|{attempt['year']}|{attempt['url']}"
        stem = hashlib.sha256(key.encode()).hexdigest()[:24]
        pdf_path = OUT / "h2_sources" / f"{stem}.pdf"
        text_path = OUT / "h2_sources" / f"{stem}.txt"
        pdf = pdf_path.read_bytes() if pdf_path.is_file() else b""
        text = text_path.read_text(encoding="utf-8") if text_path.is_file() else ""
        resolved = resolved_by_url.get(str(attempt["url"]), {})
        first_lines = [line.strip() for line in text.splitlines() if line.strip()][:6]
        details.append(
            {
                **attempt,
                "title": str(resolved.get("notice_title", "")),
                "pdf_bytes": len(pdf),
                "pdf_sha256": hashlib.sha256(pdf).hexdigest() if pdf else "",
                "text_path": str(text_path) if text_path.is_file() else "",
                "text_chars": len(text),
                "text_extraction_status": "EXTRACTED"
                if text_path.is_file() and text
                else "FAILED_OR_NOT_SAVED",
                "text_title_excerpt": " | ".join(first_lines)[:500],
                "evidence_status": str(resolved.get("evidence_status", "NOT_CONFIRMED")),
            }
        )
    pd.DataFrame(details).to_csv(OUT / "h2_notice_fetches.csv", index=False, encoding="utf-8-sig")


def _finalize(
    h1: pd.DataFrame,
    row_gt: pd.DataFrame,
    event_gt: pd.DataFrame,
    evidence_gt: pd.DataFrame,
    keys: list[tuple[str, int]],
    h2_records: list[dict[str, object]],
    session: GuardedH2Session,
    source_blocked: bool,
) -> dict[str, object]:
    fused = apply_resolved_h2_to_rows(h1, h2_records)
    fused.to_csv(OUT / "strict14_fused_row_predictions.csv", index=False, encoding="utf-8-sig")
    from scripts.run_cninfo_legal_name_recovery_20260929 import (
        _build_frozen_row_predictions,
        _build_pilot_change_artifacts,
    )

    mapping = {
        "parser_company_name_change_flag": "company_name_change_flag",
        "parser_legal_name_previous": "legal_name_previous",
        "parser_legal_name_new": "legal_name_new",
        "parser_change_effective_date": "change_effective_date",
        "parser_date_precision": "date_precision",
        "parser_legal_name_at_year_end": "legal_name_at_year_end",
        "parser_legal_name_current_in_report": "legal_name_current_in_report",
        "parser_evidence_status": "evidence_status",
        "parser_failure_reason": "failure_reason",
        "parser_evidence_context": "evidence_context",
        "parser_change_evidence_tier": "change_evidence_tier",
        "parser_change_evidence_source": "change_evidence_source",
        "parser_change_evidence_url": "change_evidence_url",
        "parser_change_announcement_id": "change_announcement_id",
        "parser_change_pdf_sha256": "change_pdf_sha256",
        "parser_source_report_title": "source_report_title",
    }
    audit = (
        fused.drop(columns=["parser_source_report_title"], errors="ignore")
        .rename(columns=mapping)
        .drop(columns=["source_url"], errors="ignore")
        .copy()
    )
    statuses = fused[["firm_key", "year", "source_url"]].copy()
    candidate, events, canonical_rows = _build_pilot_change_artifacts(audit, statuses, set(keys))
    rows = _build_frozen_row_predictions(audit, candidate, row_gt[["firm_key", "year"]].copy())
    candidate.to_csv(OUT / "strict14_fused_candidate_rows.csv", index=False, encoding="utf-8-sig")
    events.to_csv(OUT / "strict14_fused_event_predictions.csv", index=False, encoding="utf-8-sig")
    rows.to_csv(OUT / "strict14_frozen_row_predictions.csv", index=False, encoding="utf-8-sig")
    h1_scores = score_strict_rows(h1, row_gt, evidence_gt)
    fused_scores = score_strict_rows(rows, row_gt, evidence_gt)
    event_scores = score_events(events, event_gt)
    frozen45 = _run_frozen45()
    from scripts.diagnose_cnipa_full_gaps_20260930 import _hash_cache_tree

    cache_now = _hash_cache_tree(LEGAL / "cache")
    cache_baseline = json.loads(
        (ROOT / "results/cnipa_full_gap_diagnosis/baseline_summary.json").read_text(
            encoding="utf-8"
        )
    )
    expected_cache_sha = str(cache_baseline["full_cache_tree_sha256_before"])
    protected_before = cache_baseline["protected_sha256_before"]
    expected_full_status_sha = str(
        protected_before["results\\cnipa_legal_name_recovery\\full_status.csv"]
    )
    expected_full_state_sha = str(
        protected_before["results\\cnipa_legal_name_recovery\\full_run_state.json"]
    )
    full_status_sha = _hash(LEGAL / "full_status.csv")
    full_state_sha = _hash(LEGAL / "full_run_state.json")
    if (
        cache_now["sha256"] != expected_cache_sha
        or full_status_sha != expected_full_status_sha
        or full_state_sha != expected_full_state_sha
    ):
        raise RuntimeError("PROTECTED_FULL_STATE_OR_CACHE_HASH_CHANGED")
    gt_h2 = event_gt.loc[
        event_gt.get("source_evidence_tier", pd.Series("", index=event_gt.index))
        .astype(str)
        .str.contains("H2", case=False)
    ]
    manifest_keys = {
        (str(x.get("firm_key", "")), int(x.get("year", -1)))
        for x in pd.read_csv(
            OUT / "strict14_h2_needed_manifest.csv", dtype={"firm_key": str}
        ).to_dict("records")
    }
    predicted_keys = {
        (str(x.get("firm_key", "")), int(x.get("year", -1)))
        for x in events.to_dict("records")
        if str(x.get("evidence_tier", "")) == "H1"
    }
    underived = 0
    for item in gt_h2.to_dict("records"):
        match = re.match(r"^(20\d{2})", str(item.get("review_effective_date", "")))
        if match:
            event_key = (str(item.get("firm_key", "")), int(match.group(1)))
            if event_key not in manifest_keys and event_key not in predicted_keys:
                underived += 1
    unresolved_h2 = sum(str(row.get("status", "")) not in {"RESOLVED_H2"} for row in h2_records)
    incomplete = bool(source_blocked or unresolved_h2 or underived)
    gate_status = classify_strict14_gate(
        fused_evidence_correct=fused_scores["evidence_state_correct"],
        fused_year_end_correct=fused_scores["year_end_correct"],
        event_metrics=event_scores,
        unresolved_candidate_count=fused_scores["unresolved_candidate_count"],
        unresolved_event_count=event_scores["unresolved_event_count"],
        source_evidence_complete=not incomplete,
        h2_query_pair_underived_count=underived,
    )
    prior_g1 = json.loads(
        (OUT.parent / "strict14_v3_replay_20261001" / "strict14_v3_summary.json").read_text(
            encoding="utf-8"
        )
    )
    summary = {
        "parser_revision": PARSER_REVISION,
        "strict14_count": 14,
        "h1_reused": 14,
        "h1_get_count": 0,
        "r4c1_g_candidate_rows_non_equivalent": prior_g1["candidate_rows"],
        "canonical_candidate_rows_before_h2": len(canonical_candidate_rows(h1, set(keys))),
        "canonical_candidate_rows_after_h2": len(candidate),
        "canonical_adjacent_year_candidates": int(
            candidate.get("adjacent_year_name_change", pd.Series(dtype=bool)).sum()
        ),
        "h2_needed_manifest_rows": len(manifest_keys),
        "h2_targets_independent_of_gt_answers": True,
        "existing_h2_carry_count": sum(
            str(row.get("retrieval_mode", "")) == "H2_LOCAL_CARRY" for row in h2_records
        ),
        "h2_exact_url_fetch_count": 0,
        "h2_discovery_query_count": sum(session.discovery_count.values()),
        "h2_notice_pdf_count": sum(session.pdf_count.values()),
        "h2_guarded_attempts": len(session.attempts),
        "h2_scope_rejection_count": len(
            json.loads((OUT / "h2_guard_audit.json").read_text(encoding="utf-8")).get(
                "rejected", []
            )
        ),
        "h2_source_blocked": source_blocked,
        "independently_resolved_h2_count": sum(
            str(row.get("status", "")) == "RESOLVED_H2" for row in h2_records
        ),
        "h2_query_pair_underived_count": underived,
        "h1_only_evidence_state_correct": h1_scores["evidence_state_correct"],
        "h1_only_evidence_state_denominator": 14,
        "fused_evidence_state_correct": fused_scores["evidence_state_correct"],
        "fused_evidence_state_denominator": 14,
        "h1_only_year_end_correct": h1_scores["year_end_correct"],
        "h1_only_year_end_denominator": 14,
        "fused_year_end_correct": fused_scores["year_end_correct"],
        "fused_year_end_denominator": 14,
        "row_unresolved_candidate_count": fused_scores["unresolved_candidate_count"],
        "event_predictions_count": len(events),
        **event_scores,
        "strict_gate_status": gate_status,
        "frozen45": frozen45,
        "gt_raw_hashes": EXPECTED_RAW_HASHES,
        "gt_unchanged": all(
            _hash(LEGAL / name) == digest for name, digest in EXPECTED_RAW_HASHES.items()
        ),
        "full_status_sha256": full_status_sha,
        "full_run_state_sha256": full_state_sha,
        "full_cache_sha256": cache_now["sha256"],
        "full_cache_files": cache_now["file_count"],
        "full_cache_bytes": cache_now["byte_count"],
        "full_data_changed": bool(
            full_status_sha != expected_full_status_sha
            or full_state_sha != expected_full_state_sha
            or cache_now["sha256"] != expected_cache_sha
        ),
        "full_wide_reparse_blocked": "FULL_WIDE_REPARSE_BLOCKED"
        in (ROOT / "scripts/run_cninfo_legal_name_recovery_20260929.py").read_text(
            encoding="utf-8"
        ),
        "network_h1_requests": 0,
        "network_h2_requests": len(session.attempts),
        "patent_system_accessed": False,
        "300365_2020_h1_flag": str(
            h1.loc[
                h1.firm_key.astype(str).eq("SZSE:300365:2014-01-23")
                & pd.to_numeric(h1.year).eq(2020),
                "parser_company_name_change_flag",
            ].iloc[0]
        ),
        "300365_2021_h1_flag": str(
            h1.loc[
                h1.firm_key.astype(str).eq("SZSE:300365:2014-01-23")
                & pd.to_numeric(h1.year).eq(2021),
                "parser_company_name_change_flag",
            ].iloc[0]
        ),
    }
    check365 = row_gt.loc[
        row_gt.firm_key.astype(str).eq("SZSE:300365:2014-01-23"),
        ["firm_key", "year", "review_legal_name_at_year_end"],
    ].merge(
        h1.loc[
            h1.firm_key.astype(str).eq("SZSE:300365:2014-01-23"),
            [
                "firm_key",
                "year",
                "parser_legal_name_at_year_end",
                "parser_company_name_change_flag",
            ],
        ],
        on=["firm_key", "year"],
        how="left",
    )
    summary["300365_both_year_end_names_correct"] = bool(
        check365.parser_legal_name_at_year_end.astype(str)
        .eq(check365.review_legal_name_at_year_end.astype(str))
        .all()
    )
    _json(OUT / "strict14_g2_summary.json", summary)
    return summary


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--phase", choices=("offline", "network", "finalize"), required=True)
    args = parser.parse_args()
    if args.phase == "offline":
        h1, _row, _event, _old, manifest = _prepare_offline()
        print(f"OFFLINE_READY H1=14 H1_GET=0 H2_TARGETS={len(manifest)}")
        print(manifest.to_string(index=False))
        return 0
    h1, row_gt, event_gt, evidence_gt, keys, old_h2, manifest = _load_offline()
    if args.phase == "network":
        records, session, blocked = _run_h2_network(manifest, old_h2)
        _json(
            OUT / "h2_network_state.json",
            {"h2_records": records, "attempts": session.attempts, "source_blocked": blocked},
        )
        _write_notice_fetch_audit(session, records)
        print(
            f"H2_NETWORK_DONE targets={len(manifest)} "
            f"attempts={len(session.attempts)} source_blocked={blocked}"
        )
        return 0
    state = json.loads((OUT / "h2_network_state.json").read_text(encoding="utf-8"))
    session = GuardedH2Session(manifest)
    session.attempts = state["attempts"]
    guard = json.loads((OUT / "h2_guard_audit.json").read_text(encoding="utf-8"))
    session.discovery_count = {
        tuple(k.rsplit("|", 1)): int(v) for k, v in guard.get("discovery_count", {}).items()
    }
    session.pdf_count = {
        tuple(k.rsplit("|", 1)): int(v) for k, v in guard.get("pdf_count", {}).items()
    }
    summary = _finalize(
        h1,
        row_gt,
        event_gt,
        evidence_gt,
        keys,
        state["h2_records"],
        session,
        bool(state["source_blocked"]),
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
