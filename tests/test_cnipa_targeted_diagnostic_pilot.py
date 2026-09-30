from __future__ import annotations

import pandas as pd
import pytest
import requests

from scripts import run_cnipa_targeted_diagnostic_pilot_20260930 as pilot


def test_frozen_manifest_rejects_duplicate_or_out_of_target_keys():
    frame = pd.DataFrame(
        [
            {
                "firm_key": "F1",
                "year": 2021,
                "diagnosis_group": "GAP",
                "subfamily": "GAP_A",
                "risk_tier": "NOT_APPLICABLE",
                "proposed_network_action": "MANUAL_SOURCE_REVIEW",
            },
            {
                "firm_key": "F1",
                "year": 2021,
                "diagnosis_group": "GAP",
                "subfamily": "GAP_A",
                "risk_tier": "NOT_APPLICABLE",
                "proposed_network_action": "MANUAL_SOURCE_REVIEW",
            },
        ]
    )
    with pytest.raises(ValueError, match="DUPLICATE_OR_OUT_OF_TARGET_PILOT_KEY"):
        pilot.validate_frozen_manifest(frame, {("F1", 2021)}, expected_rows=2, expected_firms=1)


def test_exact_h1_and_negative_control_actions_never_plan_index_search():
    exact = pilot.plan_acquisition_action(
        "REFETCH_EXACT_H1_URL", "https://static.cninfo.com.cn/report.pdf", False
    )
    manual = pilot.plan_acquisition_action(
        "MANUAL_SOURCE_REVIEW", "https://static.cninfo.com.cn/report.pdf", False
    )
    control = pilot.plan_acquisition_action("NO_NETWORK_NEGATIVE_CONTROL", "", False)
    assert exact == {"mode": "EXACT_H1", "url": "https://static.cninfo.com.cn/report.pdf"}
    assert manual["mode"] == "EXACT_H1_FOR_MANUAL_REVIEW"
    assert control == {"mode": "LOCAL_ONLY", "url": ""}
    with pytest.raises(ValueError, match="ACTION_SCOPE_VIOLATION"):
        pilot.plan_acquisition_action(
            "REFETCH_EXACT_H1_URL", "https://example.org/report.pdf", False
        )


def test_index_candidate_requires_expected_issuer_code_year_full_report_and_official_url():
    candidate = {
        "stock_code": "600001",
        "report_year": 2022,
        "title": "甲股份有限公司2022年年度报告全文",
        "announcement_id": "123",
        "source_url": "https://static.cninfo.com.cn/2023/a.pdf",
        "source_type": "official_annual_report",
        "source_tier": "H1",
    }
    assert pilot.validate_index_candidate(candidate, stock_code="600001", report_year=2022)
    assert not pilot.validate_index_candidate(candidate, stock_code="600002", report_year=2022)
    assert not pilot.validate_index_candidate(candidate, stock_code="600001", report_year=2021)
    assert not pilot.validate_index_candidate(
        {**candidate, "title": "甲股份有限公司2022年年度报告摘要"},
        stock_code="600001",
        report_year=2022,
    )
    assert not pilot.validate_index_candidate(
        {**candidate, "source_url": "https://example.org/a.pdf"},
        stock_code="600001",
        report_year=2022,
    )


class FakeResponse:
    def __init__(self, status_code=200, text="ok"):
        self.status_code = status_code
        self.text = text


def test_request_guard_enforces_one_second_spacing_and_hard_cap():
    now = [0.0]
    waits = []
    calls = []
    guard = pilot.RequestGuard(
        state={"request_count": 0},
        persist=lambda: None,
        min_interval=1.0,
        max_requests=2,
        monotonic=lambda: now[0],
        sleep=lambda delay: (waits.append(delay), now.__setitem__(0, now[0] + delay)),
    )

    def transport(method, url, **kwargs):
        calls.append((method, url))
        return FakeResponse()

    guard.perform(transport, "GET", "https://static.cninfo.com.cn/a.pdf")
    guard.perform(transport, "GET", "https://static.cninfo.com.cn/b.pdf")
    assert waits == [1.0]
    assert len(calls) == 2
    with pytest.raises(pilot.RequestCapReached):
        guard.perform(transport, "GET", "https://static.cninfo.com.cn/c.pdf")
    assert len(calls) == 2


