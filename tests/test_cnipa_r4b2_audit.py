from __future__ import annotations

import hashlib
import json

import pandas as pd
import pytest

from src.cnipa_r4b2_audit import (
    R4B2_ADDITIONAL_GUARDED_ATTEMPT_CAP,
    R4B_HISTORICAL_GUARDED_ATTEMPTS,
    RequestAuditLog,
    build_provenance_mapping,
    classify_index_result,
    classify_source_identity,
    cumulative_guarded_attempts,
    validate_r4b2_offline_gate,
)


def test_r4b_historical_attempts_are_immutable_and_cumulative_is_separate():
    assert R4B_HISTORICAL_GUARDED_ATTEMPTS == 120
    assert R4B2_ADDITIONAL_GUARDED_ATTEMPT_CAP == 120
    assert cumulative_guarded_attempts(120, 37) == 157
    with pytest.raises(ValueError, match="R4B2_ATTEMPT_CAP_EXCEEDED"):
        cumulative_guarded_attempts(120, 121)


def test_index_page_cap_is_not_misreported_as_complete_no_result():
    assert classify_index_result(4, 4, 0) == (
        "INDEX_COMPLETE_RESULT_SET_NO_VALID_REPORT"
    )
    assert classify_index_result(4, 7, 0) == "INDEX_PAGE_CAP_REACHED_UNRESOLVED"
    assert classify_index_result(2, 7, 1) == "INDEX_VALID_REPORT_FOUND"


def test_request_audit_writes_one_terminal_event_without_sensitive_fields(tmp_path):
    path = tmp_path / "request_audit.jsonl"
    audit = RequestAuditLog(path, epoch="R4B2")
    audit.record(
        sequence=1,
        firm_key="SZSE:000001:1991-04-03",
        year=2022,
        action="TARGETED_CNINFO_INDEX_LOOKUP",
        method="POST",
        url="https://www.cninfo.com.cn/new/hisAnnouncement/query?page=2",
        attempt_started_at="2026-10-01T10:00:00+08:00",
        transport_called=True,
        response_received=True,
        http_status=200,
        index_page=2,
        exception_type="",
        exception_message_short="",
        source_blocked=False,
        budget_consumed=True,
    )
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    assert len(rows) == 1
    assert rows[0]["terminal_outcome"] == "HTTP_RESPONSE"
    assert rows[0]["host"] == "www.cninfo.com.cn"
    assert rows[0]["index_page"] == 2
    assert rows[0]["budget_consumed"] is True
    assert "headers" not in rows[0] and "cookies" not in rows[0]


def test_request_audit_records_transport_exception_as_terminal(tmp_path):
    path = tmp_path / "request_audit.jsonl"
    audit = RequestAuditLog(path, epoch="R4B2")
    audit.record(
        sequence=2,
        firm_key="SZSE:000001:1991-04-03",
        year=2022,
        action="REFETCH_EXACT_H1_URL",
        method="GET",
        url="https://static.cninfo.com.cn/a.pdf",
        attempt_started_at="2026-10-01T10:00:00+08:00",
        transport_called=True,
        response_received=False,
        http_status=None,
        index_page=None,
        exception_type="Timeout",
        exception_message_short="timed out",
        source_blocked=False,
        budget_consumed=True,
    )
    row = json.loads(path.read_text(encoding="utf-8").splitlines()[0])
    assert row["terminal_outcome"] == "TRANSPORT_EXCEPTION"
    assert row["response_received"] is False
    assert row["budget_consumed"] is True


