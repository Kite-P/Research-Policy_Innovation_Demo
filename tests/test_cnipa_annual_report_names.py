from __future__ import annotations

from scripts.run_cninfo_legal_name_recovery_20260927 import (
    _coverage_status,
    _load_status_cache,
    _process_one,
    _resolve_cross_year_name_changes,
)
from src.cnipa_annual_report_names import (
    extract_annual_report_legal_name_evidence,
    extract_company_name_change_announcement,
    select_legal_name_pilot,
    validate_firm_year_status_set,
    validate_pdf_payload,
)
from src.historical_province_sources import CNINFOAnnualReportClient


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
        "000096": [{
            "report_year": 2022,
            "title": "深圳市广聚能源股份有限公司2022年年度报告全文",
            "source_url": report_url,
            "announcement_id": "1216438315",
        }]
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


def test_extracts_wrapped_old_new_names_and_event_date_from_name_change_section():
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

    completed = {"firm_key": "firm-a", "year": 2020, "status": "COMPLETE_NO_CHANGE"}
    pending = {"firm_key": "firm-a", "year": 2021, "status": "PENDING"}
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
    assert _coverage_status({"status": "COMPLETE_NAME_CHANGE"}) == (
        "CONFIRMED_NAME_CHANGE"
    )
    assert _coverage_status({"status": "PENDING"}) == (
        "CONFIRMED_YEAR_END_NAME_ONLY"
    )
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


def test_pilot_sample_is_deterministic_unique_and_stratified():
    import pandas as pd

    rows = []
    for exchange in ("SSE", "SZSE"):
        for index in range(40):
            listing = "1995-01-01" if index < 20 else f"202{index % 5}-01-01"
            delisted = "2024-01-01" if 20 <= index < 30 else None
            rows.append({
                "firm_key": f"{exchange}:{index:06d}:{listing}",
                "exchange": exchange,
                "market_listing_date": listing,
                "delisting_date": delisted,
            })
    firms = pd.DataFrame(rows)
    first = select_legal_name_pilot(firms, seed="20260927")
    second = select_legal_name_pilot(firms, seed="20260927")
    assert first.firm_key.tolist() == second.firm_key.tolist()
    assert first.firm_key.is_unique
    assert len(first) >= 80
    assert {"SSE_current", "SZSE_current", "SSE_delisted", "SZSE_delisted",
            "recent_IPO", "long_listed"}.issubset(set(first.pilot_stratum))


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
    client = CNINFOAnnualReportClient(
        tmp_path, session=StubSession(), sleep=lambda _: None
    )
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
    assert evidence["company_name_change_flag"] == "NO"
    assert evidence["evidence_status"] == "CONFIRMED_NO_CHANGE"
    assert evidence["legal_name_at_year_end"] == "上海龙宇燃油股份有限公司"
    assert evidence["valid_to"] == "2023-01-05"


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

    assert evidence["company_name_change_flag"] == "NO"
    assert evidence["legal_name_current_in_report"] == "上海璞源化学材料集团股份有限公司"
    assert evidence["legal_name_at_year_end"] == "日播时尚集团股份有限公司"
    assert evidence["change_effective_date"] == "2026-03-10"


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
    assert evidence["change_effective_date"] == "2024-08-13"
    assert evidence["legal_name_at_year_end"] == "山东美晨科技股份有限公司"


def test_h2_announcement_rejects_a_notice_without_both_expected_names():
    evidence = extract_company_name_change_announcement(
        "公司于2024年8月13日完成工商变更登记。",
        expected_year=2024,
        previous_legal_name="甲公司股份有限公司",
        new_legal_name="乙公司股份有限公司",
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

    import scripts.run_cninfo_legal_name_recovery_20260927 as recovery_script

    monkeypatch.setattr(recovery_script, "OUTPUT", tmp_path)

    old_name = "山东美晨生态环境股份有限公司"
    new_name = "山东美晨科技股份有限公司"

    class Client:
        def list_company_name_change_announcements(self, stock_code, start, end):
            assert (stock_code, start, end) == (
                "300237", "2022-01-01", "2023-03-31"
            )
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
