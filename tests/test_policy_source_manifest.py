import csv
from pathlib import Path

from src.policy_source_manifest import (
    audit_downloads,
    complete_manifest_scope,
    read_manifest,
    validate_manifest,
)

ROOT = Path(__file__).parents[1]


def _scope():
    with (ROOT / "metadata/policy_region_scope.csv").open(
        encoding="utf-8-sig", newline=""
    ) as handle:
        return list(csv.DictReader(handle))


def test_policy_manifest_has_complete_unique_cells():
    rows = read_manifest(ROOT / "metadata/policy_source_manifest.csv")
    errors = validate_manifest(rows, _scope())
    assert not errors, errors


def test_policy_scope_is_exactly_31_mainland_provinces():
    scope = _scope()
    provinces = {row["province"] for row in scope}
    assert len(scope) == 31
    assert "香港特别行政区" not in provinces
    assert provinces == {
        "北京市", "天津市", "河北省", "山西省", "内蒙古自治区", "辽宁省", "吉林省",
        "黑龙江省", "上海市", "江苏省", "浙江省", "安徽省", "福建省", "江西省",
        "山东省", "河南省", "湖北省", "湖南省", "广东省", "广西壮族自治区", "海南省",
        "重庆市", "四川省", "贵州省", "云南省", "西藏自治区", "陕西省", "甘肃省",
        "青海省", "宁夏回族自治区", "新疆维吾尔自治区",
    }


def test_policy_manifest_years_and_paths():
    rows = read_manifest(ROOT / "metadata/policy_source_manifest.csv")
    assert {int(row["report_year"]) for row in rows} == set(range(2019, 2026))
    assert all(not Path(row["raw_relpath"]).is_absolute() for row in rows)
    assert all(":" not in row["raw_relpath"] for row in rows)


def test_policy_manifest_download_audit():
    rows = read_manifest(ROOT / "metadata/policy_source_manifest.csv")
    errors = audit_downloads(rows, ROOT)
    pending = [row["policy_id"] for row in rows if row["retrieval_status"] != "success"]
    assert len(errors) == len(pending)
    assert all(error.startswith("download not successful:") for error in errors)


def test_manifest_expansion_preserves_existing_rows_and_adds_target_cells():
    rows = read_manifest(ROOT / "metadata/policy_source_manifest.csv")
    legacy_keys = {"beijing", "shanghai", "guangdong", "jiangsu", "zhejiang", "sichuan", "hubei"}
    legacy_rows = [row for row in rows if row["province_key"] in legacy_keys]
    expanded = complete_manifest_scope(legacy_rows, _scope())
    assert len(expanded) == 217
    assert not validate_manifest(expanded, _scope())
    old_by_id = {row["policy_id"]: row for row in legacy_rows}
    expanded_by_id = {row["policy_id"]: row for row in expanded}
    assert all(expanded_by_id[key] == row for key, row in old_by_id.items())
    added = [row for row in expanded if row["policy_id"] not in old_by_id]
    assert len(added) == 168
    assert all(row["retrieval_status"] == "manual_review" for row in added)
