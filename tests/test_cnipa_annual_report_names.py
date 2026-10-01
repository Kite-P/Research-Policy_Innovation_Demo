from __future__ import annotations

from pathlib import Path

from scripts import run_cninfo_legal_name_recovery_20260929 as recovery
from scripts.run_cninfo_legal_name_recovery_20260929 import (
    _build_pilot_change_candidate_rows,
    _build_v2_strict_pilot_summary,
    _coverage_status,
    _frame_fingerprint,
    _load_status_cache,
    _preserve_manual_audit,
    _process_one,
    _resolve_cross_year_name_changes,
    _strict_pilot_authorized,
    _strict_pilot_authorized_v2,
)
from src.cnipa_annual_report_names import (
    PARSER_REVISION,
    _legal_value,
    build_canonical_change_event_roster,
    extract_annual_report_legal_name_evidence,
    extract_company_name_change_announcement,
    is_change_related_candidate,
    select_legal_name_pilot,
    validate_firm_year_status_set,
    validate_pdf_payload,
)
from src.historical_province_sources import CNINFOAnnualReportClient


def test_parser_revision_is_canonical_and_runners_import_it():
    root = Path(__file__).resolve().parents[1]
    assert PARSER_REVISION == "issuer_scope_v3"
    assert recovery.PARSER_REVISION == PARSER_REVISION

    diagnostic_source = (root / "scripts/diagnose_cnipa_full_gaps_20260930.py").read_text(
        encoding="utf-8"
    )
    pilot_source = (root / "scripts/run_cnipa_targeted_diagnostic_pilot_20260930.py").read_text(
        encoding="utf-8"
    )
    assert "from src.cnipa_annual_report_names import PARSER_REVISION" in diagnostic_source
    assert "PARSER_REVISION as CURRENT_PARSER_REVISION" in pilot_source
    assert "issuer_scope_v3" not in diagnostic_source + pilot_source


def test_parser_module_does_not_reference_review_artifacts_or_company_fixtures():
    import pandas as pd

    root = Path(__file__).resolve().parents[1]
    parser_source = (root / "src/cnipa_annual_report_names.py").read_text(encoding="utf-8")
    assert "results/" not in parser_source.lower()
    assert "review_ground_truth" not in parser_source.lower()
    assert "parser_root_cause" not in parser_source.lower()

    corpus_path = (
        root
        / "results/cnipa_full_gap_diagnosis/r4c0_20261001/reviewed_h1_regression_corpus.csv"
    )
    if not corpus_path.is_file():
        return
    corpus = pd.read_csv(corpus_path, dtype=str, keep_default_na=False)
    runner_paths = (
        root / "scripts/run_cninfo_legal_name_recovery_20260929.py",
        root / "scripts/run_cnipa_targeted_diagnostic_pilot_20260930.py",
        root / "scripts/diagnose_cnipa_full_gaps_20260930.py",
    )
    source_tree = parser_source + "\n" + "\n".join(
        path.read_text(encoding="utf-8") for path in runner_paths
    )
    stock_codes = {str(key).split(":")[1] for key in corpus.firm_key}
    review_names = (
        set(corpus.review_legal_name_at_year_end)
        | set(corpus.review_previous_name)
        | set(corpus.review_new_name)
    )
    for literal in stock_codes | review_names:
        if len(literal) >= 6:
            assert literal not in source_tree


def test_legal_name_beginning_with_marker_character_is_preserved():
    text = """2021年年度报告全文
第二节 公司简介和主要财务指标
公司的中文名称 无锡祥生医疗科技股份有限公司
"""

    result = extract_annual_report_legal_name_evidence(
        text, expected_year=2021, source_report_title="2021年年度报告全文"
    )

    assert result["legal_name_current_in_report"] == "无锡祥生医疗科技股份有限公司"


def test_legal_name_beginning_with_ordinary_negative_character_is_preserved():
    assert _legal_value("否极泰来科技股份有限公司") == "否极泰来科技股份有限公司"


def test_standalone_response_marker_is_removed_only_at_token_boundary():
    assert _legal_value("无 | 华东材料科技股份有限公司") == "华东材料科技股份有限公司"
    assert _legal_value("否：华东材料科技股份有限公司") == "华东材料科技股份有限公司"
    assert _legal_value("不适用 华东材料科技股份有限公司") == "华东材料科技股份有限公司"


def test_marker_word_without_a_following_legal_name_is_not_a_name():
    assert _legal_value("无") == ""
    assert _legal_value("不适用") == ""


def test_ordinary_legal_name_is_unchanged_by_marker_handling():
    assert _legal_value("华东材料科技股份有限公司") == "华东材料科技股份有限公司"


def test_full_report_title_uses_matching_year_not_first_table_of_contents_title():
    text = """目录：2023年度报告摘要
正文开始
第二节 公司简介和主要财务指标
公司的中文名称 华东材料科技股份有限公司
2024年年度报告全文
"""

    result = extract_annual_report_legal_name_evidence(text, expected_year=2024)

    assert result["failure_reason"] == ""
    assert result["legal_name_at_year_end"] == "华东材料科技股份有限公司"


def test_full_report_title_supports_chinese_numerals_and_late_title_position():
    text = "\n".join(["前置说明"] * 120) + "\n二〇二四年年度报告全文\n"
    text += "第二节 公司简介和主要财务指标\n法定中文名称：华东材料科技股份有限公司\n"

    result = extract_annual_report_legal_name_evidence(text, expected_year=2024)

    assert result["failure_reason"] == ""
    assert result["legal_name_current_in_report"] == "华东材料科技股份有限公司"


def test_reference_to_an_annual_report_in_prose_is_not_a_report_title():
    text = """审计报告其他信息包括2020年年度报告中涵盖的信息。
2024年年度报告全文
公司基本情况
公司的中文名称：华东材料科技股份有限公司
"""

    result = extract_annual_report_legal_name_evidence(text, expected_year=2024)

    assert result["failure_reason"] == ""
    assert "2024年年度报告全文" in result["source_report_title"]


def test_full_report_body_is_not_rejected_for_an_earlier_summary_reference():
    text = """2024年度报告摘要（目录链接）
2024年年度报告全文
公司基本情况
公司注册中文名称：华东材料科技股份有限公司
"""

    result = extract_annual_report_legal_name_evidence(text, expected_year=2024)

    assert result["failure_reason"] == ""
    assert result["legal_name_at_year_end"] == "华东材料科技股份有限公司"


def test_report_title_year_mismatch_remains_rejected():
    result = extract_annual_report_legal_name_evidence(
        "2023年年度报告全文\n公司基本情况\n中文名称：华东材料科技股份有限公司",
        expected_year=2024,
    )

    assert result["failure_reason"] == "report_year_mismatch"


def test_missing_embedded_title_is_allowed_only_with_verified_full_report_metadata():
    text = """公司基本情况
公司的中文名称：华东材料科技股份有限公司
"""
    verified = extract_annual_report_legal_name_evidence(
        text,
        expected_year=2024,
        source_report_year=2024,
        source_is_official=True,
        source_is_correct_issuer=True,
        source_is_correct_year=True,
        source_is_full_annual_report=True,
    )
    unverified = extract_annual_report_legal_name_evidence(
        text,
        expected_year=2024,
        source_report_year=2024,
        source_is_official=True,
        source_is_correct_issuer=True,
        source_is_correct_year=True,
        source_is_full_annual_report=False,
    )

    assert verified["legal_name_at_year_end"] == "华东材料科技股份有限公司"
    assert unverified["failure_reason"] == "annual_report_title_not_found"


def test_supported_issuer_name_label_variants_require_basic_information_scope():
    for label in ("法定中文名称", "公司注册中文名称", "中文名称"):
        text = f"""2024年年度报告全文
第二节 公司简介和主要财务指标
一、公司基本情况
（一）{label}：华东材料科技股份有限公司
"""
        result = extract_annual_report_legal_name_evidence(text, expected_year=2024)
        assert result["legal_name_at_year_end"] == "华东材料科技股份有限公司"
        assert result["matched_label"] == label


def test_issuer_section_heading_variant_and_table_spacing_are_supported():
    text = """2024年年度报告全文
第三节 公司简介和主要财务指标
公司代码        600001
中文名称        华东材料科技股份有限公司
"""

    result = extract_annual_report_legal_name_evidence(text, expected_year=2024)

    assert result["legal_name_at_year_end"] == "华东材料科技股份有限公司"


def test_contents_heading_does_not_truncate_the_following_issuer_information_section():
    text = """2024年年度报告全文
公司简介和主要财务指标
第一节 重要提示
第二节 公司简介和主要财务指标
公司的中文名称：华东材料科技股份有限公司
第三节 管理层讨论与分析
"""

    result = extract_annual_report_legal_name_evidence(text, expected_year=2024)

    assert result["legal_name_at_year_end"] == "华东材料科技股份有限公司"


def test_label_value_on_next_line_and_multiline_legal_value_are_supported():
    text = """2024年年度报告全文
公司基本情况
公司的中文名称
华东材料科技
股份有限公司
"""

    result = extract_annual_report_legal_name_evidence(text, expected_year=2024)

    assert result["legal_name_at_year_end"] == "华东材料科技股份有限公司"


def test_basic_information_label_does_not_match_glossary_or_subsidiary_names():
    text = """2024年年度报告全文
释义
中文名称 指 子公司甲科技股份有限公司
公司基本情况
公司的中文名称：华东材料科技股份有限公司
子公司名称：子公司乙科技股份有限公司
"""

    result = extract_annual_report_legal_name_evidence(text, expected_year=2024)

    assert result["legal_name_at_year_end"] == "华东材料科技股份有限公司"


def test_issuer_exact_name_label_beats_earlier_low_confidence_table_candidates():
    text = """2024年年度报告全文
第二节 公司简介和主要财务指标
公司名称    控股子公司甲有限公司
公司的中文名称    华东材料科技股份有限公司
"""

    result = extract_annual_report_legal_name_evidence(text, expected_year=2024)

    assert result["legal_name_at_year_end"] == "华东材料科技股份有限公司"


def test_labelled_investee_name_is_not_selected_as_issuer_name():
    text = """2024年年度报告全文
公司基本情况
被投资单位中文名称：投资对象甲科技股份有限公司
公司的中文名称：华东材料科技股份有限公司
"""

    result = extract_annual_report_legal_name_evidence(text, expected_year=2024)

    assert result["legal_name_at_year_end"] == "华东材料科技股份有限公司"


def test_ticker_or_geographic_words_do_not_suppress_an_issuer_candidate():
    text = """2024年年度报告全文
公司基本情况
公司的中文名称：广东 TCL 智慧家电股份有限公司
"""

    result = extract_annual_report_legal_name_evidence(text, expected_year=2024)

    assert result["legal_name_at_year_end"] == "广东 TCL 智慧家电股份有限公司"


def test_nearby_unrelated_negative_answer_does_not_become_change_flag_no():
    text = """2024年年度报告全文
公司基本情况
公司的中文名称：华东材料科技股份有限公司
公司名称在报告期内是否变更
董事会换届情况
否
"""

    result = extract_annual_report_legal_name_evidence(text, expected_year=2024)

    assert result["company_name_change_flag"] == "UNKNOWN"
    assert result["evidence_status"] == "CONFIRMED_YEAR_END_NAME_ONLY"


def test_dated_change_outside_report_year_does_not_imply_explicit_no_change():
    text = """2024年年度报告全文
公司基本情况
公司的中文名称：华东材料科技股份有限公司
公司名称变更情况
2019年6月更名为华东材料科技股份有限公司
"""

    result = extract_annual_report_legal_name_evidence(text, expected_year=2024)

    assert result["company_name_change_flag"] == "UNKNOWN"
    assert result["evidence_status"] == "CONFIRMED_YEAR_END_NAME_ONLY"


