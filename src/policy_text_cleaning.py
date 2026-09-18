"""Clean downloaded policy reports and extract industry-related paragraphs."""

from __future__ import annotations

import csv
import re
import subprocess
import unicodedata
from argparse import ArgumentParser
from html import unescape
from pathlib import Path

import pandas as pd
from bs4 import BeautifulSoup

QUALITY_THRESHOLDS = {
    "very_short_full_text": 500,
    "very_short_industry_text": 80,
    "abnormal_industry_share": 0.95,
}
BOILERPLATE_RE = re.compile(
    r"^(责任编辑|扫一扫|网站地图|主办单位|版权所有|备案号|打印|字体|分享|收藏|关闭|首页|当前位置)"
)
WHITESPACE_RE = re.compile(r"[ \t\f\v]+")


def load_keywords(path: str | Path) -> tuple[list[str], list[str]]:
    core: list[str] = []
    context: list[str] = []
    with Path(path).open("r", encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            (core if row["tier"] == "core" else context).append(row["term"])
    return sorted(set(core), key=len, reverse=True), sorted(set(context), key=len, reverse=True)


def decode_bytes(payload: bytes, content_type: str = "") -> tuple[str, str, str]:
    """Decode bytes without silently discarding malformed content."""

    candidates: list[str] = []
    match = re.search(r"charset=([\w-]+)", content_type, flags=re.I)
    if match:
        candidates.append(match.group(1))
    meta = payload[:4096].decode("ascii", errors="replace")
    match = re.search(r"charset\s*=\s*[\"']?([\w-]+)", meta, flags=re.I)
    if match:
        candidates.append(match.group(1))
    candidates.extend(["utf-8", "gb18030"])
    seen: set[str] = set()
    for encoding in candidates:
        if encoding.lower() in seen:
            continue
        seen.add(encoding.lower())
        try:
            return payload.decode(encoding), encoding, "ok"
        except (LookupError, UnicodeDecodeError):
            continue
    return payload.decode("utf-8", errors="replace"), "utf-8", "warning"


def normalize_text(text: str) -> str:
    text = unicodedata.normalize("NFKC", unescape(text))
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[\u0000-\u0008\u000b\u000c\u000e-\u001f\u007f]", "", text)
    lines = [WHITESPACE_RE.sub(" ", line).strip() for line in text.split("\n")]
    lines = [line for line in lines if line and not BOILERPLATE_RE.match(line)]
    return "\n".join(lines)


def split_paragraphs(text: str) -> list[str]:
    parts = [part.strip() for part in re.split(r"\n\s*\n+", text) if part.strip()]
    if len(parts) == 1:
        parts = [line.strip() for line in text.splitlines() if line.strip()]
    return parts


def clean_html(payload: bytes, content_type: str = "") -> tuple[str, str, str]:
    decoded, encoding, decode_status = decode_bytes(payload, content_type)
    soup = BeautifulSoup(decoded, "html.parser")
    for tag in soup.find_all(["script", "style", "noscript", "nav", "footer", "form"]):
        tag.decompose()
    blocks: list[str] = []
    containers = soup.find_all(
        attrs={
            "class": re.compile(
                r"(TRS_.*EDITOR|main_inner|article|content|正文|文章|detail)", re.I
            )
        }
    )
    search_root = (
        max(containers, key=lambda tag: len(tag.get_text(" ", strip=True)))
        if containers
        else soup
    )
    for tag in search_root.find_all(["h1", "h2", "h3", "h4", "h5", "h6", "p", "li"]):
        value = tag.get_text(" ", strip=True)
        if value:
            blocks.append(value)
    extracted = normalize_text("\n\n".join(blocks))
    container_text = normalize_text(search_root.get_text("\n", strip=True))
    if not blocks or len(extracted) < len(container_text) * 0.5:
        extracted = container_text
    if not extracted:
        blocks = [soup.get_text("\n", strip=True)]
        extracted = normalize_text("\n\n".join(blocks))
    return extracted, encoding, decode_status


def extract_pdf(path: str | Path) -> tuple[str, str, str]:
    result = subprocess.run(
        ["pdftotext", "-layout", "-enc", "UTF-8", str(path), "-"],
        check=False,
        capture_output=True,
    )
    if result.returncode != 0:
        return "", "pdf", "warning"
    return normalize_text(result.stdout.decode("utf-8", errors="replace")), "pdf", "ok"


def extract_report_text(path: str | Path, content_type: str = "") -> tuple[str, str, str]:
    raw_path = Path(path)
    if "pdf" in content_type.lower() or raw_path.read_bytes()[:4] == b"%PDF":
        return extract_pdf(raw_path)
    return clean_html(raw_path.read_bytes(), content_type)


def extract_industry_text(
    full_text: str,
    core_terms: list[str],
    context_terms: list[str],
) -> tuple[str, int, int, int, int]:
    paragraphs = split_paragraphs(full_text)
    selected: list[str] = []
    core_hits = 0
    context_hits = 0
    for paragraph in paragraphs:
        paragraph_core = sum(paragraph.count(term) for term in core_terms)
        paragraph_context = sum(paragraph.count(term) for term in context_terms)
        core_hits += paragraph_core
        context_hits += paragraph_context
        if paragraph_core > 0:
            selected.append(paragraph)
    industry = "\n\n".join(selected)
    return industry, core_hits, context_hits, core_hits + context_hits, len(selected)


def quality_flags(
    full_text: str,
    industry_text: str,
    industry_share: float,
    decode_status: str,
) -> str:
    flags: list[str] = []
    if not full_text:
        flags.append("empty_full_text")
    elif len(full_text) < QUALITY_THRESHOLDS["very_short_full_text"]:
        flags.append("very_short_full_text")
    if not industry_text:
        flags.append("empty_industry_text")
    elif len(industry_text) < QUALITY_THRESHOLDS["very_short_industry_text"]:
        flags.append("very_short_industry_text")
    if industry_share > QUALITY_THRESHOLDS["abnormal_industry_share"]:
        flags.append("abnormal_industry_share")
    if decode_status != "ok":
        flags.append("decode_warning")
    return ";".join(flags) if flags else "ok"


def clean_manifest(
    manifest_path: str | Path,
    keyword_path: str | Path,
    project_root: str | Path = ".",
) -> list[dict[str, object]]:
    root = Path(project_root)
    with Path(manifest_path).open("r", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    core_terms, context_terms = load_keywords(keyword_path)
    output: list[dict[str, object]] = []
    for row in rows:
        full_text, encoding_used, decode_status = extract_report_text(
            root / row["raw_relpath"], row["content_type"]
        )
        industry_text, core_hits, context_hits, total_hits, paragraph_count = extract_industry_text(
            full_text, core_terms, context_terms
        )
        share = len(industry_text) / len(full_text) if full_text else 0.0
        output.append(
            {
                "policy_id": row["policy_id"],
                "province": row["province"],
                "report_year": int(row["report_year"]),
                "title": row["title"],
                "publish_date": row["publish_date"],
                "source_url": row["source_url"],
                "full_text_clean": full_text,
                "industry_text_clean": industry_text,
                "full_text_chars": len(full_text),
                "industry_text_chars": len(industry_text),
                "industry_text_share": share,
                "core_keyword_hits": core_hits,
                "context_keyword_hits": context_hits,
                "keyword_hits_total": total_hits,
                "industry_paragraph_count": paragraph_count,
                "encoding_used": encoding_used,
                "decode_status": decode_status,
                "text_quality_flag": quality_flags(full_text, industry_text, share, decode_status),
            }
        )
    return output


def write_clean_corpus(
    manifest_path: str | Path,
    keyword_path: str | Path,
    output_path: str | Path,
    project_root: str | Path = ".",
) -> None:
    records = clean_manifest(manifest_path, keyword_path, project_root)
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(records).to_parquet(output, index=False)


if __name__ == "__main__":
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", default="metadata/policy_source_manifest.csv")
    parser.add_argument("--keywords", default="metadata/policy_industry_keywords.csv")
    parser.add_argument("--output", default="data/processed/policy_reports_clean.parquet")
    parser.add_argument("--project-root", default=".")
    args = parser.parse_args()
    write_clean_corpus(args.manifest, args.keywords, args.output, args.project_root)
