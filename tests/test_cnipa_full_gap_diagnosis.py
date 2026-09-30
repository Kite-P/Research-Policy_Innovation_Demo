from __future__ import annotations

import pandas as pd

from scripts.diagnose_cnipa_full_gaps_20260930 import (
    COVERAGE_FAMILIES,
    build_diagnostic_pilot,
    build_primary_targets,
    classify_gap_row,
    classify_gap_subfamily,
    classify_stale_risk,
    derive_coverage_family,
    validate_coverage_partition,
)


def test_coverage_families_are_mutually_exclusive_exhaustive_and_define_exact_gap_union():
    frame = pd.DataFrame(
        [
            {
                "firm_key": "A",
                "year": 2020,
                "status": "PENDING",
                "evidence_status": "CONFIRMED_YEAR_END_NAME_ONLY",
            },
            {
                "firm_key": "B",
                "year": 2020,
                "status": "COMPLETE_NAME_CHANGE",
                "evidence_status": "CONFIRMED_NAME_CHANGE",
            },
            {
                "firm_key": "C",
                "year": 2020,
                "status": "COMPLETE_NO_CHANGE",
                "evidence_status": "CONFIRMED_NO_CHANGE",
            },
            {
                "firm_key": "D",
                "year": 2020,
                "status": "PENDING",
                "evidence_status": "TEMPORAL_UNRESOLVED",
            },
            {"firm_key": "E", "year": 2020, "status": "REPORT_NOT_FOUND", "evidence_status": ""},
            {
                "firm_key": "F",
                "year": 2020,
                "status": "LEGAL_NAME_NOT_FOUND",
                "evidence_status": "",
            },
            {
                "firm_key": "G",
                "year": 2020,
                "status": "TEXT_EXTRACTION_FAILED",
                "evidence_status": "",
            },
        ]
    )
    frame["coverage_family"] = frame.apply(derive_coverage_family, axis=1)
    result = validate_coverage_partition(frame, {(key, 2020) for key in "ABCDEFG"})
    assert result["valid"]
    assert set(frame.coverage_family).issubset(set(COVERAGE_FAMILIES))
    assert set(result["family_counts"]) == set(COVERAGE_FAMILIES)
    assert result["family_counts"]["SOURCE_BLOCKED"] == 0
    assert len(frame) == sum(result["family_counts"].values()) == 7
    assert result["gap_union_count"] == 4


def test_primary_targets_apply_formal_ready_manifest_before_year_filter():
    universe = pd.DataFrame(
        [
            {"firm_key": "READY", "year": 2020},
            {"firm_key": "READY", "year": 2025},
            {"firm_key": "EXCLUDED", "year": 2020},
        ]
    )
    manifest = pd.DataFrame(
        [
            {"firm_key": "READY", "formal_ready": True},
            {"firm_key": "EXCLUDED", "formal_ready": False},
        ]
    )
    primary = build_primary_targets(universe, manifest)
    assert list(zip(primary.firm_key, primary.year, strict=True)) == [("READY", 2020)]


def test_gap_subfamily_classification_uses_recorded_features_deterministically():
    row = pd.Series(
        {
            "coverage_family": "TEMPORAL_UNRESOLVED",
            "year": 2024,
            "legal_name_current_in_report": "甲公司股份有限公司",
            "legal_name_at_year_end": "乙公司股份有限公司",
            "legal_name_previous": "甲公司股份有限公司",
            "legal_name_new": "乙公司股份有限公司",
            "change_effective_date": "2024-06-30",
            "date_precision": "exact_date",
            "failure_reason": "temporal_match_uncertain",
        }
    )
    first = classify_gap_subfamily(
        row, adjacent_name_change=True, stale_parser=True, h2_url_available=False
    )
    second = classify_gap_subfamily(
        row, adjacent_name_change=True, stale_parser=True, h2_url_available=False
    )
    assert first == second
    assert first == "PAIR_EXACT_DATE_IN_TARGET_YEAR"


def test_stale_risk_tiers_apply_context_not_geographic_words_alone():
    branch = {
        "matched_label": "公司名称",
        "evidence_context": "释义：成都分公司系本公司分支机构",
        "legal_name_current_in_report": "甲股份有限公司成都分公司",
        "profile_legal_name": "甲股份有限公司",
        "identity_name_match": False,
        "verified_historical_name_match": False,
        "adjacent_year_name_discontinuity": False,
        "temporal_unresolved": False,
        "source_url": "https://static.test/report.pdf",
        "pdf_sha256": "a" * 64,
    }
    assert classify_stale_risk(branch)[0] == "HIGH"

    precise = {
        **branch,
        "matched_label": "公司的中文名称",
        "evidence_context": "公司的中文名称：甲股份有限公司",
        "legal_name_current_in_report": "甲股份有限公司",
        "identity_name_match": True,
    }
    assert classify_stale_risk(precise)[0] == "LOW"

    geographic_only = {
        **precise,
        "evidence_context": "公司注册地址位于成都，主要办公地在杭州。",
        "legal_name_current_in_report": "成都甲股份有限公司",
    }
    assert classify_stale_risk(geographic_only)[0] != "HIGH"

    insufficient = {**precise, "matched_label": "", "evidence_context": ""}
    assert classify_stale_risk(insufficient)[0] == "INSUFFICIENT_LOCAL_EVIDENCE"


