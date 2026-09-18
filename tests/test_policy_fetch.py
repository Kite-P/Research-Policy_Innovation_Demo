
from src.fetch_policy_reports import fetch_manifest


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