def test_request_guard_records_source_block_and_refuses_every_later_request():
    state = {"request_count": 0}
    guard = pilot.RequestGuard(state=state, persist=lambda: None, min_interval=1, max_requests=10)

    def transport(*_args, **_kwargs):
        return FakeResponse(403, "Forbidden")

    with pytest.raises(pilot.SourceBlocked):
        guard.perform(transport, "GET", "https://static.cninfo.com.cn/a.pdf")
    assert state["source_blocked"] is True
    assert state["blocked_http_status"] == 403
    with pytest.raises(pilot.SourceBlocked):
        guard.perform(transport, "GET", "https://static.cninfo.com.cn/b.pdf")
    assert state["request_count"] == 1


def test_resume_requires_identical_manifest_and_evidence_hash(tmp_path):
    with pytest.raises(ValueError, match="RESUME_MANIFEST_FINGERPRINT_MISMATCH"):
        pilot.verify_resume_fingerprints({"manifest_fingerprint": "old"}, "new")
    evidence = tmp_path / "evidence.pdf"
    evidence.write_bytes(b"official PDF fixture")
    item = {
        "completed": True,
        "manifest_fingerprint": "same",
        "evidence_path": "evidence.pdf",
        "evidence_sha256": pilot.sha256_bytes(b"official PDF fixture"),
    }
    assert pilot.should_skip_completed_row(item, "same", tmp_path)
    evidence.write_bytes(b"changed fixture")
    assert not pilot.should_skip_completed_row(item, "same", tmp_path)


def test_review_template_does_not_copy_prediction_values():
    predictions = pd.DataFrame(
        [
            {
                "firm_key": "F1",
                "year": 2022,
                "parser_legal_name_current": "parser output",
                "parser_evidence_status": "CONFIRMED_NO_CHANGE",
            }
        ]
    )
    template = pilot.build_review_template(predictions)
    assert template.loc[0, "review_status"] == "PENDING"
    assert template.loc[0, "review_legal_name_at_year_end"] == ""
    assert template.loc[0, "review_change_evidence_state"] == ""
    assert template.loc[0, "reviewer_evidence_excerpt"] == ""


def test_source_metrics_exclude_controls_unresolved_and_blocked_rows():
    predictions = pd.DataFrame(
        [
            {
                "firm_key": "A",
                "year": 2020,
                "parser_legal_name_current": "A Inc",
                "parser_legal_name_at_year_end": "A Inc",
                "parser_evidence_status": "NO",
            },
            {
                "firm_key": "B",
                "year": 2020,
                "parser_legal_name_current": "B Inc",
                "parser_legal_name_at_year_end": "B Inc",
                "parser_evidence_status": "NO",
            },
            {
                "firm_key": "C",
                "year": 2020,
                "parser_legal_name_current": "C Inc",
                "parser_legal_name_at_year_end": "C Inc",
                "parser_evidence_status": "NO",
            },
            {
                "firm_key": "D",
                "year": 2020,
                "parser_legal_name_current": "D Inc",
                "parser_legal_name_at_year_end": "D Inc",
                "parser_evidence_status": "NO",
            },
        ]
    )
    review = pd.DataFrame(
        [
            {
                "firm_key": "A",
                "year": 2020,
                "review_status": "PASS",
                "source_is_official": "True",
                "source_is_correct_issuer": "True",
                "source_is_correct_year": "True",
                "source_is_full_annual_report": "True",
                "review_legal_name_at_year_end": "A Inc",
                "review_change_evidence_state": "NO",
            },
            {"firm_key": "B", "year": 2020, "review_status": "LOCAL_CONTROL_ONLY"},
            {"firm_key": "C", "year": 2020, "review_status": "SOURCE_UNRESOLVED"},
            {"firm_key": "D", "year": 2020, "review_status": "SOURCE_BLOCKED"},
        ]
    )
    result = pilot.calculate_source_grounded_metrics(predictions, review)
    assert result["review_denominator"] == 1
    assert result["parser_issuer_name_accuracy"] == 1.0
    assert result["parser_year_end_name_accuracy"] == 1.0
    assert result["parser_evidence_state_accuracy"] == 1.0
    assert result["excluded_counts"] == {
        "LOCAL_CONTROL_ONLY": 1,
        "SOURCE_UNRESOLVED": 1,
        "SOURCE_BLOCKED": 1,
        "OTHER_OR_PENDING": 0,
    }