def test_provenance_mapping_uses_acquisition_key_not_parser_name(tmp_path):
    evidence = tmp_path / "evidence" / "one.pdf"
    evidence.parent.mkdir()
    evidence.write_bytes(b"%PDF-evidence")
    evidence.with_suffix(".txt").write_text("official report text", encoding="utf-8")
    pdf_hash = hashlib.sha256(evidence.read_bytes()).hexdigest()
    predictions = pd.DataFrame(
        [
            {
                "firm_key": "SSE:600001:2000-01-01",
                "year": 2022,
                "_evidence_path": "evidence/one.pdf",
                "pdf_sha256": pdf_hash,
                "source_url_requested": "https://static.cninfo.com.cn/report.pdf",
                "source_url_final": "https://static.cninfo.com.cn/report.pdf",
                "source_title": "2022年年度报告",
                "source_announcement_id": "123",
                "planned_action": "REFETCH_EXACT_H1_URL",
                "acquisition_action": "EXACT_H1",
                "http_status": "200",
                "parser_legal_name_at_year_end": "a parser-invented name",
            }
        ]
    )
    manifest = pd.DataFrame(
        [{"firm_key": "SSE:600001:2000-01-01", "year": 2022}]
    )

    mapping = build_provenance_mapping(predictions, manifest, tmp_path)

    assert len(mapping) == 1
    assert mapping[0]["firm_key"] == "SSE:600001:2000-01-01"
    assert mapping[0]["mapping_source"] == "pilot_predictions_key_path_hash"
    assert mapping[0]["mapping_status"] == "MAPPED_TO_FROZEN_KEY"
    assert mapping[0]["source_announcement_id"] == "123"


def test_provenance_mapping_blocks_missing_evidence_path(tmp_path):
    predictions = pd.DataFrame(
        [{"firm_key": "SSE:600001:2000-01-01", "year": 2022, "pdf_sha256": "abc"}]
    )
    manifest = pd.DataFrame(
        [{"firm_key": "SSE:600001:2000-01-01", "year": 2022}]
    )

    with pytest.raises(ValueError, match="MAPPING_UNRESOLVED"):
        build_provenance_mapping(predictions, manifest, tmp_path)


@pytest.mark.parametrize(
    ("official", "issuer", "year", "full", "title", "expected"),
    [
        (True, True, True, True, "2022年年度报告全文", "VALID_FULL_H1"),
        (True, True, True, False, "2022年年度报告摘要", "ANNUAL_REPORT_SUMMARY"),
        (True, False, True, True, "2021年年度报告", "WRONG_ISSUER"),
        (True, True, False, True, "2021年年度报告", "WRONG_YEAR"),
        (False, True, True, True, "2022年年度报告", "SOURCE_IDENTITY_UNRESOLVED"),
    ],
)
def test_source_identity_classification_is_mutually_exclusive(
    official, issuer, year, full, title, expected
):
    assert classify_source_identity(
        official=official,
        correct_issuer=issuer,
        correct_year=year,
        full_annual_report=full,
        source_title=title,
    ) == expected


def test_summary_classification_uses_report_front_matter_when_title_is_ambiguous():
    assert classify_source_identity(
        official=True,
        correct_issuer=True,
        correct_year=True,
        full_annual_report=False,
        source_title="2022年年度报告",
        source_text="瀚蓝环境股份有限公司 2022 年年度报告摘要",
    ) == "ANNUAL_REPORT_SUMMARY"


def test_network_gate_requires_exact_offline_provenance_and_review_pass():
    summary = {
        "manifest_sha256": "30C47523292A96F19EDF889ACDD0851B26887B08D60B91F06E14EF2D9420F78C",
        "frame_fingerprint": "8e26547eda6d24ff78af39e8bf652128809d57b67414655495fba50b130bc2fb",
        "key_fingerprint": "96D4FF6735B18707129CE2C4F485F0D22C3547F28A0A9DAF1C164330F4757861",
        "offline_network_requests": 0,
        "r4b2_guarded_attempts": 0,
        "mapped_to_frozen_keys": 30,
        "mapping_unresolved": 0,
        "valid_full_h1_count": 27,
        "source_identity_distribution": {
            "VALID_FULL_H1": 27,
            "ANNUAL_REPORT_SUMMARY": 2,
            "WRONG_ISSUER": 1,
        },
    }
    mapping = pd.DataFrame({"mapping_status": ["MAPPED_TO_FROZEN_KEY"] * 30})
    sources = pd.DataFrame(
        {
            "classification": ["VALID_FULL_H1"] * 27
            + ["ANNUAL_REPORT_SUMMARY"] * 2
            + ["WRONG_ISSUER"]
        }
    )
    reviews = pd.DataFrame({"review_status_review": ["PASS"] * 27})

    assert validate_r4b2_offline_gate(summary, mapping, sources, reviews) is True

    summary["offline_network_requests"] = 1
    with pytest.raises(ValueError, match="R4B2_OFFLINE_GATE_FAILED"):
        validate_r4b2_offline_gate(summary, mapping, sources, reviews)