def test_text_extraction_failure_is_not_mislabeled_as_transport_or_fetch_failure():
    row = {
        "coverage_family": "REPORT_FETCH_FAILED",
        "raw_status": "TEXT_EXTRACTION_FAILED",
        "failure_reason": "ValueError:pdftotext produced empty or implausibly short text",
        "source_url": "https://static.test/report.pdf",
        "http_status": "",
        "pdf_bytes": 0,
    }
    _, subfamily, action = classify_gap_row(row)
    assert subfamily == "TEXT_EXTRACTION_FAILURE_MISCLASSIFIED_AS_FETCH_FAILURE"
    assert action == "REFETCH_EXACT_H1_URL"


def test_fetch_failure_classes_use_only_recorded_source_metadata():
    cases = [
        ({"http_status": 403, "source_url": "https://static.test/a.pdf"}, "KNOWN_URL_HTTP_403"),
        (
            {"http_status": 200, "pdf_bytes": 0, "source_url": "https://static.test/a.pdf"},
            "HTTP_200_EMPTY_OR_NON_PDF_RESPONSE",
        ),
        (
            {"http_status": 200, "pdf_bytes": 800, "source_url": "https://static.test/a.pdf"},
            "PDF_TOO_SMALL",
        ),
        ({"failure_reason": "connection timeout"}, "TRANSPORT_ERROR"),
    ]
    for fields, expected in cases:
        row = {
            "coverage_family": "REPORT_FETCH_FAILED",
            "raw_status": "PDF_FETCH_FAILED",
            **fields,
        }
        assert classify_gap_row(row)[1] == expected


def test_diagnostic_pilot_is_deterministic_and_covers_each_required_group():
    gap = pd.DataFrame(
        [
            {
                "firm_key": f"G{i}",
                "year": 2020,
                "gap_family": "TEMPORAL_UNRESOLVED",
                "gap_subfamily": "TEMPORAL_PAIR" if i % 2 else "TEMPORAL_CURRENT_ONLY",
                "suggested_next_action": "MANUAL_SOURCE_REVIEW",
                "diagnosis_basis": "fixture",
            }
            for i in range(24)
        ]
    )
    stale = pd.DataFrame(
        [
            {
                "firm_key": f"S{tier}-{i}",
                "year": 2021,
                "risk_tier": tier,
                "risk_reason": "fixture",
                "suggested_next_action": "REPARSE_EXISTING_LOCAL_TEXT",
            }
            for tier in ("HIGH", "MEDIUM", "INSUFFICIENT_LOCAL_EVIDENCE", "LOW")
            for i in range(8)
        ]
    )
    targets = {(f"G{i}", 2020) for i in range(24)} | {
        (f"S{tier}-{i}", 2021)
        for tier in ("HIGH", "MEDIUM", "INSUFFICIENT_LOCAL_EVIDENCE", "LOW")
        for i in range(8)
    }
    first = build_diagnostic_pilot(gap, stale, targets, seed="20260930")
    second = build_diagnostic_pilot(gap, stale, targets, seed="20260930")
    pd.testing.assert_frame_equal(first, second)
    assert not first.duplicated(["firm_key", "year"]).any()
    assert set(zip(first.firm_key, first.year, strict=True)).issubset(targets)
    assert set(gap.gap_subfamily).issubset(set(first.subfamily))
    assert {"HIGH", "MEDIUM", "INSUFFICIENT_LOCAL_EVIDENCE"}.issubset(set(first.risk_tier))
    assert len(first) <= 150