def test_explicit_report_period_name_change_confirms_change_without_inventing_day():
    text = """2024年年度报告全文
公司基本情况
公司的中文名称：华东新材料科技股份有限公司
报告期内，公司名称由华东材料科技股份有限公司变更为华东新材料科技股份有限公司。
"""

    result = extract_annual_report_legal_name_evidence(text, expected_year=2024)

    assert result["company_name_change_flag"] == "YES"
    assert result["evidence_status"] == "CONFIRMED_NAME_CHANGE"
    assert result["date_precision"] == "year"
    assert result["change_effective_date"] == ""


def test_unrelated_nearby_date_is_not_attached_to_historical_name_change():
    text = """2023年年度报告全文
公司基本情况
公司的中文名称：华东材料科技股份有限公司
2024年3月6日，其他事项办理完成。
本公司名称由华东旧材料股份有限公司变更为华东材料科技股份有限公司。
"""

    result = extract_annual_report_legal_name_evidence(text, expected_year=2023)

    assert result["company_name_change_flag"] == "UNKNOWN"
    assert result["legal_name_at_year_end"] == "华东材料科技股份有限公司"
    assert result["evidence_status"] == "CONFIRMED_YEAR_END_NAME_ONLY"


def test_legacy_runner_main_delegates_to_canonical(monkeypatch):
    import scripts.run_cninfo_legal_name_recovery_20260927 as legacy
    import scripts.run_cninfo_legal_name_recovery_20260929 as canonical

    called = []
    monkeypatch.setattr(canonical, "main", lambda: called.append("canonical") or 7)

    assert legacy.main() == 7
    assert called == ["canonical"]


def test_legacy_runner_cli_imports_canonical_from_script_path():
    import subprocess
    import sys
    from pathlib import Path

    result = subprocess.run(
        [sys.executable, "scripts/run_cninfo_legal_name_recovery_20260927.py", "--help"],
        capture_output=True,
        text=True,
        check=False,
        cwd=Path(__file__).resolve().parents[1],
    )
    assert result.returncode == 0
    assert "--targeted-refresh-manifest" in result.stdout


def test_evidence_state_validator_rederives_expected_flag_from_facts():
    import pandas as pd

    from scripts.run_cninfo_legal_name_recovery_20260929 import (
        EVIDENCE_STATE_GT_COLUMNS,
        _validate_evidence_state_ground_truth,
    )

    valid = {
        "firm_key": "SSE:600001:2000-01-01",
        "year": 2024,
        "historical_change_occurrence": "YES",
        "historical_event_id": "event-1",
        "review_expected_parser_flag": "YES",
        "evidence_basis": "annual report",
        "evidence_tier": "H1",
        "reviewer_evidence_url": "https://official.test/report.pdf",
        "reviewer_evidence_title": "annual report",
        "reviewer_evidence_excerpt": "name changed",
        "explicit_no_change_disclosure": "NO",
        "verified_change_event_in_target_year": "YES",
        "verified_change_event_outside_target_year": "NO",
        "review_status": "PASS",
        "review_notes": "verified",
    }
    assert _validate_evidence_state_ground_truth(
        pd.DataFrame([valid], columns=EVIDENCE_STATE_GT_COLUMNS)
    )["valid"]

    contradictory = dict(valid, review_expected_parser_flag="UNKNOWN")
    result = _validate_evidence_state_ground_truth(
        pd.DataFrame([contradictory], columns=EVIDENCE_STATE_GT_COLUMNS)
    )
    assert not result["valid"]

    unsupported_no = dict(
        valid,
        review_expected_parser_flag="NO",
        historical_change_occurrence="NO",
        historical_event_id="",
        verified_change_event_in_target_year="NO",
    )
    assert not _validate_evidence_state_ground_truth(
        pd.DataFrame([unsupported_no], columns=EVIDENCE_STATE_GT_COLUMNS)
    )["valid"]

    outside_year_no = dict(
        unsupported_no,
        verified_change_event_outside_target_year="YES",
    )
    assert _validate_evidence_state_ground_truth(
        pd.DataFrame([outside_year_no], columns=EVIDENCE_STATE_GT_COLUMNS)
    )["valid"]

    silence = dict(
        valid,
        historical_change_occurrence="UNRESOLVED",
        historical_event_id="",
        review_expected_parser_flag="UNKNOWN",
        verified_change_event_in_target_year="NO",
    )
    assert _validate_evidence_state_ground_truth(
        pd.DataFrame([silence], columns=EVIDENCE_STATE_GT_COLUMNS)
    )["valid"]

    contradictory_facts = dict(
        valid, verified_change_event_outside_target_year="YES"
    )
    assert not _validate_evidence_state_ground_truth(
        pd.DataFrame([contradictory_facts], columns=EVIDENCE_STATE_GT_COLUMNS)
    )["valid"]


def test_targeted_manifest_rejects_duplicate_and_out_of_universe_keys(tmp_path, monkeypatch):
    import pandas as pd
    import pytest

    from scripts import run_cninfo_legal_name_recovery_20260929 as recovery

    monkeypatch.setattr(recovery, "FULL_TARGET_FIRM_YEARS", 2)
    expected = {("F1", 2020), ("F2", 2021)}
    path = tmp_path / "targets.csv"
    pd.DataFrame(
        [{"firm_key": "F1", "year": 2020, "reason": "stale parser"}]
    ).to_csv(path, index=False)
    manifest, pairs, fingerprint = recovery._load_targeted_refresh_manifest(path, expected)
    assert pairs == {("F1", 2020)}
    assert len(fingerprint) == 64
    assert len(manifest) == 1

    pd.DataFrame(
        [
            {"firm_key": "F1", "year": 2020, "reason": "first"},
            {"firm_key": "F1", "year": 2020, "reason": "duplicate"},
        ]
    ).to_csv(path, index=False)
    with pytest.raises(ValueError, match="DUPLICATE_KEYS"):
        recovery._load_targeted_refresh_manifest(path, expected)

    pd.DataFrame(
        [{"firm_key": "OUTSIDE", "year": 2020, "reason": "invalid"}]
    ).to_csv(path, index=False)
    with pytest.raises(ValueError, match="OUT_OF_TARGET_KEYS"):
        recovery._load_targeted_refresh_manifest(path, expected)


def test_targeted_refresh_replaces_only_manifest_rows(tmp_path, monkeypatch):
    import pandas as pd

    from scripts import run_cninfo_legal_name_recovery_20260929 as recovery

    monkeypatch.setattr(recovery, "FULL_TARGET_FIRM_YEARS", 2)
    expected = {("F1", 2020), ("F2", 2021)}
    baseline = pd.DataFrame(
        [
            {"firm_key": "F1", "year": 2020, "status": "PENDING", "detail": "old"},
            {"firm_key": "F2", "year": 2021, "status": "COMPLETE_NO_CHANGE", "detail": "keep"},
        ]
    )
    replacements = pd.DataFrame(
        [{"firm_key": "F1", "year": 2020, "status": "PENDING", "detail": "new"}]
    )
    result, fingerprints = recovery._replace_targeted_full_rows(
        baseline, replacements, {("F1", 2020)}, expected
    )
    assert len(result) == 2
    assert result.loc[result.firm_key.eq("F1"), "detail"].item() == "new"
    assert result.loc[result.firm_key.eq("F2"), "detail"].item() == "keep"
    assert fingerprints["non_target_before_sha256"] == fingerprints["non_target_after_sha256"]
    assert fingerprints["target_before_sha256"] != fingerprints["target_after_sha256"]


def test_targeted_refresh_baseline_must_match_exact_declared_full_size(tmp_path, monkeypatch):
    import pandas as pd
    import pytest

    from scripts import run_cninfo_legal_name_recovery_20260929 as recovery

    monkeypatch.setattr(recovery, "FULL_TARGET_FIRM_YEARS", 2)
    baseline = pd.DataFrame(
        [{"firm_key": "F1", "year": 2020, "status": "PENDING"}]
    )
    with pytest.raises(ValueError, match="BASELINE_ROW_COUNT_MISMATCH"):
        recovery._validate_full_baseline(baseline, {("F1", 2020), ("F2", 2021)})


