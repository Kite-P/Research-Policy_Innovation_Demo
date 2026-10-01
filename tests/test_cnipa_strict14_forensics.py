from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest


def _forensics_api():
    from src import cnipa_strict14_forensics

    return cnipa_strict14_forensics


def test_notice_with_pair_date_and_completion_is_extractor_layout_gap_if_unresolved():
    classify_notice_record = _forensics_api().classify_notice_record
    target = {
        "firm_key": "SSE:600936:2016-08-15",
        "year": 2025,
        "previous_legal_name": "旧公司股份有限公司",
        "new_legal_name": "新公司股份有限公司",
    }
    notice = {
        "source_url": "https://static.cninfo.com.cn/finalpage/2026-01-06/1234567890.PDF",
        "http_status": 200,
        "pdf_sha256": "a" * 64,
        "text_extraction_status": "EXTRACTED",
        "text_chars": 2000,
    }
    text = (
        "证券代码：600936\n新公司股份有限公司\n"
        "（曾用名：旧公司股份有限公司）\n"
        "2025年12月31日，公司完成上述变更公司名称并完成工商变更登记。"
    )
    result = classify_notice_record(
        target,
        notice,
        text,
        {
            "evidence_status": "TEMPORAL_UNRESOLVED",
            "failure_reason": "notice_does_not_confirm_expected_name_pair",
        },
    )
    assert result["terminal_failure_class"] == "EXTRACTOR_LAYOUT_GAP"
    assert result["expected_pair_text_present"] is True
    assert result["completion_semantics_present"] is True
    assert result["effective_date_text"] == "2025-12-31"


def test_proposal_with_names_but_pending_approval_is_not_resolved_notice():
    classify_notice_record = _forensics_api().classify_notice_record
    target = {
        "firm_key": "SSE:600936:2016-08-15",
        "year": 2025,
        "previous_legal_name": "旧公司股份有限公司",
        "new_legal_name": "新公司股份有限公司",
    }
    notice = {
        "source_url": "https://static.cninfo.com.cn/finalpage/2025-12-11/1234567890.PDF",
        "http_status": 200,
        "text_extraction_status": "EXTRACTED",
        "text_chars": 500,
    }
    text = (
        "证券代码：600936\n旧公司股份有限公司关于变更公司名称的公告。"
        "拟变更后的公司中文全称：新公司股份有限公司。"
        "本次事项尚需提交股东大会审议并办理工商登记。"
    )
    result = classify_notice_record(
        target,
        notice,
        text,
        {"evidence_status": "TEMPORAL_UNRESOLVED", "failure_reason": "pair_not_confirmed"},
    )
    assert result["expected_pair_text_present"] is True
    assert result["completion_semantics_present"] is False
    assert result["terminal_failure_class"] == "NOTICE_RETURNED_PAIR_NOT_CONFIRMED"


def test_unrelated_completed_transaction_and_notice_date_do_not_become_name_change_effective_date():
    classify_notice_record = _forensics_api().classify_notice_record
    target = {
        "firm_key": "SSE:600936:2016-08-15",
        "year": 2025,
        "previous_legal_name": "旧公司股份有限公司",
        "new_legal_name": "新公司股份有限公司",
    }
    text = (
        "证券代码：600936。2025年8月29日，公司完成重大资产置换。"
        "2025年12月11日公告拟将全称变更为新公司股份有限公司。"
        "该事项尚需股东大会审议，之后将申请工商变更登记。"
        "原名旧公司股份有限公司。"
    )
    result = classify_notice_record(
        target,
        {
            "source_url": "https://static.cninfo.com.cn/finalpage/2025-12-11/1234567890.PDF",
            "http_status": 200,
            "text_extraction_status": "EXTRACTED",
        },
        text,
        {"evidence_status": "TEMPORAL_UNRESOLVED", "failure_reason": "pending"},
    )
    assert result["expected_pair_text_present"] is True
    assert result["effective_date_text"] == ""
    assert result["completion_semantics_present"] is False
    assert result["terminal_failure_class"] == "NOTICE_RETURNED_PAIR_NOT_CONFIRMED"


