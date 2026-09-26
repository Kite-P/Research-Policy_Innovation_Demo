from types import SimpleNamespace

from src.fetch_policy_reports import fetch_manifest, validate_report_content


def test_report_content_validator_rejects_short_verification_pages():
    payload = "<html><title>访问验证</title><body>请完成验证码验证后继续访问</body></html>".encode()
    assert validate_report_content(payload, "text/html", "北京市", 2025) == (
        "challenge_or_login_page"
    )


def test_report_content_validator_accepts_full_province_year_report():
    body = "北京市2025年政府工作报告。现在，我代表北京市人民政府向大会报告工作。"
    payload = f"<html><body><h1>{body}</h1><p>{'产业创新发展。' * 1600}</p></body></html>".encode()
    assert validate_report_content(payload, "text/html", "北京市", 2025) is None


def test_report_content_validator_rejects_wrong_province():
    body = "河北省2025年政府工作报告。现在，我代表河北省人民政府向大会报告工作。"
    payload = f"<html><body><h1>{body}</h1><p>{'产业创新发展。' * 1600}</p></body></html>".encode()
    assert validate_report_content(payload, "text/html", "天津市", 2025) == (
        "province_name_missing_from_body"
    )


def test_report_content_validator_accepts_province_and_report_identity_from_title():
    payload = f"<html><body><p>{'产业创新发展。' * 1600}</p></body></html>".encode()
    assert validate_report_content(
        payload, "text/html", "吉林省", 2019, "2019年吉林省政府工作报告（全文）"
    ) is None


def test_fetch_does_not_save_challenge_page_as_success(tmp_path, monkeypatch):
    manifest = tmp_path / "manifest.csv"
    manifest.write_text(
        "policy_id,province,province_key,report_year,title,issuer,publish_date,source_url,alternate_url,source_domain,source_type,retrieved_at_utc,http_status,final_url,content_type,raw_relpath,content_sha256,raw_bytes,retrieval_status,review_status,notes\n"
        "demo_2025,北京市,demo,2025,北京市政府工作报告,北京市人民政府,2025-01-01,https://example.gov.cn/report,,example.gov.cn,government_work_report,,,,data/raw/policy_reports/html/demo_2025.html,,,,manual_review,pending,\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "src.fetch_policy_reports.requests.get",
        lambda *args, **kwargs: SimpleNamespace(
            status_code=200,
            url="https://example.gov.cn/report",
            headers={"Content-Type": "text/html; charset=utf-8"},
            content="<html><title>访问验证</title><body>请完成验证码验证后继续访问</body></html>".encode(),
        ),
    )
    fetch_manifest(manifest, tmp_path, delay_seconds=0)
    assert "manual_review,challenge_or_login_page" in manifest.read_text(encoding="utf-8")
    assert not (tmp_path / "data/raw/policy_reports/html/demo_2025.html").exists()


def test_fetch_module_does_not_escape_project_root(tmp_path):
    manifest = tmp_path / "manifest.csv"
    manifest.write_text(
        "policy_id,province,province_key,report_year,title,issuer,publish_date,source_url,alternate_url,source_domain,source_type,retrieved_at_utc,http_status,final_url,content_type,raw_relpath,content_sha256,raw_bytes,retrieval_status,review_status,notes\n"
        "demo_2019,示例省,demo,2019,示例政府工作报告,示例省政府,2019-01-01,,,example.gov.cn,government_work_report,,,,data/raw/policy_reports/html/demo_2019.html,,,,manual_review,pending,\n",
        encoding="utf-8",
    )
    fetch_manifest(manifest, tmp_path, delay_seconds=0)
    text = manifest.read_text(encoding="utf-8")
    assert "manual_review" in text
    assert not (tmp_path.parent / "data").exists()