def test_offline_run_preserves_protected_inputs_and_never_opens_network(tmp_path, monkeypatch):
    import json
    import socket

    from scripts import diagnose_cnipa_full_gaps_20260930 as diagnosis

    full_dir = tmp_path / "cnipa"
    cache_dir = full_dir / "cache"
    cache_dir.mkdir(parents=True)
    historical_cache = tmp_path / "historical-cache"
    historical_cache.mkdir()
    output_dir = tmp_path / "diagnosis"
    firms = [f"F{i}" for i in range(7)]
    categories = [
        ("PENDING", "CONFIRMED_YEAR_END_NAME_ONLY"),
        ("COMPLETE_NAME_CHANGE", "CONFIRMED_NAME_CHANGE"),
        ("COMPLETE_NO_CHANGE", "CONFIRMED_NO_CHANGE"),
        ("PENDING", "TEMPORAL_UNRESOLVED"),
        ("REPORT_NOT_FOUND", ""),
        ("LEGAL_NAME_NOT_FOUND", ""),
        ("TEXT_EXTRACTION_FAILED", ""),
    ]
    records = []
    for index, (firm, pair) in enumerate(zip(firms, categories, strict=True)):
        status, evidence_status = pair
        records.append(
            {
                "firm_key": firm,
                "year": 2020,
                "exchange": "SSE",
                "stock_code": str(600000 + index),
                "status": status,
                "evidence_status": evidence_status,
                "legal_name_current_in_report": "甲股份有限公司" if index < 4 else "",
                "legal_name_at_year_end": "甲股份有限公司" if index < 4 else "",
                "legal_name_previous": "",
                "legal_name_new": "",
                "company_name_change_flag": "UNKNOWN",
                "change_effective_date": "",
                "date_precision": "year",
                "temporal_match_uncertain": index == 3,
                "failure_reason": "",
                "matched_label": "",
                "evidence_context": "",
                "source_url": "https://static.test/report.pdf" if index != 4 else "",
                "source_announcement_id": "",
                "source_report_title": "2020 年年度报告",
                "source_report_date": "2021-01-01",
                "http_status": 200,
                "pdf_bytes": 5000,
                "pdf_sha256": f"{index:064x}",
                "text_chars": 10000,
                "pdf_content_persisted": False,
                "change_evidence_tier": "",
                "change_evidence_url": "",
            }
        )
    baseline = pd.DataFrame(records)
    baseline["coverage_status"] = baseline.apply(diagnosis.derive_coverage_family, axis=1)
    baseline_path = full_dir / "full_status.csv"
    baseline.to_csv(baseline_path, index=False)
    state_path = full_dir / "full_run_state.json"
    state_path.write_text(
        json.dumps(
            {
                "stage": "full",
                "status": "COMPLETE",
                "status_key_set_exact": True,
                "target_firm_years": 7,
            }
        ),
        encoding="utf-8",
    )
    for name in (
        "pilot_change_event_ground_truth.csv",
        "pilot_change_row_ground_truth.csv",
        "pilot_change_evidence_state_ground_truth.csv",
    ):
        (full_dir / name).write_text("frozen fixture\n", encoding="utf-8")
    success = baseline.loc[
        baseline.status.isin({"PENDING", "COMPLETE_NAME_CHANGE", "COMPLETE_NO_CHANGE"})
    ]
    for index, row in enumerate(success.to_dict("records")):
        (cache_dir / f"cache-{index}.json").write_text(
            json.dumps({**row, "parser_revision": "issuer_scope_v1"}), encoding="utf-8"
        )
    entity_coverage = tmp_path / "entity_year_name_coverage.csv"
    out_of_scope_coverage = pd.DataFrame(
        [{"firm_key": "F0", "year": 2025, "coverage_status": "CONFIRMED_NO_CHANGE"}]
    )
    pd.concat(
        [baseline[["firm_key", "year", "coverage_status"]], out_of_scope_coverage],
        ignore_index=True,
    ).to_csv(entity_coverage, index=False)
    universe_path = tmp_path / "universe.parquet"
    pd.DataFrame(
        [
            {
                "firm_key": firm,
                "year": 2020,
                "company_name_legal_profile": "甲股份有限公司",
                "company_name_legal": "甲股份有限公司",
                "listing_date": "2010-01-01",
                "delisting_date": "",
                "market_listing_date": "2010-01-01",
            }
            for firm in firms
        ]
    ).to_parquet(universe_path, index=False)
    manifest_path = tmp_path / "target_manifest.csv"
    pd.DataFrame({"firm_key": firms, "formal_ready": True}).to_csv(manifest_path, index=False)
    entity_audit_path = tmp_path / "entity_name_audit.csv"
    pd.DataFrame(
        columns=[
            "firm_key",
            "verification_status",
            "name_type",
            "candidate_name_normalized",
            "candidate_name_raw",
        ]
    ).to_csv(entity_audit_path, index=False)
    for name, value in {
        "FULL_DIR": full_dir,
        "FULL_STATUS": baseline_path,
        "FULL_STATE": state_path,
        "CACHE_DIR": cache_dir,
        "ENTITY_COVERAGE": entity_coverage,
        "UNIVERSE": universe_path,
        "TARGET_MANIFEST": manifest_path,
        "ENTITY_NAME_AUDIT": entity_audit_path,
        "HISTORICAL_SOURCE_CACHE": historical_cache,
        "OUTPUT_DIR": output_dir,
        "EXPECTED_FULL_ROWS": 7,
    }.items():
        monkeypatch.setattr(diagnosis, name, value)
    monkeypatch.setattr(
        socket.socket,
        "connect",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("network attempted")),
    )

    before = diagnosis._snapshot_protected_files()
    result = diagnosis.run_offline_diagnosis()
    after = diagnosis._snapshot_protected_files()
    assert result["network_requests"] == 0
    assert result["full_and_pilot_inputs_unchanged"]
    assert before == after
    assert result["baseline_rows"] == 7
    assert result["gap_union_count"] == 4
    assert result["entity_coverage_rows_outside_primary_target"] == 1
    assert result["stale_success_count"] == 4
    assert sum(result["stale_risk_tier_counts"].values()) == 4
    pilot = pd.read_csv(output_dir / "diagnostic_pilot_manifest.csv")
    assert not pilot.duplicated(["firm_key", "year"]).any()
    assert set(zip(pilot.firm_key.astype(str), pilot.year.astype(int))).issubset(
        set(zip(firms, [2020] * len(firms)))
    )