def test_notice_identity_and_target_window_are_checked_before_extractor_failure():
    classify_notice_record = _forensics_api().classify_notice_record
    target = {
        "firm_key": "SZSE:300237:2011-06-29",
        "year": 2024,
        "previous_legal_name": "旧公司股份有限公司",
        "new_legal_name": "新公司股份有限公司",
    }
    wrong_issuer = classify_notice_record(
        target,
        {
            "source_url": "https://static.cninfo.com.cn/finalpage/2024-08-13/1234567890.PDF",
            "http_status": 200,
            "text_extraction_status": "EXTRACTED",
        },
        "证券代码：600936 旧公司股份有限公司变更为新公司股份有限公司",
        {"evidence_status": "TEMPORAL_UNRESOLVED"},
    )
    assert wrong_issuer["terminal_failure_class"] == "NOTICE_SOURCE_IDENTITY_PROBLEM"
    out_of_window = classify_notice_record(
        target,
        {
            "source_url": "https://static.cninfo.com.cn/finalpage/2026-06-01/1234567890.PDF",
            "http_status": 200,
            "text_extraction_status": "EXTRACTED",
        },
        "证券代码：300237 旧公司股份有限公司变更为新公司股份有限公司",
        {"evidence_status": "TEMPORAL_UNRESOLVED"},
    )
    assert out_of_window["terminal_failure_class"] == "NOTICE_DATE_WINDOW_MISMATCH"


def test_all_four_h2_targets_receive_one_terminal_class():
    build_h2_target_forensics = _forensics_api().build_h2_target_forensics
    manifest = pd.DataFrame(
        [{"firm_key": f"SZSE:{i:06d}:2000-01-01", "year": 2020 + i} for i in range(1, 5)]
    )
    evidence = pd.DataFrame(
        [
            {
                "firm_key": manifest.iloc[0].firm_key,
                "year": manifest.iloc[0].year,
                "status": "RESOLVED_H2",
                "retrieval_mode": "H2_LOCAL_CARRY",
            },
            {
                "firm_key": manifest.iloc[1].firm_key,
                "year": manifest.iloc[1].year,
                "status": "H2_SOURCE_UNAVAILABLE",
            },
            {
                "firm_key": manifest.iloc[2].firm_key,
                "year": manifest.iloc[2].year,
                "status": "H2_SOURCE_UNAVAILABLE",
                "discovery_notice_count": 0,
            },
            {
                "firm_key": manifest.iloc[3].firm_key,
                "year": manifest.iloc[3].year,
                "status": "H2_SOURCE_UNAVAILABLE",
                "discovery_notice_count": 1,
            },
        ]
    )
    notices = pd.DataFrame(
        [
            {
                "firm_key": manifest.iloc[1].firm_key,
                "year": manifest.iloc[1].year,
                "terminal_failure_class": "EXTRACTOR_LAYOUT_GAP",
                "text_extraction_status": "EXTRACTED",
            },
        ]
    )
    audit = pd.DataFrame(
        [
            {
                "firm_key": row.firm_key,
                "year": row.year,
                "purpose": "targeted_name_change_discovery",
            }
            for row in manifest.itertuples()
        ]
    )
    result = build_h2_target_forensics(manifest, evidence, audit, notices)
    assert len(result) == 4
    assert result.terminal_failure_class.tolist() == [
        "RESOLVED_H2",
        "EXTRACTOR_LAYOUT_GAP",
        "NO_NOTICE_RETURNED",
        "SOURCE_PROVENANCE_INSUFFICIENT",
    ]
    assert result.terminal_failure_class.nunique() == 4
    assert "EXTRACTOR_LAYOUT_GAP" in result.iloc[1].failure_detail


def test_event_decomposition_exhausts_six_slots_without_fabricating_predictions():
    build_event_failure_decomposition = _forensics_api().build_event_failure_decomposition
    event_gt = pd.DataFrame(
        [
            {
                "event_id": f"E{i}",
                "firm_key": f"SZSE:{i:06d}:2000-01-01",
                "review_previous_legal_name": f"old{i}",
                "review_new_legal_name": f"new{i}",
                "review_effective_date": "2024-01-01",
                "review_date_precision": "exact_date",
            }
            for i in range(1, 7)
        ]
    )
    predictions = pd.DataFrame(
        [
            {
                "event_id": f"E{i}",
                "firm_key": f"SZSE:{i:06d}:2000-01-01",
                "parser_previous_legal_name": f"old{i}",
                "parser_new_legal_name": f"new{i}",
                "parser_effective_date": "2024-01-01",
                "parser_date_precision": "exact_date",
                "source_evidence_tier": "H1",
            }
            for i in range(1, 4)
        ]
        + [
            {
                "event_id": "E4",
                "firm_key": "SZSE:000004:2000-01-01",
                "parser_previous_legal_name": "old4",
                "parser_new_legal_name": "new4",
                "parser_effective_date": "",
                "parser_date_precision": "year",
                "source_evidence_tier": "H2",
            }
        ]
    )
    result = build_event_failure_decomposition(
        predictions,
        event_gt,
        h2_failure_by_event={"E5": "EXTRACTOR_LAYOUT_GAP"},
        local_h1_event_ids={"E6"},
    )
    assert len(result) == 6
    assert result.event_id.is_unique
    assert result.status.value_counts().to_dict() == {
        "EVENT_CORRECT": 3,
        "EVENT_FIELD_MISMATCH": 1,
        "EVENT_H2_EXTRACTOR_FAILURE": 1,
        "EVENT_CANDIDATE_MAPPING_FAILURE": 1,
    }
    assert result.loc[result.event_id.eq("E5"), "event_prediction_present"].item() is False
    assert result.loc[result.event_id.eq("E6"), "event_prediction_present"].item() is False


