"""Conservatively download canonical policy report bytes and update manifest metadata."""

from __future__ import annotations

import csv
import hashlib
import re
import subprocess
import tempfile
import time
from argparse import ArgumentParser
from datetime import datetime, timezone
from pathlib import Path

import requests

from src.policy_text_cleaning import clean_html

CHALLENGE_MARKERS = ("验证码", "访问验证", "安全验证", "请输入验证码", "请登录", "统一身份认证")
SUMMARY_MARKERS = ("一图读懂", "图解", "摘要", "速读", "要点", "解读", "摘登")


def validate_report_content(
    payload: bytes,
    content_type: str,
    province: str,
    report_year: int,
    title: str = "",
) -> str | None:
    """Return a review code unless the downloaded body resembles a complete report."""

    if not payload:
        return "empty_response_body"
    if "pdf" in content_type.lower() or payload.startswith(b"%PDF"):
        if not payload.startswith(b"%PDF"):
            return "invalid_pdf_signature"
        temp_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as handle:
                handle.write(payload)
                temp_path = Path(handle.name)
            extracted = subprocess.run(
                ["pdftotext", "-layout", "-enc", "UTF-8", str(temp_path), "-"],
                capture_output=True,
                check=False,
            )
        except OSError:
            return "pdf_text_extraction_unavailable"
        finally:
            if temp_path is not None:
                temp_path.unlink(missing_ok=True)
        if extracted.returncode != 0:
            return "pdf_text_extraction_failed"
        text = extracted.stdout.decode("utf-8", errors="replace")
    else:
        text, _, _ = clean_html(payload, content_type)

    compact = re.sub(r"\s+", "", text)
    lowered = compact.lower()
    if any(marker in title for marker in SUMMARY_MARKERS):
        return "summary_or_interpretation_title"
    if len(compact) < 5000 and any(marker in compact for marker in CHALLENGE_MARKERS):
        return "challenge_or_login_page"
    if len(compact) < 5000:
        return "report_text_too_short"
    normalized_title = re.sub(r"\s+", "", title)
    if "政府工作报告" not in compact and "政府工作报告" not in normalized_title:
        return "government_work_report_phrase_missing"
    if str(report_year) not in compact and str(report_year) not in normalized_title:
        return "report_year_missing_from_body"
    if province not in compact and province not in normalized_title:
        return "province_name_missing_from_body"
    if any(marker in lowered for marker in ("captcha", "verify you are human", "access denied")):
        return "challenge_or_error_page"
    return None


def fetch_manifest(
    manifest_path: str | Path,
    project_root: str | Path = ".",
    delay_seconds: float = 1.0,
    force_policy_ids: set[str] | None = None,
) -> None:
    root = Path(project_root)
    path = root / manifest_path
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        rows = list(reader)
        fieldnames = reader.fieldnames or []
    request_count = 0
    for row in rows:
        if (
            row.get("retrieval_status") == "success"
            and row.get("content_sha256")
            and row.get("policy_id") not in (force_policy_ids or set())
        ):
            continue
        if not row.get("raw_relpath"):
            source_path = row.get("source_url", "").lower().split("?")[0]
            extension = ".pdf" if source_path.endswith(".pdf") else ".html"
            row["raw_relpath"] = f"data/raw/policy_reports/html/{row['policy_id']}{extension}"
        raw_path = root / row["raw_relpath"]
        raw_path.parent.mkdir(parents=True, exist_ok=True)
        url = row.get("source_url", "")
        row["retrieved_at_utc"] = datetime.now(timezone.utc).isoformat()
        if not url:
            row["retrieval_status"] = "manual_review"
            row["review_status"] = "missing_source_url"
            continue
        try:
            if request_count:
                time.sleep(delay_seconds)
            request_count += 1
            response = requests.get(
                url,
                headers={"User-Agent": "research-policy-corpus/1.0"},
                timeout=40,
                allow_redirects=True,
            )
            row["http_status"] = str(response.status_code)
            row["final_url"] = response.url
            row["content_type"] = response.headers.get("Content-Type", "")
            if response.status_code >= 400:
                row["retrieval_status"] = (
                    "blocked" if response.status_code in {403, 429} else "http_error"
                )
                row["review_status"] = "manual_review"
                continue
            content = response.content
            validation_issue = validate_report_content(
                content,
                row.get("content_type", ""),
                row.get("province", ""),
                int(row["report_year"]),
                row.get("title", ""),
            )
            if validation_issue:
                row["retrieval_status"] = "manual_review"
                row["review_status"] = validation_issue
                row["notes"] = (
                    f"{row.get('notes', '')} content_validation={validation_issue}"
                ).strip()
                continue
            raw_path.write_bytes(content)
            row["content_sha256"] = hashlib.sha256(content).hexdigest()
            row["raw_bytes"] = str(len(content))
            row["retrieval_status"] = "success"
            row["review_status"] = "downloaded"
        except (requests.RequestException, TimeoutError, OSError) as exc:
            row["retrieval_status"] = "http_error"
            row["review_status"] = "manual_review"
            row["notes"] = f"{row.get('notes', '')} fetch_error={type(exc).__name__}".strip()
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


if __name__ == "__main__":
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", default="metadata/policy_source_manifest.csv")
    parser.add_argument("--project-root", default=".")
    parser.add_argument("--force-policy-id", action="append", default=[])
    args = parser.parse_args()
    fetch_manifest(args.manifest, args.project_root, force_policy_ids=set(args.force_policy_id))
