"""Validate the tracked policy source manifest without downloading report bodies."""

from __future__ import annotations

import csv
import hashlib
import re
from pathlib import Path

MANIFEST_COLUMNS = [
    "policy_id",
    "province",
    "province_key",
    "report_year",
    "title",
    "issuer",
    "publish_date",
    "source_url",
    "alternate_url",
    "source_domain",
    "source_type",
    "retrieved_at_utc",
    "http_status",
    "final_url",
    "content_type",
    "raw_relpath",
    "content_sha256",
    "raw_bytes",
    "retrieval_status",
    "review_status",
    "notes",
]

SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
ALLOWED_STATUS = {
    "success",
    "http_error",
    "blocked",
    "not_found",
    "parse_required",
    "manual_review",
}


def read_manifest(path: str | Path) -> list[dict[str, str]]:
    with Path(path).open("r", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    missing = set(MANIFEST_COLUMNS) - set(rows[0]) if rows else set(MANIFEST_COLUMNS)
    if missing:
        raise ValueError(f"manifest missing columns: {sorted(missing)}")
    return rows


def validate_manifest(rows: list[dict[str, str]], scope_rows: list[dict[str, str]]) -> list[str]:
    errors: list[str] = []
    expected_scope = {(row["province"], row["province_key"]) for row in scope_rows}
    expected_cells = {
        (province, year)
        for province, _ in expected_scope
        for year in range(2019, 2026)
    }
    seen_ids: set[str] = set()
    seen_cells: set[tuple[str, int]] = set()
    for row in rows:
        cell = (row["province"], int(row["report_year"]))
        if row["policy_id"] in seen_ids:
            errors.append(f"duplicate policy_id: {row['policy_id']}")
        if cell in seen_cells:
            errors.append(f"duplicate province-year: {cell}")
        seen_ids.add(row["policy_id"])
        seen_cells.add(cell)
        if (row["province"], row["province_key"]) not in expected_scope:
            errors.append(f"province outside scope: {cell}")
        if row["policy_id"] != f"{row['province_key']}_{row['report_year']}":
            errors.append(f"invalid policy_id: {row['policy_id']}")
        if row["source_type"] != "government_work_report":
            errors.append(f"invalid source_type: {row['policy_id']}")
        if row["retrieval_status"] not in ALLOWED_STATUS:
            errors.append(f"invalid retrieval_status: {row['policy_id']}")
        raw_path = Path(row["raw_relpath"])
        if raw_path.is_absolute() or ":" in row["raw_relpath"]:
            errors.append(f"absolute raw_relpath: {row['policy_id']}")
        if row["retrieval_status"] == "success":
            if not row["source_url"]:
                errors.append(f"success row missing source_url: {row['policy_id']}")
            if not SHA256_RE.fullmatch(row["content_sha256"]):
                errors.append(f"success row missing SHA256: {row['policy_id']}")
            if not row["raw_bytes"].isdigit() or int(row["raw_bytes"]) <= 0:
                errors.append(f"success row invalid raw_bytes: {row['policy_id']}")
    if set(seen_cells) != expected_cells:
        errors.append(
            f"coverage mismatch: expected={len(expected_cells)} "
            f"observed={len(seen_cells)}"
        )
    return errors


def audit_downloads(rows: list[dict[str, str]], project_root: str | Path) -> list[str]:
    """Check that successful raw files exist and match manifest byte metadata."""

    root = Path(project_root)
    errors: list[str] = []
    for row in rows:
        if row["retrieval_status"] != "success":
            errors.append(f"download not successful: {row['policy_id']}")
            continue
        path = root / row["raw_relpath"]
        if not path.is_file():
            errors.append(f"raw file missing: {row['policy_id']} -> {row['raw_relpath']}")
            continue
        payload = path.read_bytes()
        if hashlib.sha256(payload).hexdigest() != row["content_sha256"]:
            errors.append(f"SHA256 mismatch: {row['policy_id']}")
        if len(payload) != int(row["raw_bytes"]):
            errors.append(f"raw_bytes mismatch: {row['policy_id']}")
        if len(payload) < 1000:
            errors.append(f"raw file suspiciously short: {row['policy_id']}")
        if row["content_type"].lower().find("pdf") < 0:
            text = payload.decode("utf-8", errors="ignore")
            year = row["report_year"]
            if year not in text and year.encode("gb18030") not in payload:
                errors.append(f"report year not found in raw file: {row['policy_id']}")
    return errors
