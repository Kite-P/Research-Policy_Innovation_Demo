"""Conservatively download canonical policy report bytes and update manifest metadata."""

from __future__ import annotations

import csv
import hashlib
import time
from datetime import datetime, timezone
from pathlib import Path

import requests


def fetch_manifest(
    manifest_path: str | Path,
    project_root: str | Path = ".",
    delay_seconds: float = 1.0,
) -> None:
    root = Path(project_root)
    path = root / manifest_path
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        rows = list(reader)
        fieldnames = reader.fieldnames or []
    for index, row in enumerate(rows):
        if row.get("retrieval_status") == "success" and row.get("content_sha256"):
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
            raw_path.write_bytes(content)
            row["content_sha256"] = hashlib.sha256(content).hexdigest()
            row["raw_bytes"] = str(len(content))
            row["retrieval_status"] = "success"
            row["review_status"] = "downloaded"
        except (requests.RequestException, TimeoutError, OSError) as exc:
            row["retrieval_status"] = "http_error"
            row["review_status"] = "manual_review"
            row["notes"] = f"{row.get('notes', '')} fetch_error={type(exc).__name__}".strip()
        if index < len(rows) - 1:
            time.sleep(delay_seconds)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


if __name__ == "__main__":
    fetch_manifest("metadata/policy_source_manifest.csv")