def test_event_decomposition_does_not_copy_gt_values_into_missing_predictions():
    build_event_failure_decomposition = _forensics_api().build_event_failure_decomposition
    event_gt = pd.DataFrame(
        [
            {
                "event_id": f"E{i}",
                "firm_key": f"SSE:{i:06d}:2000-01-01",
                "review_previous_legal_name": f"GT old{i}",
                "review_new_legal_name": f"GT new{i}",
                "review_effective_date": "2023-01-01",
                "review_date_precision": "exact_date",
            }
            for i in range(1, 7)
        ]
    )
    result = build_event_failure_decomposition(
        pd.DataFrame(
            columns=[
                "event_id",
                "firm_key",
                "parser_previous_legal_name",
                "parser_new_legal_name",
                "parser_effective_date",
                "parser_date_precision",
            ]
        ),
        event_gt,
        h2_failure_by_event={},
        local_h1_event_ids=set(),
    )
    missing = result.loc[result.event_id.eq("E1")].iloc[0]
    assert not missing.event_prediction_present
    assert missing.predicted_previous_name == ""
    assert missing.predicted_new_name == ""
    assert missing.predicted_effective_date == ""


def test_row_decomposition_is_fourteen_rows_and_all_fused_mismatches_have_dependency():
    build_row_evidence_state_decomposition = _forensics_api().build_row_evidence_state_decomposition
    keys = [(f"SZSE:{i:06d}:2000-01-01", 2020 + i) for i in range(1, 15)]
    h1 = pd.DataFrame(
        [{"firm_key": k, "year": y, "parser_change_flag": "UNKNOWN"} for k, y in keys]
    )
    fused = h1.copy()
    frozen = pd.DataFrame(
        [
            {
                "firm_key": k,
                "year": y,
                "parser_change_flag": "UNKNOWN",
                "parser_legal_name_at_year_end": f"name{i}",
                "proposed_event_id": "",
            }
            for i, (k, y) in enumerate(keys, 1)
        ]
    )
    expected = ["NO"] * 12 + ["UNKNOWN", "UNKNOWN"]
    evidence_gt = pd.DataFrame(
        [
            {"firm_key": k, "year": y, "review_expected_parser_flag": flag}
            for (k, y), flag in zip(keys, expected, strict=True)
        ]
    )
    candidates = pd.DataFrame(
        columns=["firm_key", "year", "adjacent_year_name_change", "candidate_reason"]
    )
    result = build_row_evidence_state_decomposition(
        h1,
        fused,
        frozen,
        candidates,
        evidence_gt,
        h2_dependency_by_key={keys[0]: "DEP-H2"},
        h1_pair_evidence_by_key={keys[1]: "DEP-H1"},
        event_ids_by_firm={keys[2][0]: ["EVT-1"]},
    )
    assert len(result) == 14
    mismatches = result.loc[~result.fused_correct]
    assert mismatches.failure_dependency_id.notna().all()
    assert mismatches.failure_dependency_id.ne("").all()