def test_outcome_requires_independent_review_and_distinguishes_correction_from_change():
    base = {
        "review_status": "PASS",
        "source_is_official": True,
        "source_is_correct_issuer": True,
        "source_is_correct_year": True,
        "source_is_full_annual_report": True,
        "old_legal_name_at_year_end": "Old Ltd",
        "parser_legal_name_at_year_end": "New Ltd",
        "review_legal_name_at_year_end": "New Ltd",
        "old_evidence_status": "NO",
        "parser_evidence_status": "YES",
        "review_change_evidence_state": "YES",
    }
    assert pilot.classify_diagnostic_outcome(base) == "CORRECTED_BY_CURRENT_PARSER"
    assert (
        pilot.classify_diagnostic_outcome({**base, "parser_legal_name_at_year_end": "Wrong Ltd"})
        == "CURRENT_PARSER_STILL_WRONG"
    )
    assert (
        pilot.classify_diagnostic_outcome({**base, "review_status": "LOCAL_CONTROL_ONLY"})
        == "UNRESOLVED"
    )


def test_mixed_failure_mechanisms_require_more_diagnostic_pilot():
    assert pilot.recommend_repair_mode({"PARSER_LAYOUT_GAP", "SOURCE_WRONG_REPORT"}) == (
        "MORE_DIAGNOSTIC_REQUIRED"
    )
    assert pilot.recommend_repair_mode({"PARSER_LAYOUT_GAP"}) == "PARSER_FIX_REQUIRED"


def test_frozen_manifest_exact_identity_and_action_counts():
    frame = pd.read_csv(pilot.MANIFEST_PATH, dtype={"firm_key": str}, keep_default_na=False)
    targets = pd.read_csv(pilot.FULL_STATUS_PATH, dtype={"firm_key": str})
    primary = set(
        zip(targets.firm_key.astype(str), pd.to_numeric(targets.year).astype(int), strict=True)
    )
    result = pilot.validate_frozen_manifest(
        frame,
        primary,
        expected_rows=94,
        expected_firms=86,
        expected_action_counts={
            "REFETCH_EXACT_H1_URL": 50,
            "TARGETED_CNINFO_INDEX_LOOKUP": 20,
            "MANUAL_SOURCE_REVIEW": 14,
            "NO_NETWORK_NEGATIVE_CONTROL": 10,
        },
    )
    assert result["key_fingerprint"].upper() == pilot.EXPECTED_KEY_FINGERPRINT
    assert pilot.sha256_file(pilot.MANIFEST_PATH).upper() == pilot.EXPECTED_MANIFEST_SHA256
    assert pilot.canonical._frame_fingerprint(frame) == pilot.EXPECTED_FRAME_FINGERPRINT


def test_manual_without_exact_cached_pdf_is_local_only_and_never_h2():
    assert pilot.plan_acquisition_action("MANUAL_SOURCE_REVIEW", "", False) == {
        "mode": "LOCAL_ONLY",
        "url": "",
    }


def test_source_block_challenge_page_stops_even_when_http_200():
    state = {"request_count": 0}
    guard = pilot.RequestGuard(state=state, persist=lambda: None)

    def transport(*_args, **_kwargs):
        return FakeResponse(200, "请完成验证 captcha")

    with pytest.raises(pilot.SourceBlocked):
        guard.perform(transport, "GET", "https://www.cninfo.com.cn/a.pdf")
    assert state["source_blocked"] is True
    assert state["request_count"] == 1


def test_pdf_body_is_not_scanned_as_challenge_text():
    response = FakeResponse(200, "captcha")
    response.content = b"%PDF-1.7"
    guard = pilot.RequestGuard(state={"request_count": 0}, persist=lambda: None)
    assert (
        guard.perform(lambda *_a, **_k: response, "GET", "https://static.cninfo.com.cn/a.pdf")
        is response
    )


def test_request_guard_rejects_limits_above_hard_ceiling():
    with pytest.raises(ValueError, match="INVALID_REQUEST_GUARD_LIMITS"):
        pilot.RequestGuard(state={}, persist=lambda: None, max_requests=121)