def test_targeted_resume_ignores_stale_cache_rows_outside_manifest(tmp_path):
    import json

    from scripts.run_cninfo_legal_name_recovery_20260929 import _load_status_cache

    target = ("F1", 2020)
    outside = ("F2", 2021)
    (tmp_path / "target.json").write_text(
        json.dumps(
            {
                "firm_key": target[0],
                "year": target[1],
                "status": "PENDING",
                    "parser_revision": "issuer_scope_v3",
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "outside-stale.json").write_text(
        json.dumps(
            {
                "firm_key": outside[0],
                "year": outside[1],
                "status": "PENDING",
                "parser_revision": "old_revision",
            }
        ),
        encoding="utf-8",
    )
    loaded = _load_status_cache(tmp_path, {target})
    assert set(loaded) == {target}
    assert outside not in loaded


def test_complete_full_resume_with_stale_success_cache_is_hard_blocked(tmp_path, monkeypatch):
    import json

    import pandas as pd
    import pytest

    from scripts import run_cninfo_legal_name_recovery_20260929 as recovery

    monkeypatch.setattr(recovery, "FULL_TARGET_FIRM_YEARS", 2)
    expected = {("F1", 2020), ("F2", 2021)}
    status_path = tmp_path / "full_status.csv"
    state_path = tmp_path / "full_run_state.json"
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir()
    pd.DataFrame(
        [
            {"firm_key": "F1", "year": 2020, "status": "PENDING"},
            {"firm_key": "F2", "year": 2021, "status": "REPORT_NOT_FOUND"},
        ]
    ).to_csv(status_path, index=False)
    state_path.write_text(
        json.dumps(
            {
                "stage": "full",
                "status": "COMPLETE",
                "status_key_set_exact": True,
                "target_firm_years": 2,
            }
        ),
        encoding="utf-8",
    )
    (cache_dir / "stale.json").write_text(
        json.dumps(
            {
                "firm_key": "F1",
                "year": 2020,
                "status": "PENDING",
                "parser_revision": "old_revision",
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="FULL_WIDE_REPARSE_BLOCKED"):
        recovery._guard_full_resume_against_wide_stale_reparse(
            status_path, state_path, cache_dir, expected
        )


def _event_row(**overrides):
    row = {
        "firm_key": "SSE:600001:2000-01-01",
        "year": 2024,
        "company_name_change_flag": "YES",
        "legal_name_previous": "甲股份有限公司",
        "legal_name_new": "乙股份有限公司",
        "change_effective_date": "2024-06-10",
        "date_precision": "exact_date",
        "change_evidence_tier": "H2",
        "change_evidence_url": "https://notice.test/one.pdf",
        "change_announcement_id": "notice-1",
        "evidence_status": "CONFIRMED_NAME_CHANGE",
        "failure_reason": "",
        "change_case_reviewed": "",
        "evidence_context": "公司名称由甲股份有限公司变更为乙股份有限公司",
        "legal_name_at_year_end": "乙股份有限公司",
    }
    row.update(overrides)
    return row


def test_change_candidate_includes_independent_qualifying_signals():
    assert is_change_related_candidate(_event_row())
    assert is_change_related_candidate(_event_row(company_name_change_flag="NO"))
    assert is_change_related_candidate(
        _event_row(
            company_name_change_flag="NO",
            legal_name_previous="",
            legal_name_new="",
            change_evidence_tier="H2",
        )
    )
    assert not is_change_related_candidate(
        _event_row(
            company_name_change_flag="NO",
            legal_name_previous="",
            legal_name_new="",
            change_evidence_tier="",
            change_evidence_url="",
            evidence_context="",
        )
    )
    assert is_change_related_candidate(
        _event_row(
            company_name_change_flag="NO",
            legal_name_previous="",
            legal_name_new="",
            change_evidence_tier="",
            change_evidence_url="",
            change_case_reviewed="YES",
        )
    )
    assert is_change_related_candidate(
        _event_row(
            company_name_change_flag="NO",
            legal_name_previous="",
            legal_name_new="",
            change_evidence_tier="",
            change_evidence_url="",
            evidence_context="",
            evidence_status="TEMPORAL_UNRESOLVED",
            failure_reason="名称时间无法确定",
        )
    )
    assert is_change_related_candidate(
        _event_row(
            company_name_change_flag="NO",
            legal_name_previous="",
            legal_name_new="",
            change_evidence_tier="",
            change_evidence_url="",
            evidence_context="",
        ),
        adjacent_year_name_change=True,
    )
    assert is_change_related_candidate(
        _event_row(
            company_name_change_flag="NO",
            legal_name_previous="",
            legal_name_new="",
            change_evidence_tier="",
            change_evidence_url="",
            evidence_context="公司名称由甲股份有限公司变更为乙股份有限公司",
        )
    )


def test_one_change_event_can_map_to_multiple_firm_year_rows():
    first = _event_row(year=2023)
    second = _event_row(year=2024, change_announcement_id="notice-1")

    events, row_mapping = build_canonical_change_event_roster([first, second])

    assert len(events) == 1
    assert (
        events[0]["source_firm_year_rows"]
        == "SSE:600001:2000-01-01|2023;SSE:600001:2000-01-01|2024"
    )
    assert row_mapping["SSE:600001:2000-01-01|2023"] == events[0]["event_id"]
    assert row_mapping["SSE:600001:2000-01-01|2024"] == events[0]["event_id"]


def test_same_name_pair_with_distinct_exact_dates_remains_two_events():
    first = _event_row(change_effective_date="2023-06-10", year=2023)
    second = _event_row(
        change_effective_date="2024-06-10", year=2024, change_announcement_id="notice-2"
    )

    events, _ = build_canonical_change_event_roster([first, second])

    assert len(events) == 2
    assert len({event["event_id"] for event in events}) == 2


def test_announcement_id_is_preferred_for_event_identity():
    first = _event_row(change_effective_date="2024-06-10")
    second = _event_row(year=2025, change_effective_date="2024-06-11")

    events, mapping = build_canonical_change_event_roster([first, second])

    assert len(events) == 1
    assert mapping["SSE:600001:2000-01-01|2024"] == mapping["SSE:600001:2000-01-01|2025"]


def test_exact_date_and_issuer_pair_can_confirm_same_event_across_notices():
    first = _event_row(change_announcement_id="notice-a")
    second = _event_row(year=2025, change_announcement_id="notice-b")

    events, _ = build_canonical_change_event_roster([first, second])

    assert len(events) == 1
    assert events[0]["date_precision"] == "exact_date"


def test_year_precision_events_deduplicate_only_with_same_official_notice():
    first = _event_row(
        change_effective_date="", date_precision="year", change_announcement_id="notice-year"
    )
    second = _event_row(
        year=2025,
        change_effective_date="",
        date_precision="year",
        change_announcement_id="notice-year",
    )
    unsupported = _event_row(
        year=2026,
        change_effective_date="",
        date_precision="year",
        change_announcement_id="",
        change_evidence_url="",
    )

    events, mapping = build_canonical_change_event_roster([first, second, unsupported])

    assert len(events) == 2
    assert mapping["SSE:600001:2000-01-01|2024"] == mapping["SSE:600001:2000-01-01|2025"]
    assert next(event for event in events if event["event_verification_status"] == "UNRESOLVED")


def test_unresolved_same_name_candidates_are_not_silently_merged():
    first = _event_row(
        change_effective_date="",
        date_precision="unknown",
        change_announcement_id="",
        change_evidence_url="",
    )
    second = _event_row(
        year=2025,
        change_effective_date="",
        date_precision="unknown",
        change_announcement_id="",
        change_evidence_url="",
    )

    events, mapping = build_canonical_change_event_roster([first, second])

    assert len(events) == 2
    assert mapping["SSE:600001:2000-01-01|2024"] != mapping["SSE:600001:2000-01-01|2025"]
    assert {event["event_verification_status"] for event in events} == {"UNRESOLVED"}


def test_duplicate_candidate_firm_year_keys_are_rejected():
    import pytest

    row = _event_row()
    with pytest.raises(ValueError, match="DUPLICATE_CHANGE_CANDIDATE_ROW_KEY"):
        build_canonical_change_event_roster([row, dict(row)])


def _strict_summary_fixture(sample, targets, audit, roster):
    return {
        "schema": "cnipa_strict_pilot_gate_v1",
        "status": "STRICT_PILOT_GATE_PASS",
        "seed": "20260927",
        "pilot_gate_pass": True,
        "status_key_set_exact": True,
        "pilot_firms": 80,
        "target_firm_years": 80,
        "case_roster_reconciled": True,
        "sample_fingerprint": _frame_fingerprint(sample),
        "target_fingerprint": _frame_fingerprint(targets),
        "source_evidence_fingerprint": _frame_fingerprint(audit),
        "case_roster_fingerprint": _frame_fingerprint(roster),
        "review_complete": True,
        "reviewed_case_ids": ["case-1"],
        "change_case_denominator": 1,
        "metrics": {
            "legal_name_precision": 1.0,
            "security_abbreviation_false_positives": 0,
            "human_audit_unreviewed": 0,
            "company_name_change_flag_accuracy": 1.0,
            "previous_name_accuracy": 1.0,
            "new_name_accuracy": 1.0,
        },
    }


def test_strict_pilot_summary_must_match_fingerprints_and_reviews():
    import pandas as pd

    sample = pd.DataFrame([{"firm_key": f"SSE:{i:06}:2000-01-01"} for i in range(80)])
    targets = pd.DataFrame(
        [{"firm_key": row.firm_key, "year": 2024} for row in sample.itertuples()]
    )
    audit = pd.DataFrame([{"source_url": "https://example.test/report.pdf"}])
    roster = pd.DataFrame(
        [
            {
                "case_id": "case-1",
                "firm_key": sample.firm_key.iloc[0],
                "year": 2024,
                "review_status": "PASS",
                "manual_change_flag": "YES",
                "parser_change_flag": "YES",
                "parser_legal_name_at_year_end": "乙股份有限公司",
                "manual_previous_name": "甲股份有限公司",
                "manual_new_name": "乙股份有限公司",
                "review_evidence_url": "https://example.test/notice.pdf",
            }
        ]
    )
    summary = _strict_summary_fixture(sample, targets, audit, roster)

    assert not _strict_pilot_authorized(summary, sample, targets, audit, roster)
    assert not _strict_pilot_authorized(
        summary, sample.assign(firm_key="SZSE:000001:2000-01-01"), targets, audit, roster
    )
    assert not _strict_pilot_authorized(
        {**summary, "review_complete": False}, sample, targets, audit, roster
    )
    assert not _strict_pilot_authorized(
        {**summary, "change_case_denominator": 2}, sample, targets, audit, roster
    )
    assert not _strict_pilot_authorized(
        summary, sample, targets, audit, roster.assign(review_status="PENDING")
    )


def test_legacy_pilot_pass_cannot_authorize_full():
    import pandas as pd

    sample = pd.DataFrame([{"firm_key": f"SSE:{i:06}:2000-01-01"} for i in range(80)])
    targets = pd.DataFrame(
        [{"firm_key": row.firm_key, "year": 2024} for row in sample.itertuples()]
    )
    audit = pd.DataFrame([{"source_url": "https://example.test/report.pdf"}])
    legacy = {"status": "COMPLETE", "pilot_gate_pass": True}

    assert not _strict_pilot_authorized(legacy, sample, targets, audit, pd.DataFrame())


def test_rerun_preserves_manual_fields_only_when_source_identity_matches():
    import pandas as pd

    evidence = {
        "firm_key": "SSE:600001:2000-01-01",
        "year": 2024,
        "legal_name_current_in_report": "甲股份有限公司",
        "legal_name_at_year_end": "甲股份有限公司",
        "company_name_change_flag": "NO",
        "legal_name_previous": "",
        "legal_name_new": "",
        "change_effective_date": "",
        "change_evidence_url": "",
        "change_pdf_sha256": "",
    }
    prior = pd.DataFrame(
        [
            {
                **evidence,
                "human_audit_status": "PASS",
                "audited_legal_name": "甲股份有限公司",
            }
        ]
    )

    same = _preserve_manual_audit(pd.DataFrame([evidence]), prior)
    changed = _preserve_manual_audit(
        pd.DataFrame([{**evidence, "legal_name_at_year_end": "乙股份有限公司"}]), prior
    )

    assert same.loc[0, "human_audit_status"] == "PASS"
    assert same.loc[0, "audited_legal_name"] == "甲股份有限公司"
    assert changed.loc[0, "human_audit_status"] == ""


def test_name_parser_has_no_pilot_issuer_specific_code_branches():
    from pathlib import Path

    parser = Path("src/cnipa_annual_report_names.py").read_text(encoding="utf-8")
    runner = Path("scripts/run_cninfo_legal_name_recovery_20260929.py").read_text(encoding="utf-8")

    for stock_code in ("300237", "600936", "603003", "603196", "300365"):
        assert stock_code not in parser
        assert stock_code not in runner


def test_finalize_pilot_does_not_promote_unreconciled_legacy_summary(tmp_path, monkeypatch):
    import json

    import pandas as pd

    import scripts.run_cninfo_legal_name_recovery_20260929 as recovery_script

    monkeypatch.setattr(recovery_script, "OUTPUT", tmp_path)
    sample = pd.DataFrame([{"firm_key": "SSE:600001:2000-01-01"}])
    targets = pd.DataFrame([{"firm_key": "SSE:600001:2000-01-01", "year": 2024}])
    status = targets.assign(status="COMPLETE_NO_CHANGE")
    audit = pd.DataFrame(
        [
            {
                "firm_key": "SSE:600001:2000-01-01",
                "year": 2024,
                "legal_name_current_in_report": "甲股份有限公司",
                "legal_name_at_year_end": "甲股份有限公司",
                "company_name_change_flag": "NO",
                "legal_name_previous": "",
                "legal_name_new": "",
                "human_audit_status": "PASS",
                "audited_legal_name": "甲股份有限公司",
                "abbreviation_false_positive": "0",
                "change_case_reviewed": "",
                "audited_change_flag": "",
                "audited_previous_legal_name": "",
                "audited_new_legal_name": "",
                "source_url": "https://example.test/report.pdf",
            }
        ]
    )
    sample.to_csv(tmp_path / "pilot_sample.csv", index=False)
    targets.to_csv(tmp_path / "pilot_firm_year_targets.csv", index=False)
    status.to_csv(tmp_path / "pilot_status.csv", index=False)
    audit.to_csv(tmp_path / "pilot_context_audit.csv", index=False)
    legacy = {"status": "COMPLETE", "pilot_gate_pass": True, "name_change_case_firm_years": 6}
    (tmp_path / "pilot_summary.json").write_text(json.dumps(legacy), encoding="utf-8")

    strict = recovery_script._finalize_pilot_audit()

    assert strict["pilot_gate_pass"] is False
    assert strict["change_case_denominator"] is None
    assert "FROZEN_CASE_ROSTER_MISSING_OR_INVALID" in strict["failure_reasons"]
    assert json.loads((tmp_path / "pilot_summary.json").read_text(encoding="utf-8")) == legacy


def test_full_run_fallback_accepts_cninfo_list_annual_reports_source_url():
    report_url = "https://static.cninfo.com.cn/finalpage/2023-04-18/1216438315.PDF"

    class Client:
        def extract_pdf_text_with_metadata(self, url):
            assert url == report_url
            return (
                "2022年年度报告全文\n"
                "公司的中文名称 深圳市广聚能源股份有限公司\n"
                "公司名称在报告期内是否变更 否",
                {"pdf_bytes": 12, "pdf_sha256": "a" * 64},
            )

    report_index = {
        "000096": [
            {
                "report_year": 2022,
                "title": "深圳市广聚能源股份有限公司2022年年度报告全文",
                "source_url": report_url,
                "announcement_id": "1216438315",
            }
        ]
    }

    result = _process_one(
        Client(),
        {"firm_key": "SZSE:000096:2000-07-24", "stock_code_current": "000096"},
        2022,
        None,
        report_index,
    )

    assert result["status"] == "COMPLETE_NO_CHANGE"
    assert result["source_url"] == report_url
    assert result["source_announcement_id"] == "1216438315"
    assert result["fallback_used"] == 1


def test_extracts_wrapped_chinese_legal_name_and_no_change_disclosure():
    text = """
2024年年度报告
公司的中文名称
华东材料科技股份
有限公司
公司的中文简称 华材科技
A股简称 *ST华材
公司名称在报告期内是否变更 否
"""

    result = extract_annual_report_legal_name_evidence(
        text, expected_year=2024, source_report_title="华东材料2024年年度报告全文"
    )

    assert result["legal_name_current_in_report"] == "华东材料科技股份有限公司"
    assert result["company_name_change_flag"] == "NO"
    assert result["evidence_status"] == "CONFIRMED_NO_CHANGE"
    assert "*ST华材" not in result["legal_name_current_in_report"]
    assert "公司的中文名称" in result["evidence_context"]


def test_never_uses_security_or_short_name_labels_as_legal_name():
    text = """
2024年年度报告
公司中文简称 华材科技
证券简称 ST华材
股票简称 *ST华材
A股简称 G华材
"""

    result = extract_annual_report_legal_name_evidence(
        text, expected_year=2024, source_report_title="2024年年度报告"
    )

    assert result["legal_name_current_in_report"] == ""
    assert result["evidence_status"] == "LEGAL_NAME_EXTRACTION_FAILED"


def test_bare_chinese_name_label_in_subsidiary_text_is_not_issuer_legal_name():
    result = extract_annual_report_legal_name_evidence(
        "2022年年度报告\nCanalyst Financial Modeling Corporation（中文名称：卡纳利斯特）"
        "\n丝路控股指丝路控股集团有限公司",
        expected_year=2022,
        source_report_title="2022年年度报告全文",
    )
    assert result["legal_name_current_in_report"] == ""


def test_official_company_information_section_outweighs_glossary_and_branch_name():
    text = """
2021年年度报告全文
释义
北辰科技 指 北辰新材科技发展有限公司，股份改制前公司名称
海滨分公司 指 北辰新材科技股份有限公司海滨分公司
第二节 公司简介和主要财务指标
一、公司信息
公司的中文名称 北辰新材科技股份有限公司
"""
    result = extract_annual_report_legal_name_evidence(
        text, expected_year=2021, source_report_title="2021年年度报告全文"
    )
    assert result["legal_name_current_in_report"] == "北辰新材科技股份有限公司"
    assert "公司的中文名称 北辰新材科技股份有限公司" in result["evidence_context"]


def test_no_explicit_issuer_name_change_disclosure_remains_unknown():
    text = """
2021年年度报告全文
释义
海滨分公司 指 北辰新材科技股份有限公司海滨分公司
第二节 公司简介和主要财务指标
一、公司信息
公司的中文名称 北辰新材科技股份有限公司
公司注册地址历史变更情况 本报告期未发生注册地址变更
"""
    result = extract_annual_report_legal_name_evidence(
        text, expected_year=2021, source_report_title="2021年年度报告全文"
    )
    assert result["company_name_change_flag"] == "UNKNOWN"


def test_explicit_split_issuer_name_change_field_skips_blank_layout_lines():
    text = """
2024年年度报告
第二节 公司简介和主要财务指标
一、公司信息
公司的中文名称 华东材料科技股份有限公司
公司名称在报告期内是否变更

    否
"""
    result = extract_annual_report_legal_name_evidence(
        text, expected_year=2024, source_report_title="2024年年度报告全文"
    )
    assert result["company_name_change_flag"] == "NO"


def test_extracts_old_and_new_full_legal_names_with_exact_effective_date():
    text = """
2023年年度报告全文
公司的中文名称 华东材料科技股份有限公司
公司名称在报告期内是否变更 是
变更前公司名称 华东新材料股份有限公司
变更后公司名称 华东材料科技股份有限公司于2023年6月10日完成工商变更登记。
"""

    result = extract_annual_report_legal_name_evidence(
        text, expected_year=2023, source_report_title="2023年年度报告全文"
    )

    assert result["company_name_change_flag"] == "YES"
    assert result["legal_name_previous"] == "华东新材料股份有限公司"
    assert result["legal_name_new"] == "华东材料科技股份有限公司"
    assert result["change_effective_date"] == "2023-06-10"
    assert result["date_precision"] == "exact_date"
    assert result["temporal_match_uncertain"] == 0
    assert result["evidence_status"] == "CONFIRMED_NAME_CHANGE"


def test_name_change_without_exact_date_uses_year_precision_and_uncertainty():
    text = """
2022年年度报告
公司中文名称 华东材料科技股份有限公司
公司名称在报告期内是否变更 是
变更前公司名称 华东新材料股份有限公司
变更后公司名称 华东材料科技股份有限公司
"""

    result = extract_annual_report_legal_name_evidence(
        text, expected_year=2022, source_report_title="2022年年度报告"
    )

    assert result["date_precision"] == "year"
    assert result["valid_from"] == "2022"
    assert result["valid_to"] == "2022"
    assert result["temporal_match_uncertain"] == 1


def test_unrelated_company_date_is_not_attributed_to_issuer_name_change():
    text = """
2022年年度报告
公司中文名称 华东材料科技股份有限公司
公司名称在报告期内是否变更 是
变更前公司名称 华东新材料股份有限公司
变更后公司名称 华东材料科技股份有限公司

其他事项：子公司甲有限公司于2022年7月4日完成名称登记。






发行人于2022年12月9日完成股权登记。
"""
    result = extract_annual_report_legal_name_evidence(
        text, expected_year=2022, source_report_title="2022年年度报告"
    )
    assert result["change_effective_date"] == ""
    assert result["evidence_status"] == "TEMPORAL_UNRESOLVED"


def test_historical_change_pair_does_not_imply_no_change_in_report_year():
    text = """
2022年年度报告
公司的中文名称 云南旅游股份有限公司
（三）公司名称变更
本公司于2010年8月26日召开临时股东大会，审议名称变更议案。
将公司名称及证券简称自 2010年9月16日变更。
原公司名称：

全称：昆明世博园股份有限公司

现更名为：

全称：云南旅游股份有限公司
（四）公司目前注册登记情况
"""
    result = extract_annual_report_legal_name_evidence(
        text, expected_year=2022, source_report_title="云南旅游2022年年度报告全文"
    )
    assert result["company_name_change_flag"] == "UNKNOWN"
    assert result["legal_name_previous"] == "昆明世博园股份有限公司"
    assert result["legal_name_new"] == "云南旅游股份有限公司"
    assert result["change_effective_date"] == "2010-09-16"
    assert result["date_precision"] == "exact_date"
    assert result["evidence_status"] == "CONFIRMED_YEAR_END_NAME_ONLY"


def test_does_not_treat_subsidiary_old_name_labels_as_issuer_name_history():
    text = """
2024年年度报告
公司的中文名称 华东材料科技股份有限公司
子公司历史沿革：原公司名称
全称：昆明世博园股份有限公司
新公司名称：
全称：昆明旅游服务有限公司
"""
    result = extract_annual_report_legal_name_evidence(
        text, expected_year=2024, source_report_title="2024年年度报告全文"
    )
    assert result["legal_name_current_in_report"] == "华东材料科技股份有限公司"
    assert result["legal_name_previous"] == ""
    assert result["legal_name_new"] == ""


def test_name_change_without_both_full_names_remains_temporally_unresolved():
    text = """
2021年年度报告
公司中文名称 华东材料科技股份有限公司
公司名称在报告期内是否变更 是
变更前公司名称 华东新材料
"""

    result = extract_annual_report_legal_name_evidence(
        text, expected_year=2021, source_report_title="2021年年度报告"
    )

    assert result["evidence_status"] == "TEMPORAL_UNRESOLVED"
    assert result["legal_name_previous"] == ""
    assert result["temporal_match_uncertain"] == 1


def test_rejects_annual_report_summary_and_wrong_report_year():
    summary = extract_annual_report_legal_name_evidence(
        "2024年年度报告摘要 公司中文名称 华东材料科技股份有限公司",
        expected_year=2024,
        source_report_title="2024年年度报告摘要",
    )
    wrong_year = extract_annual_report_legal_name_evidence(
        "2023年年度报告 公司中文名称 华东材料科技股份有限公司",
        expected_year=2024,
        source_report_title="华东材料2024年年度报告全文",
    )

    assert summary["failure_reason"] == "annual_report_summary_rejected"
    assert wrong_year["failure_reason"] == "report_year_mismatch"


def test_rejects_summary_title_found_in_pdf_text_without_metadata_title():
    result = extract_annual_report_legal_name_evidence(
        "2024年年度报告摘要\n公司中文名称 华东材料科技股份有限公司",
        expected_year=2024,
    )
    assert result["failure_reason"] == "annual_report_summary_rejected"


def test_rejects_pdf_payload_that_is_short_or_not_a_pdf():
    assert validate_pdf_payload(b"%PDF-1.7 short")["failure_reason"] == "pdf_too_small"
    assert validate_pdf_payload(b"<html>blocked</html>" * 200)["failure_reason"] == (
        "response_not_pdf"
    )


def test_hashes_valid_pdf_payload_without_persisting_it():
    payload = b"%PDF-1.7\n" + (b"x" * 4096)

    result = validate_pdf_payload(payload)

    assert result["http_status"] == 200
    assert result["pdf_bytes"] == len(payload)
    assert len(result["pdf_sha256"]) == 64
    assert "pdf_content" not in result


def test_status_manifest_must_equal_target_firm_year_set():
    target = {("firm-a", 2020), ("firm-a", 2021)}
    assert validate_firm_year_status_set(target, target) is True
    assert validate_firm_year_status_set(target, {("firm-a", 2020)}) is False


def test_resume_reuses_completed_and_pending_records_without_retrieval(tmp_path):
    import json

    completed = {
        "firm_key": "firm-a",
        "year": 2020,
        "status": "COMPLETE_NO_CHANGE",
            "parser_revision": "issuer_scope_v3",
    }
    pending = {
        "firm_key": "firm-a",
        "year": 2021,
        "status": "PENDING",
            "parser_revision": "issuer_scope_v3",
    }
    for index, record in enumerate((completed, pending)):
        (tmp_path / f"{index}.json").write_text(json.dumps(record), encoding="utf-8")
    target = {("firm-a", 2020), ("firm-a", 2021)}
    loaded = _load_status_cache(tmp_path, target)
    assert set(loaded) == target
    assert _coverage_status(completed) == "CONFIRMED_NO_CHANGE"
    uncertain_completed = {
        **completed,
        "evidence_status": "TEMPORAL_UNRESOLVED",
    }
    assert _coverage_status(uncertain_completed) == "TEMPORAL_UNRESOLVED"
    assert _coverage_status({"status": "COMPLETE_NAME_CHANGE"}) == ("CONFIRMED_NAME_CHANGE")
    assert _coverage_status({"status": "PENDING"}) == ("CONFIRMED_YEAR_END_NAME_ONLY")
    assert _coverage_status({**pending, "evidence_status": "TEMPORAL_UNRESOLVED"}) == (
        "TEMPORAL_UNRESOLVED"
    )


def test_source_blocked_and_retryable_failures_are_explicit_statuses(tmp_path):
    import json

    rows = [
        {"firm_key": "firm-a", "year": 2020, "status": "SOURCE_BLOCKED"},
        {"firm_key": "firm-a", "year": 2021, "status": "PDF_FETCH_FAILED"},
        {"firm_key": "firm-a", "year": 2022, "status": "REPORT_NOT_FOUND"},
    ]
    for index, record in enumerate(rows):
        (tmp_path / f"{index}.json").write_text(json.dumps(record), encoding="utf-8")
    target = {("firm-a", 2020), ("firm-a", 2021), ("firm-a", 2022)}
    assert len(_load_status_cache(tmp_path, target)) == 3
    retried = _load_status_cache(tmp_path, target, retry_failures=True)
    assert set(retried) == {("firm-a", 2022)}
    assert _coverage_status(rows[0]) == "SOURCE_BLOCKED"
    assert _coverage_status(rows[1]) == "REPORT_FETCH_FAILED"
    assert _coverage_status(rows[2]) == "REPORT_NOT_FOUND"


def test_resume_does_not_reuse_successful_records_from_an_old_parser_revision(tmp_path):
    import json

    stale = {
        "firm_key": "firm-a",
        "year": 2021,
        "status": "PENDING",
        "legal_name_current_in_report": "旧解析结果股份有限公司",
    }
    (tmp_path / "stale.json").write_text(json.dumps(stale), encoding="utf-8")
    assert _load_status_cache(tmp_path, {("firm-a", 2021)}) == {}


def test_pilot_sample_is_deterministic_unique_and_stratified():
    import pandas as pd

    rows = []
    for exchange in ("SSE", "SZSE"):
        for index in range(40):
            listing = "1995-01-01" if index < 20 else f"202{index % 5}-01-01"
            delisted = "2024-01-01" if 20 <= index < 30 else None
            rows.append(
                {
                    "firm_key": f"{exchange}:{index:06d}:{listing}",
                    "exchange": exchange,
                    "market_listing_date": listing,
                    "delisting_date": delisted,
                }
            )
    firms = pd.DataFrame(rows)
    first = select_legal_name_pilot(firms, seed="20260927")
    second = select_legal_name_pilot(firms, seed="20260927")
    assert first.firm_key.tolist() == second.firm_key.tolist()
    assert first.firm_key.is_unique
    assert len(first) >= 80
    assert {
        "SSE_current",
        "SZSE_current",
        "SSE_delisted",
        "SZSE_delisted",
        "recent_IPO",
        "long_listed",
    }.issubset(set(first.pilot_stratum))


def test_pdf_download_returns_digest_metadata_but_not_payload(monkeypatch, tmp_path):
    import hashlib
    from types import SimpleNamespace

    import src.historical_province_sources as source_module

    payload = b"%PDF-1.7\n" + b"x" * 4096

    class StubSession:
        headers = {}

        def request(self, method, url, timeout, **kwargs):
            return SimpleNamespace(status_code=200, text="", content=payload)

    monkeypatch.setattr(source_module.shutil, "which", lambda _: "pdftotext")
    monkeypatch.setattr(
        source_module.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(returncode=0, stdout=b"report text " * 30),
    )
    client = CNINFOAnnualReportClient(tmp_path, session=StubSession(), sleep=lambda _: None)
    text, metadata = client.extract_pdf_text_with_metadata("https://example.invalid/a.pdf")
    assert text.startswith("report text")
    assert metadata["pdf_sha256"] == hashlib.sha256(payload).hexdigest()
    assert metadata["pdf_bytes"] == len(payload)
    assert metadata["pdf_content_persisted"] is False
    assert "pdf_content" not in metadata


def test_issuer_name_change_disclosed_in_body_is_temporally_attributed():
    report = (
        "2022年年度报告\n"
        "公司的中文名称 上海龙宇数据股份有限公司\n"
        "报告期内，公司启动实施了战略更名计划，并于 2023 年 1 月 9 日完成了公司名称以及公司章程的"
        "工商变更登记手续，公司全称已正式变更为“上海龙宇数据股份有限公司”。\n"
        "2023 年 1 月 5 日，公司名称正式由上海龙宇燃油股份有限公司变更为"
        "上海龙宇数据股份有限公司。\n"
        "其他说明：2022年8月，被购买方公司名称由上海磐石瑞辰投资管理有限公司变更为上海磐石边缘云计算有限公司。\n"
    )

    evidence = extract_annual_report_legal_name_evidence(
        report,
        expected_year=2022,
        source_report_title="2022 年年度报告",
    )

    assert evidence["legal_name_previous"] == "上海龙宇燃油股份有限公司"
    assert evidence["legal_name_new"] == "上海龙宇数据股份有限公司"
    assert evidence["change_effective_date"] == "2023-01-05"
    assert evidence["company_name_change_flag"] == "UNKNOWN"
    assert evidence["evidence_status"] == "CONFIRMED_YEAR_END_NAME_ONLY"
    assert evidence["legal_name_at_year_end"] == "上海龙宇燃油股份有限公司"


def test_post_year_end_name_change_does_not_rewrite_fiscal_year_name():
    report = (
        "2025年年度报告\n"
        "公司的中文名称 上海璞源化学材料集团股份有限公司\n"
        "本公司已于 2026 年 3 月 10 日完成工商变更，并换取新的营业执照，"
        "公司名称由日播时尚集团股份有限公司变更为上海璞源化学材料集团股份有限公司。\n"
    )

    evidence = extract_annual_report_legal_name_evidence(
        report,
        expected_year=2025,
        source_report_title="上海璞源化学材料集团股份有限公司2025 年年度报告",
    )

    assert evidence["company_name_change_flag"] == "UNKNOWN"
    assert evidence["legal_name_current_in_report"] == "上海璞源化学材料集团股份有限公司"
    assert evidence["legal_name_at_year_end"] == "日播时尚集团股份有限公司"
    assert evidence["change_effective_date"] == "2026-03-10"


def test_historical_exact_name_change_does_not_assert_report_year_no_without_field():
    report = (
        "2020年年度报告\n"
        "公司的中文名称 云南旅游股份有限公司\n"
        "公司名称于2010年9月16日由昆明世博园股份有限公司变更为云南旅游股份有限公司。\n"
    )
    evidence = extract_annual_report_legal_name_evidence(
        report, expected_year=2020, source_report_title="2020年年度报告"
    )
    assert evidence["company_name_change_flag"] == "UNKNOWN"
    assert evidence["legal_name_at_year_end"] == "云南旅游股份有限公司"
    assert evidence["evidence_status"] == "CONFIRMED_YEAR_END_NAME_ONLY"


def test_candidate_builder_includes_union_of_change_signals_and_adjacent_names():
    import pandas as pd

    audit = pd.DataFrame(
        [
            _event_row(
                firm_key="SSE:600001:2000-01-01",
                year=2023,
                company_name_change_flag="NO",
                legal_name_previous="",
                legal_name_new="",
                evidence_context="",
                change_case_reviewed="",
            ),
            _event_row(firm_key="SSE:600001:2000-01-01", year=2024),
            _event_row(
                firm_key="SSE:600002:2000-01-01",
                year=2024,
                company_name_change_flag="NO",
                legal_name_previous="",
                legal_name_new="",
                evidence_context="",
                change_case_reviewed="",
                change_evidence_url="",
                change_announcement_id="",
                change_evidence_tier="",
            ),
        ]
    )
    audit.loc[0, "legal_name_at_year_end"] = "甲股份有限公司"
    audit.loc[1, "legal_name_at_year_end"] = "乙股份有限公司"
    audit.loc[2, "legal_name_at_year_end"] = "丙股份有限公司"
    statuses = pd.DataFrame(
        [
            {
                "firm_key": row.firm_key,
                "year": row.year,
                "source_url": f"https://reports.test/{row.firm_key}/{row.year}.pdf",
            }
            for row in audit.itertuples()
        ]
    )
    candidates = _build_pilot_change_candidate_rows(audit, statuses)
    assert list(zip(candidates.firm_key, candidates.year.astype(int))) == [
        ("SSE:600001:2000-01-01", 2023),
        ("SSE:600001:2000-01-01", 2024),
    ]
    assert candidates.source_report_url.str.startswith("https://").all()


def test_frozen_row_predictions_keep_rows_removed_from_candidate_builder():
    import pandas as pd

    from scripts.run_cninfo_legal_name_recovery_20260929 import (
        _build_frozen_row_predictions,
    )

    firm_key = "SZSE:TEST:2014-01-23"
    audit = pd.DataFrame(
        [
            {
                "firm_key": firm_key,
                "year": 2020,
                "legal_name_current_in_report": "华北示例科技股份有限公司",
                "legal_name_at_year_end": "华北示例科技股份有限公司",
                "company_name_change_flag": "UNKNOWN",
            },
            {
                "firm_key": firm_key,
                "year": 2021,
                "legal_name_current_in_report": "华北示例科技股份有限公司",
                "legal_name_at_year_end": "华北示例科技股份有限公司",
                "company_name_change_flag": "UNKNOWN",
            },
        ]
    )
    candidate_rows = pd.DataFrame(
        [
            {
                "firm_key": firm_key,
                "year": 2020,
                "parser_change_flag": "UNKNOWN",
                "parser_legal_name_at_year_end": "华北示例科技股份有限公司",
                "candidate_reason": "adjacent_year_name_difference",
            }
        ]
    )
    frozen_gt = pd.DataFrame(
        [{"firm_key": firm_key, "year": "2020"}, {"firm_key": firm_key, "year": "2021"}]
    )
    predictions = _build_frozen_row_predictions(audit, candidate_rows, frozen_gt)
    assert set(predictions.year.astype(str)) == {"2020", "2021"}
    removed_candidate = predictions.loc[predictions.year.astype(str).eq("2021")].iloc[0]
    assert removed_candidate.parser_legal_name_at_year_end == "华北示例科技股份有限公司"
    assert removed_candidate.candidate_reason == ""


def test_fixed_evaluation_scope_prevents_unreviewed_adjacent_rows_from_creating_candidates():
    import pandas as pd

    from scripts.run_cninfo_legal_name_recovery_20260929 import (
        _build_pilot_change_candidate_rows,
    )

    firm_key = "SSE:TEST:2010-01-01"
    audit = pd.DataFrame(
        [
            {
                "firm_key": firm_key,
                "year": 2020,
                "company_name_change_flag": "UNKNOWN",
                "legal_name_current_in_report": "示例能源股份有限公司",
                "legal_name_at_year_end": "示例能源股份有限公司",
            },
            {
                "firm_key": firm_key,
                "year": 2021,
                "company_name_change_flag": "UNKNOWN",
                "legal_name_current_in_report": "示例能源股份有限公司",
                "legal_name_at_year_end": "示例能源股份有限公司",
            },
            {
                "firm_key": firm_key,
                "year": 2022,
                "company_name_change_flag": "UNKNOWN",
                "legal_name_current_in_report": "分公司释义示例能源股份有限公司",
                "legal_name_at_year_end": "分公司释义示例能源股份有限公司",
            },
        ]
    )
    candidates = _build_pilot_change_candidate_rows(
        audit,
        pd.DataFrame(columns=["firm_key", "year", "source_url"]),
        {(firm_key, 2020), (firm_key, 2021)},
    )
    assert candidates.empty


def test_v2_gate_requires_complete_independent_event_and_row_reviews():
    import pandas as pd

    sample = pd.DataFrame({"firm_key": [f"F{i}" for i in range(92)]})
    target_rows = [{"firm_key": f"F{i}", "year": 2020 + j} for i in range(92) for j in range(5)]
    target_rows.append({"firm_key": "F0", "year": 2025})
    targets = pd.DataFrame(target_rows)
    audit = pd.DataFrame(
        {
            "firm_key": targets.firm_key,
            "year": targets.year,
            "legal_name_current_in_report": "甲股份有限公司",
            "legal_name_at_year_end": "甲股份有限公司",
            "audited_legal_name": "甲股份有限公司",
            "human_audit_status": "PASS",
            "abbreviation_false_positive": "0",
        }
    )
    candidates = pd.DataFrame([{"firm_key": "SSE:600001:2000-01-01", "year": 2024}])
    events = pd.DataFrame(
        [
            {
                "event_id": "EVT-1",
                "firm_key": "SSE:600001:2000-01-01",
                "parser_previous_legal_name": "甲股份有限公司",
                "parser_new_legal_name": "乙股份有限公司",
                "parser_effective_date": "2024-06-10",
                "parser_date_precision": "exact_date",
            }
        ]
    )
    rows = pd.DataFrame(
        [
            {
                "firm_key": "SSE:600001:2000-01-01",
                "year": 2024,
                "candidate_reason": "parser_old_new_name_pair",
                "proposed_event_id": "EVT-1",
                "parser_change_flag": "YES",
                "parser_legal_name_at_year_end": "乙股份有限公司",
                "parser_previous_name": "甲股份有限公司",
                "parser_new_name": "乙股份有限公司",
            }
        ]
    )
    event_gt = pd.DataFrame(
        [
            {
                "event_id": "EVT-1",
                "parser_previous_legal_name": "甲股份有限公司",
                "parser_new_legal_name": "乙股份有限公司",
                "parser_effective_date": "2024-06-10",
                "parser_date_precision": "exact_date",
                "review_previous_legal_name": "甲股份有限公司",
                "review_new_legal_name": "乙股份有限公司",
                "review_effective_date": "2024-06-10",
                "review_date_precision": "exact_date",
                "review_event_is_real": "YES",
                "review_status": "PASS",
                "reviewer_evidence_url": "https://notice.test/event.pdf",
                "reviewer_evidence_title": "名称变更公告",
                "reviewer_evidence_excerpt": "法人全称由甲变更为乙",
            }
        ]
    )
    row_gt = pd.DataFrame(
        [
            {
                "firm_key": "SSE:600001:2000-01-01",
                "year": 2024,
                "candidate_reason": "parser_old_new_name_pair",
                "proposed_event_id": "EVT-1",
                "parser_change_flag": "YES",
                "parser_legal_name_at_year_end": "乙股份有限公司",
                "review_event_id": "EVT-1",
                "parser_previous_name": "甲股份有限公司",
                "parser_new_name": "乙股份有限公司",
                "review_is_change_related": "YES",
                "review_change_flag": "YES",
                "review_previous_name": "甲股份有限公司",
                "review_new_name": "乙股份有限公司",
                "review_legal_name_at_year_end": "乙股份有限公司",
                "review_status": "PASS",
                "reviewer_evidence_url": "https://notice.test/row.pdf",
                "reviewer_evidence_title": "年报",
                "reviewer_evidence_excerpt": "公司的中文名称 乙股份有限公司",
                "exclusion_reason": "",
            }
        ]
    )
    summary = _build_v2_strict_pilot_summary(
        sample, targets, audit, candidates, events, rows, event_gt, row_gt
    )
    assert summary["schema"] == "cnipa_strict_pilot_gate_v2"
    assert summary["pilot_gate_pass"] is True
    assert not _strict_pilot_authorized_v2(
        summary, sample, targets, audit, candidates, events, rows, event_gt, row_gt
    )
    assert not _strict_pilot_authorized_v2(
        summary,
        sample,
        targets,
        audit,
        candidates,
        events,
        rows,
        event_gt.assign(review_previous_legal_name="changed"),
        row_gt,
    )
    assert not _strict_pilot_authorized_v2(
        {**summary, "schema": "cnipa_strict_pilot_gate_v1"},
        sample,
        targets,
        audit,
        candidates,
        events,
        rows,
        event_gt,
        row_gt,
    )
    assert not _strict_pilot_authorized_v2(
        summary, sample, targets, audit, candidates, events, rows.iloc[0:0], event_gt, row_gt
    )
    for key in (
        "sample_fingerprint",
        "target_fingerprint",
        "source_evidence_fingerprint",
        "change_candidate_row_fingerprint",
        "change_event_roster_fingerprint",
        "change_row_review_fingerprint",
        "event_ground_truth_fingerprint",
        "row_ground_truth_fingerprint",
    ):
        assert not _strict_pilot_authorized_v2(
            {**summary, key: "0" * 64},
            sample,
            targets,
            audit,
            candidates,
            events,
            rows,
            event_gt,
            row_gt,
        )
    assert not _strict_pilot_authorized_v2(
        {"status": "COMPLETE", "pilot_gate_pass": True, "schema": "legacy"},
        sample,
        targets,
        audit,
        candidates,
        events,
        rows,
        event_gt,
        row_gt,
    )


def test_h2_announcement_confirms_change_pair_and_exact_registration_date():
    notice = (
        "关于变更公司名称暨完成工商变更登记的公告。特别提示：公司名称由"
        "“山东美晨生态环境股份有限公司”变更为“山东美晨科技股份有限公司”。"
        "2024年8月13日，公司完成了工商变更登记手续，并领取换发的营业执照。"
    )

    evidence = extract_company_name_change_announcement(
        notice,
        expected_year=2024,
        previous_legal_name="山东美晨生态环境股份有限公司",
        new_legal_name="山东美晨科技股份有限公司",
    )

    assert evidence["company_name_change_flag"] == "YES"
    assert evidence["evidence_status"] == "CONFIRMED_NAME_CHANGE"


def test_ground_truth_templates_are_pending_blank_and_protected(tmp_path):
    import pandas as pd
    import pytest

    from scripts.run_cninfo_legal_name_recovery_20260929 import (
        _prepare_pilot_ground_truth_review,
    )

    events = pd.DataFrame([{"event_id": "EVT-1", "firm_key": "SSE:1:2000-01-01"}])
    rows = pd.DataFrame([{"firm_key": "SSE:1:2000-01-01", "year": 2024}])
    _prepare_pilot_ground_truth_review(tmp_path, events, rows)
    event_gt = pd.read_csv(
        tmp_path / "pilot_change_event_ground_truth.csv", dtype=str, keep_default_na=False
    )
    row_gt = pd.read_csv(
        tmp_path / "pilot_change_row_ground_truth.csv", dtype=str, keep_default_na=False
    )
    assert event_gt.loc[0, "review_status"] == "PENDING"
    assert event_gt.loc[0, "review_previous_legal_name"] == ""
    assert row_gt.loc[0, "review_status"] == "PENDING"
    assert row_gt.loc[0, "review_change_flag"] == ""
    with pytest.raises(FileExistsError, match="GROUND_TRUTH_RESET_REQUIRES_EXPLICIT_FLAG"):
        _prepare_pilot_ground_truth_review(tmp_path, events, rows)
    _prepare_pilot_ground_truth_review(tmp_path, events, rows, force_reset=True)
    event_gt = pd.read_csv(
        tmp_path / "pilot_change_event_ground_truth.csv", dtype=str, keep_default_na=False
    )
    assert event_gt.loc[0, "review_status"] == "PENDING"


def test_parser_predictions_contain_no_automatic_review_fields():
    import pandas as pd

    from scripts.run_cninfo_legal_name_recovery_20260929 import (
        _build_pilot_change_artifacts,
    )

    audit = pd.DataFrame([_event_row()])
    audit["legal_name_at_year_end"] = "乙股份有限公司"
    audit["legal_name_current_in_report"] = "乙股份有限公司"
    audit["legal_name_previous"] = "甲股份有限公司"
    audit["legal_name_new"] = "乙股份有限公司"
    audit["audited_legal_name"] = "乙股份有限公司"
    audit["company_name_change_flag"] = "YES"
    audit["change_effective_date"] = "2024-06-10"
    audit["date_precision"] = "exact_date"
    audit["change_evidence_url"] = "https://official.test/notice.pdf"
    audit["change_evidence_tier"] = "H2"
    statuses = pd.DataFrame(
        [
            {
                "firm_key": audit.loc[0, "firm_key"],
                "year": 2024,
                "source_url": "https://official.test/report.pdf",
            }
        ]
    )
    candidates, events, rows = _build_pilot_change_artifacts(audit, statuses)
    assert not any(str(column).startswith(("manual_", "review_")) for column in events.columns)
    assert not any(str(column).startswith(("manual_", "review_")) for column in rows.columns)
    assert not any(
        str(column).startswith(("manual_", "review_", "audited_", "human_"))
        or column == "abbreviation_false_positive"
        for column in candidates.columns
    )


def test_v2_metrics_compare_predictions_only_to_separate_ground_truth():
    import pandas as pd

    from scripts.run_cninfo_legal_name_recovery_20260929 import (
        _build_v2_strict_pilot_summary,
    )

    sample = pd.DataFrame({"firm_key": [f"F{i}" for i in range(92)]})
    target_rows = [{"firm_key": f"F{i}", "year": 2020 + j} for i in range(92) for j in range(5)]
    target_rows.append({"firm_key": "F0", "year": 2025})
    targets = pd.DataFrame(target_rows)
    audit = pd.DataFrame(
        {
            "firm_key": targets.firm_key,
            "year": targets.year,
            "legal_name_current_in_report": "甲股份有限公司",
            "legal_name_at_year_end": "甲股份有限公司",
            "audited_legal_name": "甲股份有限公司",
            "human_audit_status": "PASS",
            "abbreviation_false_positive": "0",
        }
    )
    candidates = pd.DataFrame([{"firm_key": "SSE:1:2000-01-01", "year": 2024}])
    events = pd.DataFrame(
        [
            {
                "event_id": "EVT-1",
                "firm_key": "SSE:1:2000-01-01",
                "parser_previous_legal_name": "甲股份有限公司",
                "parser_new_legal_name": "乙股份有限公司",
                "parser_effective_date": "2024-06-10",
                "parser_date_precision": "exact_date",
            }
        ]
    )
    rows = pd.DataFrame(
        [
            {
                "firm_key": "SSE:1:2000-01-01",
                "year": 2024,
                "candidate_reason": "parser_old_new_name_pair",
                "proposed_event_id": "EVT-1",
                "parser_change_flag": "YES",
                "parser_legal_name_at_year_end": "乙股份有限公司",
                "parser_previous_name": "甲股份有限公司",
                "parser_new_name": "乙股份有限公司",
            }
        ]
    )
    rows.loc[len(rows)] = {
        "firm_key": "SSE:1:2000-01-01",
        "year": 2023,
        "candidate_reason": "",
        "proposed_event_id": "",
        "parser_change_flag": "NO",
        "parser_legal_name_at_year_end": "甲股份有限公司",
        "parser_previous_name": "",
        "parser_new_name": "",
    }
    event_gt = pd.DataFrame(
        [
            {
                "event_id": "EVT-1",
                "review_previous_legal_name": "甲股份有限公司",
                "parser_previous_legal_name": "甲股份有限公司",
                "parser_new_legal_name": "乙股份有限公司",
                "parser_effective_date": "2024-06-10",
                "parser_date_precision": "exact_date",
                "review_new_legal_name": "乙股份有限公司",
                "review_effective_date": "2024-06-10",
                "review_date_precision": "exact_date",
                "review_event_is_real": "YES",
                "review_status": "PASS",
                "reviewer_evidence_url": "https://official.test/e.pdf",
                "reviewer_evidence_title": "公告",
                "reviewer_evidence_excerpt": "法人名称变更",
            }
        ]
    )
    row_gt = pd.DataFrame(
        [
            {
                "firm_key": "SSE:1:2000-01-01",
                "year": "2024",
                "candidate_reason": "stale frozen parser snapshot",
                "proposed_event_id": "stale-event-id",
                "parser_change_flag": "UNKNOWN",
                "parser_legal_name_at_year_end": "stale parser name",
                "parser_previous_name": "stale old name",
                "parser_new_name": "stale new name",
                "review_event_id": "EVT-1",
                "review_is_change_related": "YES",
                "review_change_flag": "YES",
                "review_legal_name_at_year_end": "乙股份有限公司",
                "review_previous_name": "甲股份有限公司",
                "review_new_name": "乙股份有限公司",
                "exclusion_reason": "",
                "review_status": "PASS",
                "reviewer_evidence_url": "https://official.test/r.pdf",
                "reviewer_evidence_title": "年报",
                "reviewer_evidence_excerpt": "公司中文名称",
            },
            {
                "firm_key": "SSE:1:2000-01-01",
                "year": "2023",
                "candidate_reason": "stale frozen parser snapshot",
                "proposed_event_id": "",
                "parser_change_flag": "UNKNOWN",
                "parser_legal_name_at_year_end": "stale parser name",
                "parser_previous_name": "",
                "parser_new_name": "",
                "review_event_id": "",
                "review_is_change_related": "NO",
                "review_change_flag": "NO",
                "review_legal_name_at_year_end": "甲股份有限公司",
                "review_previous_name": "",
                "review_new_name": "",
                "exclusion_reason": "NOT_A_LEGAL_NAME_CHANGE_EVENT:stable name",
                "review_status": "PASS",
                "reviewer_evidence_url": "https://official.test/r-2023.pdf",
                "reviewer_evidence_title": "年报",
                "reviewer_evidence_excerpt": "公司中文名称",
            },
        ]
    )
    summary = _build_v2_strict_pilot_summary(
        sample, targets, audit, candidates, events, rows, event_gt, row_gt
    )
    assert summary["pilot_gate_pass"] is True
    assert summary["row_evaluation_denominator"] == 2
    assert summary["metrics"]["firm_year_accuracy_denominator"] == 2
    wrong = event_gt.assign(review_previous_legal_name="错误旧名称")
    summary = _build_v2_strict_pilot_summary(
        sample, targets, audit, candidates, events, rows, wrong, row_gt
    )
    assert summary["metrics"]["event_old_name_accuracy"] == 0
    assert summary["pilot_gate_pass"] is False
    wrong_new = event_gt.assign(review_new_legal_name="错误新名称")
    wrong_date = event_gt.assign(review_effective_date="2024-06-11")
    assert (
        _build_v2_strict_pilot_summary(
            sample, targets, audit, candidates, events, rows, wrong_new, row_gt
        )["metrics"]["event_new_name_accuracy"]
        == 0
    )
    assert (
        _build_v2_strict_pilot_summary(
            sample, targets, audit, candidates, events, rows, wrong_date, row_gt
        )["metrics"]["event_effective_date_accuracy"]
        == 0
    )
    wrong_year_end = row_gt.assign(review_legal_name_at_year_end="错误年末名称")
    wrong_flag = row_gt.assign(review_change_flag="NO")
    assert (
        _build_v2_strict_pilot_summary(
            sample, targets, audit, candidates, events, rows, event_gt, wrong_year_end
        )["metrics"]["firm_year_year_end_name_accuracy"]
        == 0
    )
    assert (
        _build_v2_strict_pilot_summary(
            sample, targets, audit, candidates, events, rows, event_gt, wrong_flag
        )["metrics"]["firm_year_change_flag_accuracy"]
        == 0.5
    )
    assert not _build_v2_strict_pilot_summary(
        sample,
        targets,
        audit,
        candidates,
        events,
        rows,
        event_gt.assign(review_status="PENDING"),
        row_gt,
    )["event_review_complete"]
    assert not _build_v2_strict_pilot_summary(
        sample,
        targets,
        audit,
        candidates,
        events,
        rows,
        event_gt.assign(reviewer_evidence_url=""),
        row_gt,
    )["event_review_complete"]
    assert not _build_v2_strict_pilot_summary(
        sample,
        targets,
        audit,
        candidates,
        events,
        rows,
        event_gt.assign(reviewer_evidence_excerpt=""),
        row_gt,
    )["event_review_complete"]
    non_event_without_reason = row_gt.assign(
        proposed_event_id="",
        review_event_id="",
        review_is_change_related="NO",
        exclusion_reason="",
    )
    non_event_prediction = rows.assign(proposed_event_id="")
    assert not _build_v2_strict_pilot_summary(
        sample,
        targets,
        audit,
        candidates,
        events,
        non_event_prediction,
        event_gt,
        non_event_without_reason,
    )["firm_year_review_complete"]


def test_v2_gate_rejects_pending_or_evidenceless_ground_truth():
    import pandas as pd

    from scripts.run_cninfo_legal_name_recovery_20260929 import (
        _review_is_complete,
    )

    required = ["review_status", "reviewer_evidence_url", "reviewer_evidence_excerpt"]
    assert not _review_is_complete(pd.DataFrame(), required)
    pending = pd.DataFrame(
        [
            {
                "review_status": "PENDING",
                "reviewer_evidence_url": "https://official.test/a.pdf",
                "reviewer_evidence_excerpt": "证据摘录",
            }
        ]
    )
    assert not _review_is_complete(pending, required)
    missing_url = pending.assign(review_status="PASS", reviewer_evidence_url="")
    assert not _review_is_complete(missing_url, required)
    missing_excerpt = pending.assign(review_status="PASS", reviewer_evidence_excerpt="")
    assert not _review_is_complete(missing_excerpt, required)
    unresolved = pending.assign(review_status="UNRESOLVED")
    assert not _review_is_complete(unresolved, required)


def test_finalizing_predictions_never_overwrites_existing_ground_truth(tmp_path, monkeypatch):
    import pandas as pd

    import scripts.run_cninfo_legal_name_recovery_20260929 as recovery

    audit = pd.DataFrame([_event_row()])
    audit["legal_name_current_in_report"] = "乙股份有限公司"
    audit["legal_name_at_year_end"] = "乙股份有限公司"
    audit["audited_legal_name"] = "乙股份有限公司"
    audit["human_audit_status"] = "PASS"
    audit["abbreviation_false_positive"] = "0"
    statuses = pd.DataFrame(
        [
            {
                "firm_key": audit.loc[0, "firm_key"],
                "year": 2024,
                "source_url": "https://official.test/report.pdf",
            }
        ]
    )
    _, events, predictions = recovery._build_pilot_change_artifacts(audit, statuses)
    recovery._prepare_pilot_ground_truth_review(tmp_path, events, predictions)
    event_path = tmp_path / "pilot_change_event_ground_truth.csv"
    row_path = tmp_path / "pilot_change_row_ground_truth.csv"
    event_gt = pd.read_csv(event_path, dtype=str, keep_default_na=False)
    row_gt = pd.read_csv(row_path, dtype=str, keep_default_na=False)
    event_gt.loc[0, "reviewer_evidence_title"] = "manual event sentinel"
    row_gt.loc[0, "reviewer_evidence_title"] = "manual row sentinel"
    event_gt.to_csv(event_path, index=False, encoding="utf-8-sig")
    row_gt.to_csv(row_path, index=False, encoding="utf-8-sig")
    sample = pd.DataFrame({"firm_key": [f"F{i}" for i in range(92)]})
    targets = pd.DataFrame(
        [{"firm_key": f"F{i}", "year": year} for i in range(92) for year in range(2020, 2025)]
        + [{"firm_key": "F0", "year": 2025}]
    )
    sample.to_csv(tmp_path / "pilot_sample.csv", index=False)
    targets.to_csv(tmp_path / "pilot_firm_year_targets.csv", index=False)
    audit.to_csv(tmp_path / "pilot_context_audit.csv", index=False)
    statuses.to_csv(tmp_path / "pilot_status.csv", index=False)
    evidence_state = pd.DataFrame(
        [
            {
                "firm_key": str(row_gt.loc[0, "firm_key"]),
                "year": int(row_gt.loc[0, "year"]),
                "historical_change_occurrence": "UNRESOLVED",
                "historical_event_id": "",
                "review_expected_parser_flag": "YES",
                "evidence_basis": "synthetic test fixture",
                "evidence_tier": "H1",
                "reviewer_evidence_url": "https://official.test/evidence.pdf",
                "reviewer_evidence_title": "synthetic evidence",
                "reviewer_evidence_excerpt": "synthetic excerpt",
                "explicit_no_change_disclosure": "NO",
                "verified_change_event_in_target_year": "YES",
                "verified_change_event_outside_target_year": "NO",
                "review_status": "PASS",
                "review_notes": "synthetic validator fixture",
            }
        ]
    )
    evidence_state.to_csv(
        tmp_path / "pilot_change_evidence_state_ground_truth.csv",
        index=False,
        encoding="utf-8-sig",
    )
    monkeypatch.setattr(recovery, "OUTPUT", tmp_path)
    recovery._finalize_pilot_change_events()
    event_after = pd.read_csv(event_path, dtype=str, keep_default_na=False)
    row_after = pd.read_csv(row_path, dtype=str, keep_default_na=False)
    assert event_after.loc[0, "reviewer_evidence_title"] == "manual event sentinel"
    assert row_after.loc[0, "reviewer_evidence_title"] == "manual row sentinel"


def test_pilot_pass_flag_alone_cannot_authorize_full(tmp_path, monkeypatch):
    import pandas as pd
    import pytest

    import scripts.run_cninfo_legal_name_recovery_20260929 as recovery

    targets = pd.DataFrame(
        [{"firm_key": f"F{i}", "year": year} for i in range(92) for year in range(2020, 2025)]
        + [{"firm_key": "F0", "year": 2025}]
    )
    monkeypatch.setattr(recovery, "OUTPUT", tmp_path)
    monkeypatch.setattr(recovery, "_firm_year_targets", lambda: (targets, targets))
    monkeypatch.setattr(recovery, "_source_records", lambda: [])
    pd.DataFrame(
        [{"schema": "cnipa_strict_pilot_gate_v1", "status": "STRICT_PILOT_GATE_PASS"}]
    ).to_json(tmp_path / "pilot_strict_gate_v2_summary.json", orient="records")
    args = type("Args", (), {"stage": "full", "pilot_pass": True})()
    with pytest.raises(ValueError, match="CANONICAL_STRICT_PILOT_GATE_INPUTS_MISSING"):
        recovery._run(args)


def test_h2_announcement_rejects_a_notice_without_both_expected_names():
    evidence = extract_company_name_change_announcement(
        "公司于2024年8月13日完成工商变更登记。",
        expected_year=2024,
        previous_legal_name="甲公司股份有限公司",
        new_legal_name="乙公司股份有限公司",
    )

    assert evidence["evidence_status"] == "TEMPORAL_UNRESOLVED"
    assert evidence["failure_reason"] == "notice_does_not_confirm_expected_name_pair"


def test_h2_announcement_rejects_two_names_not_linked_as_the_expected_pair():
    evidence = extract_company_name_change_announcement(
        "公司名称由甲股份有限公司变更为丙股份有限公司；乙股份有限公司为本公告关联方。"
        "本公司完成名称变更登记。",
        expected_year=2025,
        previous_legal_name="甲股份有限公司",
        new_legal_name="乙股份有限公司",
        announcement_date="2025-05-01",
    )

    assert evidence["evidence_status"] == "TEMPORAL_UNRESOLVED"
    assert evidence["failure_reason"] == "notice_does_not_confirm_expected_name_pair"


def test_h2_completed_name_change_without_effective_day_uses_year_precision():
    notice = (
        "关于完成公司名称变更的公告。公司名称由山东美晨科技股份有限公司"
        "变更为山东美晨科技集团股份有限公司。公告日期2025年11月24日。"
    )

    evidence = extract_company_name_change_announcement(
        notice,
        expected_year=2025,
        previous_legal_name="山东美晨科技股份有限公司",
        new_legal_name="山东美晨科技集团股份有限公司",
        announcement_date="2025-11-24",
    )

    assert evidence["company_name_change_flag"] == "YES"
    assert evidence["evidence_status"] == "CONFIRMED_NAME_CHANGE"
    assert evidence["change_effective_date"] == ""
    assert evidence["date_precision"] == "year"
    assert evidence["temporal_match_uncertain"] == 1


def test_h2_short_text_pdf_is_audited_and_next_notice_is_checked(tmp_path, monkeypatch):
    import pandas as pd

    import scripts.run_cninfo_legal_name_recovery_20260929 as recovery_script

    monkeypatch.setattr(recovery_script, "OUTPUT", tmp_path)

    old_name = "山东美晨生态环境股份有限公司"
    new_name = "山东美晨科技股份有限公司"

    class Client:
        def list_company_name_change_announcements(self, stock_code, start, end):
            assert (stock_code, start, end) == ("300237", "2022-01-01", "2023-03-31")
            return [
                {"title": "第一份公告", "source_url": "https://example.invalid/short.pdf"},
                {"title": "名称变更公告", "source_url": "https://example.invalid/good.pdf"},
            ]

        def extract_pdf_text_with_metadata(self, url):
            if url.endswith("short.pdf"):
                raise ValueError("pdftotext produced empty or implausibly short text")
            return (
                f"公司名称由{old_name}变更为{new_name}，2022年8月13日完成工商变更登记。",
                {"pdf_sha256": "a" * 64, "pdf_bytes": 2048, "text_chars": 100},
            )

    firm_key = "SZSE:300237:2010-01-01"
    current = {
        "firm_key": firm_key,
        "stock_code": "300237",
        "legal_name_at_year_end": new_name,
        "legal_name_current_in_report": new_name,
        "company_name_change_flag": "UNKNOWN",
    }
    rows = {
        (firm_key, 2021): {"legal_name_at_year_end": old_name},
        (firm_key, 2022): current,
    }

    audit, source_blocked = _resolve_cross_year_name_changes(
        rows,
        pd.DataFrame([{"firm_key": firm_key, "stock_code_current": "300237"}]),
        Client(),
        "full",
    )

    assert source_blocked is False
    assert audit[0]["status"] == "RESOLVED_H2"
    assert audit[0]["notice_extraction_failures"] == [
        "第一份公告:ValueError:pdftotext produced empty or implausibly short text"
    ]
    assert current["company_name_change_flag"] == "YES"
    assert current["legal_name_previous"] == old_name


def test_v3_evidence_state_semantics_and_old_authorization(monkeypatch, tmp_path):
    import pandas as pd

    from scripts.run_cninfo_legal_name_recovery_20260929 import (
        _expected_parser_flag_from_review,
        _score_evidence_state_predictions,
        _validate_evidence_state_ground_truth,
        _validate_historical_occurrence_alignment,
    )

    assert _expected_parser_flag_from_review(
        explicit_change_in_year=False,
        explicit_no_change=False,
        verified_event_year=None,
        chronology_sufficient=False,
    ) == "UNKNOWN"
    assert _expected_parser_flag_from_review(
        explicit_change_in_year=True,
        explicit_no_change=False,
        verified_event_year=None,
        chronology_sufficient=False,
    ) == "YES"
    assert _expected_parser_flag_from_review(
        explicit_change_in_year=False,
        explicit_no_change=False,
        verified_event_year=2024,
        chronology_sufficient=True,
        target_year=2024,
    ) == "YES"
    assert _expected_parser_flag_from_review(
        explicit_change_in_year=False,
        explicit_no_change=False,
        verified_event_year=2010,
        chronology_sufficient=True,
        target_year=2020,
    ) == "NO"
    assert _expected_parser_flag_from_review(
        explicit_change_in_year=False,
        explicit_no_change=False,
        verified_event_year=2010,
        chronology_sufficient=False,
        target_year=2020,
    ) == "UNKNOWN"
    assert _expected_parser_flag_from_review(
        explicit_change_in_year=False,
        explicit_no_change=True,
        verified_event_year=None,
        chronology_sufficient=False,
        target_year=2020,
    ) == "NO"

    row = {
        "firm_key": "SZSE:300365:2014-01-23",
        "year": 2020,
        "historical_change_occurrence": "NO",
        "historical_event_id": "",
        "review_expected_parser_flag": "UNKNOWN",
        "evidence_basis": "年末法人名称可确认；未见足够事件时间证据",
        "evidence_tier": "H1",
        "reviewer_evidence_url": "https://example.invalid/report.pdf",
        "reviewer_evidence_title": "年度报告",
        "reviewer_evidence_excerpt": "公司的中文名称为甲公司",
        "explicit_no_change_disclosure": "NO",
        "verified_change_event_in_target_year": "NO",
        "verified_change_event_outside_target_year": "NO",
        "review_status": "PASS",
        "review_notes": "历史事实与证据状态分离",
    }
    validation = _validate_evidence_state_ground_truth(pd.DataFrame([row]))
    assert validation["valid"] is True
    assert validation["unresolved_review_count"] == 0
    assert validation["fingerprint"]
    assert _validate_historical_occurrence_alignment(
        pd.DataFrame([{
            "firm_key": row["firm_key"], "year": 2020,
            "review_change_flag": "NO", "review_event_id": "",
        }]),
        pd.DataFrame([row]),
    )
    predicted = pd.DataFrame(
        [{"firm_key": row["firm_key"], "year": 2020, "parser_change_flag": "UNKNOWN"}]
    )
    expected = pd.DataFrame(
        [{
            "firm_key": row["firm_key"],
            "year": 2020,
            "review_expected_parser_flag": "UNKNOWN",
        }]
    )
    assert _score_evidence_state_predictions(predicted, expected)["accuracy"] == 1.0
    assert _score_evidence_state_predictions(
        predicted.assign(parser_change_flag="NO"), expected
    )["accuracy"] == 0.0
    explicit_no = expected.assign(review_expected_parser_flag="NO")
    assert _score_evidence_state_predictions(
        predicted, explicit_no
    )["accuracy"] == 0.0
    assert _score_evidence_state_predictions(
        predicted.assign(parser_change_flag="NO"), explicit_no
    )["accuracy"] == 1.0
    assert _expected_parser_flag_from_review(
        explicit_change_in_year=True,
        explicit_no_change=False,
        verified_event_year=2024,
        chronology_sufficient=True,
        target_year=2024,
        issuer_level_event=False,
    ) == "UNKNOWN"
    pending = pd.DataFrame([row | {"review_status": "PENDING"}])
    assert _validate_evidence_state_ground_truth(pending)["valid"] is False


def test_v3_gate_uses_14_evidence_rows_not_historical_no(monkeypatch):
    import copy

    import pandas as pd

    import scripts.run_cninfo_legal_name_recovery_20260929 as recovery

    keys = [(f"SZSE:{index:06d}:2000-01-01", 2020) for index in range(14)]
    truth = pd.DataFrame(
        [
            {
                "firm_key": firm,
                "year": year,
                "historical_change_occurrence": "NO" if index == 0 else "YES",
                "historical_event_id": "" if index == 0 else f"EVT-{index}",
                "review_expected_parser_flag": "UNKNOWN" if index == 0 else "YES",
                "evidence_basis": "independent review basis",
                "evidence_tier": "H1",
                "reviewer_evidence_url": "https://example.invalid/report.pdf",
                "reviewer_evidence_title": "annual report",
                "reviewer_evidence_excerpt": "issuer-level evidence excerpt",
                "explicit_no_change_disclosure": "NO",
                "verified_change_event_in_target_year": "NO" if index == 0 else "YES",
                "verified_change_event_outside_target_year": "NO",
                "review_status": "PASS",
                "review_notes": "reviewed independently",
            }
            for index, (firm, year) in enumerate(keys)
        ]
    )
    rows = pd.DataFrame(
        [
            {"firm_key": firm, "year": year, "parser_change_flag": "UNKNOWN" if i == 0 else "YES"}
            for i, (firm, year) in enumerate(keys)
        ]
    )
    row_gt = pd.DataFrame(
        [
            {
                "firm_key": firm,
                "year": year,
                "review_change_flag": "NO" if index == 0 else "YES",
                "review_event_id": "" if index == 0 else f"EVT-{index}",
            }
            for index, (firm, year) in enumerate(keys)
        ]
    )
    base = {
        "metrics": {
            "firm_year_change_flag_accuracy": 13 / 14,
            "event_old_name_accuracy": 1.0,
            "event_new_name_accuracy": 1.0,
            "event_effective_date_accuracy": 1.0,
            "event_date_precision_accuracy": 1.0,
            "firm_year_year_end_name_accuracy": 1.0,
            "unresolved_candidate_count": 0,
            "unresolved_event_count": 0,
        },
        "event_review_complete": True,
        "firm_year_review_complete": True,
        "row_evaluation_denominator": 14,
    }
    monkeypatch.setattr(
        recovery, "_build_v2_strict_pilot_summary", lambda *args: copy.deepcopy(base)
    )
    summary = recovery._build_v3_strict_pilot_summary(
        pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), pd.DataFrame(),
        rows, pd.DataFrame(), row_gt, truth,
    )
    assert summary["row_evaluation_denominator"] == 14
    assert summary["historical_change_occurrence_accuracy"] == 13 / 14
    assert summary["parser_evidence_state_accuracy"] == 1.0
    assert summary["pilot_gate_pass"] is True

    overclaimed = rows.assign(parser_change_flag="NO")
    failing = recovery._build_v3_strict_pilot_summary(
        pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), pd.DataFrame(),
        overclaimed, pd.DataFrame(), row_gt, truth,
    )
    assert failing["parser_evidence_state_accuracy"] < 1.0
    assert failing["pilot_gate_pass"] is False

    pending = truth.assign(review_status="PENDING")
    blocked = recovery._build_v3_strict_pilot_summary(
        pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), pd.DataFrame(),
        rows, pd.DataFrame(), row_gt, pending,
    )
    assert blocked["evidence_state_ground_truth_review_complete"] is False
    assert blocked["pilot_gate_pass"] is False

    missing_row = truth.iloc[:-1].copy()
    missing_key = recovery._build_v3_strict_pilot_summary(
        pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), pd.DataFrame(),
        rows.iloc[:-1], pd.DataFrame(), row_gt.iloc[:-1], missing_row,
    )
    assert missing_key["parser_evidence_state_denominator"] == 13
    assert missing_key["pilot_gate_pass"] is False


def test_v3_evidence_fingerprint_mismatch_blocks_authorization(monkeypatch):
    import pandas as pd

    import scripts.run_cninfo_legal_name_recovery_20260929 as recovery

    ground_truth = pd.DataFrame([{"firm_key": "SSE:600001:2000-01-01", "year": 2024}])
    summary = {
        "schema": "cnipa_strict_pilot_gate_v3",
        "pilot_gate_pass": True,
        "status": "STRICT_PILOT_GATE_PASS",
        "parser_evidence_state_accuracy": 1.0,
        "parser_evidence_state_denominator": 14,
        "evidence_state_ground_truth_fingerprint": recovery._frame_fingerprint(ground_truth),
    }
    monkeypatch.setattr(recovery, "_build_v3_strict_pilot_summary", lambda *args: summary)
    assert recovery._strict_pilot_authorized_v3(
        summary, pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), pd.DataFrame(),
        pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), ground_truth,
    )
    changed = ground_truth.assign(year=2025)
    assert not recovery._strict_pilot_authorized_v3(
        summary, pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), pd.DataFrame(),
        pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), changed,
    )