def test_same_unresolved_h2_dependency_can_explain_multiple_row_mismatches():
    build_row_evidence_state_decomposition = _forensics_api().build_row_evidence_state_decomposition
    focal = [("SSE:600936:2016-08-15", 2024), ("SSE:600936:2016-08-15", 2025)]
    keys = focal + [(f"SZSE:{i:06d}:2000-01-01", 2000 + i) for i in range(1, 13)]
    h1 = pd.DataFrame(
        [{"firm_key": k, "year": y, "parser_change_flag": "UNKNOWN"} for k, y in keys]
    )
    frozen = pd.DataFrame(
        [
            {
                "firm_key": k,
                "year": y,
                "parser_change_flag": "UNKNOWN",
                "parser_legal_name_at_year_end": "name",
                "proposed_event_id": "",
            }
            for k, y in keys
        ]
    )
    expected = ["NO", "YES"] + ["UNKNOWN"] * 12
    evidence_gt = pd.DataFrame(
        [
            {"firm_key": k, "year": y, "review_expected_parser_flag": flag}
            for (k, y), flag in zip(keys, expected, strict=True)
        ]
    )
    result = build_row_evidence_state_decomposition(
        h1,
        h1,
        frozen,
        pd.DataFrame(),
        evidence_gt,
        h2_dependency_by_key={key: "DEP-H2-600936-2025" for key in keys},
        h1_pair_evidence_by_key={},
        event_ids_by_firm={},
    )
    mismatches = result.loc[~result.fused_correct]
    assert len(mismatches) == 2
    assert mismatches.failure_dependency_id.nunique() == 1
    assert mismatches.failure_dependency_id.iloc[0] == "DEP-H2-600936-2025"
    assert mismatches.failure_class.tolist() == ["WAITING_ON_UNRESOLVED_H2"] * 2


def test_no_flag_requires_an_independently_mapped_event_and_absence_stays_unknown():
    build_row_evidence_state_decomposition = _forensics_api().build_row_evidence_state_decomposition
    key = ("SZSE:000001:2000-01-01", 2024)
    keys = [key] + [(f"SZSE:{i:06d}:2000-01-01", 2000 + i) for i in range(1, 14)]
    h1 = pd.DataFrame(
        [{"firm_key": k, "year": y, "parser_change_flag": "UNKNOWN"} for k, y in keys]
    )
    frozen = pd.DataFrame(
        [
            {
                "firm_key": k,
                "year": y,
                "parser_change_flag": "UNKNOWN",
                "parser_legal_name_at_year_end": "name",
                "proposed_event_id": "",
            }
            for k, y in keys
        ]
    )
    evidence_gt = pd.DataFrame(
        [
            {
                "firm_key": k,
                "year": y,
                "review_expected_parser_flag": "NO" if (k, y) == key else "UNKNOWN",
            }
            for k, y in keys
        ]
    )
    result = build_row_evidence_state_decomposition(
        h1,
        h1,
        frozen,
        pd.DataFrame(),
        evidence_gt,
        h2_dependency_by_key={},
        h1_pair_evidence_by_key={},
        event_ids_by_firm={},
    )
    focal = result.loc[result.firm_key.eq(key[0]) & result.year.eq(key[1])].iloc[0]
    assert focal.fused_flag == "UNKNOWN"
    assert focal.failure_class == "OTHER"
    assert focal.failure_dependency_id != ""


def test_mapped_non_target_year_event_classifies_unknown_as_missing_propagation_not_no():
    build_row_evidence_state_decomposition = _forensics_api().build_row_evidence_state_decomposition
    key = ("SZSE:000001:2000-01-01", 2024)
    keys = [key] + [(f"SZSE:{i:06d}:2000-01-01", 2000 + i) for i in range(1, 14)]
    h1 = pd.DataFrame(
        [{"firm_key": k, "year": y, "parser_change_flag": "UNKNOWN"} for k, y in keys]
    )
    frozen = pd.DataFrame(
        [
            {
                "firm_key": k,
                "year": y,
                "parser_change_flag": "UNKNOWN",
                "parser_legal_name_at_year_end": "name",
                "proposed_event_id": "EVT1" if (k, y) == key else "",
            }
            for k, y in keys
        ]
    )
    evidence_gt = pd.DataFrame(
        [
            {
                "firm_key": k,
                "year": y,
                "review_expected_parser_flag": "NO" if (k, y) == key else "UNKNOWN",
            }
            for k, y in keys
        ]
    )
    result = build_row_evidence_state_decomposition(
        h1,
        h1,
        frozen,
        pd.DataFrame(),
        evidence_gt,
        h2_dependency_by_key={},
        h1_pair_evidence_by_key={},
        event_ids_by_firm={key[0]: ["EVT1"]},
    )
    focal = result.loc[result.firm_key.eq(key[0]) & result.year.eq(key[1])].iloc[0]
    assert focal.fused_flag == "UNKNOWN"
    assert focal.failure_class == "WAITING_ON_EVENT_PROPAGATION"