def test_completed_row_evidence_must_reside_under_diagnostic_root(tmp_path):
    outside = tmp_path.parent / "outside-evidence.tmp"
    outside.write_bytes(b"fixture")
    item = {
        "completed": True,
        "manifest_fingerprint": "same",
        "evidence_path": "../outside-evidence.tmp",
        "evidence_sha256": pilot.sha256_file(outside),
    }
    assert not pilot.should_skip_completed_row(item, "same", tmp_path)


def test_review_template_has_no_parser_derived_review_fields():
    predictions = pd.DataFrame(
        [{"firm_key": "F", "year": 2023, "parser_legal_name_at_year_end": "predicted"}]
    )
    review = pilot.build_review_template(predictions)
    assert review.review_status.tolist() == ["PENDING"]
    assert review.review_legal_name_at_year_end.tolist() == [""]
    assert review.source_is_official.tolist() == [""]


def test_existing_independent_review_is_preserved_without_key_drift(tmp_path):
    predictions = pd.DataFrame([{"firm_key": "F", "year": 2023}])
    review = pilot.build_review_template(predictions)
    review.loc[0, "review_status"] = "PASS"
    review.loc[0, "review_legal_name_at_year_end"] = "source-based review"
    path = tmp_path / "review.csv"
    review.to_csv(path, index=False)
    loaded = pilot.load_or_create_independent_review(predictions, path)
    assert loaded.loc[0, "review_status"] == "PASS"
    assert loaded.loc[0, "review_legal_name_at_year_end"] == "source-based review"


def test_mixed_subfamily_mechanisms_are_not_promoted_to_bulk_repair():
    for mechanisms in (
        {"PARSER_LAYOUT_GAP", "TEXT_EXTRACTION_PROBLEM"},
        {"NO_TRUE_TEMPORAL_PROBLEM", "TARGETED_H2_REQUIRED"},
    ):
        assert pilot.recommend_repair_mode(mechanisms) == "MORE_DIAGNOSTIC_REQUIRED"


def test_index_candidate_rejects_summary_cancel_and_non_h1_records():
    base = {
        "stock_code": "000001",
        "report_year": 2022,
        "title": "公司2022年年度报告全文",
        "announcement_id": "A1",
        "source_url": "https://static.cninfo.com.cn/a.pdf",
        "source_type": "official_annual_report",
        "source_tier": "H1",
    }
    for patch in (
        {"title": "公司2022年年度报告摘要"},
        {"title": "关于2022年年度报告的更正公告"},
        {"source_tier": "H2"},
        {"announcement_id": ""},
    ):
        assert not pilot.validate_index_candidate(
            {**base, **patch}, stock_code="000001", report_year=2022
        )


def test_guarded_session_forces_redirects_off_without_duplicate_keyword(monkeypatch):
    seen = {}

    def fake_request(_session, method, url, **kwargs):
        seen.update(method=method, url=url, **kwargs)
        return FakeResponse(200, "ok")

    monkeypatch.setattr(requests.Session, "request", fake_request)
    guard = pilot.RequestGuard(state={"request_count": 0}, persist=lambda: None)
    session = pilot.GuardedSession(guard)
    session.request("GET", "https://static.cninfo.com.cn/a.pdf", allow_redirects=True)
    assert seen["allow_redirects"] is False
    assert seen["method"] == "GET"


def test_index_lookup_is_scoped_to_one_security_code_and_one_fiscal_year():
    class FakeClient:
        _stock_catalog = None

        def stock_catalog(self):
            return {"600001": "ORG1"}

        def _request(self, method, url, **kwargs):
            assert method == "POST"
            assert kwargs["data"]["stock"] == "600001,ORG1"
            assert kwargs["data"]["searchkey"] == "2022年年度报告"
            assert kwargs["data"]["seDate"] == "2023-01-01~2024-12-31"

            class JsonResponse:
                @staticmethod
                def json():
                    return {"announcements": [], "totalpages": 0}

            return JsonResponse()

    candidates, audit = pilot.query_targeted_annual_report(
        FakeClient(), stock_code="600001", report_year=2022
    )
    assert candidates == []
    assert audit == []


def test_output_root_cannot_escape_ignored_diagnostic_workspace(tmp_path):
    with pytest.raises(ValueError, match="DIAGNOSTIC_OUTPUT_OUTSIDE_IGNORED_RESULTS"):
        pilot._ensure_output_root(tmp_path)
