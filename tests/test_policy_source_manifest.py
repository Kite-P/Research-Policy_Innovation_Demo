import csv
from pathlib import Path

from src.policy_source_manifest import audit_downloads, read_manifest, validate_manifest

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


def test_policy_manifest_years_and_paths():
    rows = read_manifest(ROOT / "metadata/policy_source_manifest.csv")
    assert {int(row["report_year"]) for row in rows} == set(range(2019, 2026))
    assert all(not Path(row["raw_relpath"]).is_absolute() for row in rows)
    assert all(":" not in row["raw_relpath"] for row in rows)


def test_policy_manifest_download_audit():
    rows = read_manifest(ROOT / "metadata/policy_source_manifest.csv")
    assert audit_downloads(rows, ROOT) == []