def test_local_h1_change_pair_takes_precedence_over_empty_h2_search():
    build_row_evidence_state_decomposition = _forensics_api().build_row_evidence_state_decomposition
    key = ("SSE:603003:2012-08-17", 2023)
    keys = [key] + [(f"SZSE:{i:06d}:2000-01-01", 2000 + i) for i in range(1, 14)]
    h1 = pd.DataFrame(
        [{"firm_key": k, "year": y, "parser_change_flag": "UNKNOWN"} for k, y in keys]
    )
    frozen = pd.DataFrame(
        [
            {
                "firm_key": k,
                "year": y,
                "parser_change_flag": "UNKNOWN",
                "parser_legal_name_at_year_end": "new",
                "proposed_event_id": "",
            }
            for k, y in keys
        ]
    )
    evidence_gt = pd.DataFrame(
        [
            {
                "firm_key": k,
                "year": y,
                "review_expected_parser_flag": "YES" if (k, y) == key else "UNKNOWN",
            }
            for k, y in keys
        ]
    )
    result = build_row_evidence_state_decomposition(
        h1,
        h1,
        frozen,
        pd.DataFrame(),
        evidence_gt,
        h2_dependency_by_key={key: "DEP-NO-H2"},
        h1_pair_evidence_by_key={key: "DEP-H1-603003"},
        event_ids_by_firm={},
    )
    focal = result.loc[result.firm_key.eq(key[0]) & result.year.eq(key[1])].iloc[0]
    assert focal.failure_class == "H1_EXPLICIT_FLAG_ERROR"
    assert focal.failure_dependency_id == "DEP-H1-603003"


def test_year_end_decomposition_lists_only_the_mismatch_and_uses_h1_residual_class():
    build_year_end_failure_decomposition = _forensics_api().build_year_end_failure_decomposition
    h1 = pd.DataFrame(
        [
            {"firm_key": "SSE:1", "year": 2022, "parser_legal_name_at_year_end": "新名"},
            {"firm_key": "SSE:2", "year": 2022, "parser_legal_name_at_year_end": "正确名"},
        ]
    )
    fused = h1.copy()
    row_gt = pd.DataFrame(
        [
            {"firm_key": "SSE:1", "year": 2022, "review_legal_name_at_year_end": "旧名"},
            {"firm_key": "SSE:2", "year": 2022, "review_legal_name_at_year_end": "正确名"},
        ]
    )
    result = build_year_end_failure_decomposition(
        h1,
        fused,
        row_gt,
        h1_temporal_evidence_by_key={("SSE:1", 2022): "DEP-H1"},
        unresolved_h2_by_key={},
    )
    assert len(result) == 1
    assert result.failure_class.item() == "H1_YEAR_END_PARSER_ERROR"
    assert result.failure_dependency_id.item() == "DEP-H1"


def test_year_end_h2_dependency_is_not_mislabeled_as_h1_parser_error():
    build_year_end_failure_decomposition = _forensics_api().build_year_end_failure_decomposition
    h1 = pd.DataFrame(
        [{"firm_key": "SSE:1", "year": 2024, "parser_legal_name_at_year_end": "旧名"}]
    )
    fused = h1.copy()
    row_gt = pd.DataFrame(
        [{"firm_key": "SSE:1", "year": 2024, "review_legal_name_at_year_end": "新名"}]
    )
    result = build_year_end_failure_decomposition(
        h1,
        fused,
        row_gt,
        h1_temporal_evidence_by_key={},
        unresolved_h2_by_key={("SSE:1", 2024): "DEP-H2"},
    )
    assert result.failure_class.item() == "TEMPORAL_H2_EVIDENCE_MISSING"


def test_dependency_graph_aggregates_shared_failures_and_counts_metrics():
    build_failure_dependency_graph = _forensics_api().build_failure_dependency_graph
    rows = pd.DataFrame(
        [
            {
                "firm_key": "SSE:1",
                "year": 2024,
                "fused_correct": False,
                "failure_dependency_id": "DEP1",
                "failure_class": "WAITING_ON_UNRESOLVED_H2",
            },
            {
                "firm_key": "SSE:1",
                "year": 2025,
                "fused_correct": False,
                "failure_dependency_id": "DEP1",
                "failure_class": "WAITING_ON_UNRESOLVED_H2",
            },
        ]
    )
    events = pd.DataFrame(
        [
            {
                "event_id": "E1",
                "status": "EVENT_H2_EXTRACTOR_FAILURE",
                "failure_dependency_id": "DEP1",
            },
        ]
    )
    year_end = pd.DataFrame(columns=["firm_key", "year", "failure_dependency_id", "failure_class"])
    result = build_failure_dependency_graph(rows, events, year_end)
    assert len(result) == 1
    assert result.affected_row_count.item() == 2
    assert result.affected_event_count.item() == 1
    assert result.requires_network.item() is False


def test_frozen45_metrics_and_prior25_regression_guard():
    validate_frozen45_summary = _forensics_api().validate_frozen45_summary
    validate_frozen45_summary(
        {
            "issuer_correct": 45,
            "year_end_correct": 45,
            "evidence_state_correct": 45,
            "denominator": 45,
            "prior_correct25_denominator": 25,
            "prior_correct25_regressions": 0,
        }
    )
    with pytest.raises(ValueError, match="FROZEN45_GATE_FAILED"):
        validate_frozen45_summary(
            {
                "issuer_correct": 44,
                "year_end_correct": 45,
                "evidence_state_correct": 45,
                "denominator": 45,
                "prior_correct25_denominator": 25,
                "prior_correct25_regressions": 0,
            }
        )


def test_discovery_cap_is_only_reported_when_returned_candidates_exceed_fetched_pdfs():
    build_h2_target_forensics = _forensics_api().build_h2_target_forensics
    manifest = pd.DataFrame([{"firm_key": "SSE:000001:2000-01-01", "year": 2025}])
    evidence = pd.DataFrame(
        [
            {
                "firm_key": "SSE:000001:2000-01-01",
                "year": 2025,
                "status": "H2_SOURCE_UNAVAILABLE",
                "discovery_notice_count": 4,
            }
        ]
    )
    notices = pd.DataFrame(
        [
            {
                "firm_key": "SSE:000001:2000-01-01",
                "year": 2025,
                "pdf_sha256": digest,
                "terminal_failure_class": "NOTICE_RETURNED_PAIR_NOT_CONFIRMED",
            }
            for digest in ("a" * 64, "b" * 64, "c" * 64)
        ]
    )
    result = build_h2_target_forensics(manifest, evidence, pd.DataFrame(), notices)
    assert result.potentially_truncated_by_three_pdf_cap.item()


def test_300365_unknown_negative_control_is_not_reclassified_as_no():
    build_row_evidence_state_decomposition = _forensics_api().build_row_evidence_state_decomposition
    keys = [("SZSE:300365:2014-01-23", year) for year in (2020, 2021)]
    keys.extend((f"SSE:{i:06d}:2000-01-01", 2000 + i) for i in range(1, 13))
    predictions = pd.DataFrame(
        [{"firm_key": firm, "year": year, "parser_change_flag": "UNKNOWN"} for firm, year in keys]
    )
    frozen = pd.DataFrame(
        [
            {
                "firm_key": firm,
                "year": year,
                "parser_change_flag": "UNKNOWN",
                "parser_legal_name_at_year_end": "issuer",
                "proposed_event_id": "",
            }
            for firm, year in keys
        ]
    )
    expected = pd.DataFrame(
        [
            {"firm_key": firm, "year": year, "review_expected_parser_flag": "UNKNOWN"}
            for firm, year in keys
        ]
    )
    result = build_row_evidence_state_decomposition(
        predictions,
        predictions,
        frozen,
        pd.DataFrame(),
        expected,
        h2_dependency_by_key={},
        h1_pair_evidence_by_key={},
        event_ids_by_firm={},
    )
    negative = result.loc[result.firm_key.str.contains(":300365:")]
    assert len(negative) == 2
    assert negative.fused_flag.tolist() == ["UNKNOWN", "UNKNOWN"]
    assert negative.failure_class.tolist() == ["NEGATIVE_CONTROL_PASS", "NEGATIVE_CONTROL_PASS"]


def test_g3_driver_has_no_network_client_or_network_call_surface():
    driver = Path(__file__).parents[1] / "scripts" / "diagnose_cnipa_strict14_g3.py"
    source = driver.read_text(encoding="utf-8")
    lowered = source.lower()
    assert "import requests" not in lowered
    assert "import httpx" not in lowered
    assert "urllib.request" not in lowered
    assert "requests.get(" not in lowered
    assert "requests.post(" not in lowered
    assert "session.request(" not in lowered
    assert "urlopen(" not in lowered
