from __future__ import annotations

import hashlib
import re
import unicodedata
from collections.abc import Iterable, Mapping

PARSER_REVISION = "issuer_scope_v3"

_LEGAL_SUFFIX = re.compile(r"(?:股份有限公司|有限责任公司|有限公司|股份公司)$")
_LEGAL_LABELS = (
    "公司的中文名称",
    "公司中文名称",
    "公司名称",
    "公司全称",
)
_ISSUER_LEGAL_LABELS = (
    "公司的中文名称",
    "公司中文名称",
    "公司注册中文名称",
    "法定中文名称",
    "中文名称",
    "公司名称",
    "公司全称",
)
_SHORT_LABELS = (
    "公司的中文简称",
    "公司中文简称",
    "公司简称",
    "证券简称",
    "股票简称",
    "A股简称",
    "英文简称",
    "外文名称",
    "英文名称",
)
_FIELD_LABEL = re.compile(
    r"(?:公司的中文名称|公司中文名称|中文名称|公司名称|公司全称|"
    r"公司的中文简称|公司中文简称|公司简称|证券简称|股票简称|A股简称|"
    r"公司名称在报告期内是否变更|报告期内公司名称是否变更|"
    r"公司名称是否发生变更|公司名称是否变更|报告期内公司名称变更情况|"
    r"公司名称变更情况|变更前公司名称|变更后公司名称|"
    r"原公司名称|新公司名称|现更名为)"
)


def _clean(value: str) -> str:
    return re.sub(r"[\s:：|]+", "", value).strip("，。；;、")


def _legal_value(value: str) -> str:
    candidate = value.lstrip()
    candidate = re.sub(
        r"^(?:是|否|无|不适用)(?=$|[\s:：|｜])[\s:：|｜]*",
        "",
        candidate,
    )
    candidate = re.sub(r"[\s:：|｜]+", " ", candidate).strip()
    candidate = re.sub(r"(?<=[\u4e00-\u9fff])\s+(?=[\u4e00-\u9fff])", "", candidate)
    candidate = re.sub(r"^(?:全称|中文全称|名称)\s*", "", candidate)
    candidate = re.split(r"[。；;，,\t]", candidate, maxsplit=1)[0]
    match = re.search(
        r"([\u4e00-\u9fffA-Za-z0-9（）()·.\-\s]{2,120}?"
        r"(?:股份有限公司|有限责任公司|有限公司|股份公司))",
        candidate,
    )
    return match.group(1).strip() if match else ""


def _normalize_legal_name(value: str) -> str:
    normalized = re.sub(r"\s+", " ", unicodedata.normalize("NFKC", value)).strip()
    return re.sub(r"(?<=[\u4e00-\u9fff])\s+(?=[\u4e00-\u9fff])", "", normalized)


def _legal_name_key(value: str) -> str:
    return re.sub(r"\s+", "", unicodedata.normalize("NFKC", value))


def _label_value(lines: list[str], labels: tuple[str, ...], max_following: int = 3) -> str:
    return _label_value_with_evidence(lines, labels, max_following)[0]


def _label_value_with_evidence(
    lines: list[str], labels: tuple[str, ...], max_following: int = 3
) -> tuple[str, str, str]:
    for label in labels:
        for i, raw in enumerate(lines):
            line = raw.strip()
            # Treat labels as fields, not substrings in glossary prose such as
            # “股份改制前公司名称” or branch/subsidiary definitions.
            match = re.match(
                rf"^(?:[|｜]\s*)?(?:[（(][一二三四五六七八九十]+[）)]\s*)?"
                rf"{re.escape(label)}(?:\s*[:：|｜]\s*|\s+|$)",
                line,
            )
            if not match:
                continue
            if re.search(r"(?:^|\s)指(?:\s|$)", line[match.end() :]):
                continue
            if label in _SHORT_LABELS or any(
                line.startswith(short) and label != short for short in _SHORT_LABELS
            ):
                continue
            remainder = line[match.end() :]
            found = _legal_value(remainder)
            if found:
                return found, label, " | ".join(lines[i : i + 2])[:1000]
            continuation: list[str] = []
            for next_line in lines[i + 1 : i + 1 + max_following]:
                if _FIELD_LABEL.search(next_line):
                    break
                if next_line.strip():
                    continuation.append(next_line.strip())
                    joined = _legal_value("".join(continuation))
                    if joined:
                        context = " | ".join(lines[i : i + len(continuation) + 1])[:1000]
                        return joined, label, context
    return "", "", ""


def _annual_report_title_status(
    text: str, source_report_title: str, expected_year: int
) -> tuple[str, str]:
    year_token = r"(?P<year>20\d{2}|[二〇○零一二三四五六七八九]{4})"
    title_pattern = re.compile(
        year_token
        + r"\s*年?\s*年度报告(?:全文)?(?=$|[\s:：,，。；;（）()\[\]【】]|摘要|简版|节选)"
    )
    numeral_map = str.maketrans("〇○零一二三四五六七八九", "000123456789")
    text_candidates = text.splitlines()
    matching_years: set[int] = set()
    full_titles: list[str] = []
    summary_titles: list[str] = []
    for candidate in text_candidates:
        for match in title_pattern.finditer(candidate):
            raw_year = match.group("year")
            normalized_year = raw_year.translate(numeral_map)
            year = int(normalized_year)
            is_summary = bool(re.match(r"\s*(?:摘要|简版|节选)", candidate[match.end() :]))
            if year == expected_year and not is_summary:
                full_titles.append(candidate.strip())
            elif year == expected_year:
                summary_titles.append(candidate.strip())
            matching_years.add(year)
    if full_titles:
        return "", full_titles[0]
    source_matches = list(title_pattern.finditer(source_report_title))
    if source_matches:
        source_years = {
            int(match.group("year").translate(numeral_map)) for match in source_matches
        }
        source_is_full = any(
            match.group("year").translate(numeral_map) == str(expected_year)
            and not re.match(r"\s*(?:摘要|简版|节选)", source_report_title[match.end() :])
            for match in source_matches
        )
        if source_is_full and (not matching_years or expected_year in matching_years):
            return "", source_report_title
        matching_years.update(source_years)
    if summary_titles:
        return "annual_report_summary_rejected", summary_titles[0]
    if matching_years:
        return "report_year_mismatch", source_report_title
    return "annual_report_title_not_found", source_report_title


def extract_annual_report_legal_name_evidence(
    text: str,
    *,
    expected_year: int,
    source_report_title: str = "",
    source_report_year: int | None = None,
    source_is_official: bool = False,
    source_is_correct_issuer: bool = False,
    source_is_correct_year: bool = False,
    source_is_full_annual_report: bool = False,
) -> dict[str, object]:
    title = re.sub(r"<[^>]+>", "", source_report_title or "").strip()
    result: dict[str, object] = {
        "expected_year": int(expected_year),
        "source_report_title": title,
        "legal_name_current_in_report": "",
        "legal_name_at_year_end": "",
        "company_name_change_flag": "UNKNOWN",
        "legal_name_previous": "",
        "legal_name_new": "",
        "change_effective_date": "",
        "date_precision": "unknown",
        "valid_from": "",
        "valid_to": "",
        "temporal_match_uncertain": 1,
        "evidence_status": "LEGAL_NAME_EXTRACTION_FAILED",
        "failure_reason": "legal_name_not_found",
        "matched_label": "",
        "evidence_context": "",
    }
    title_status, title_for_check = _annual_report_title_status(text, title, int(expected_year))
    source_metadata_verified = (
        source_report_year == int(expected_year)
        and source_is_official
        and source_is_correct_issuer
        and source_is_correct_year
        and source_is_full_annual_report
    )
    if title_status == "annual_report_title_not_found" and source_metadata_verified:
        title_status = ""
    result["source_report_title"] = title_for_check
    if title_status:
        result["failure_reason"] = title_status
        return result

    lines = [re.sub(r"\s+", " ", line).strip() for line in text.splitlines()]
    issuer_heading = re.compile(
        r"(?:(?:第[二三]节\s*)?公司简介和主要财务指标|"
        r"公司基本情况(?:简介)?|[一二三四五六七八九十]+[、.．]\s*公司简介)"
    )
    heading_indexes = [
        index for index, line in enumerate(lines) if issuer_heading.fullmatch(line)
    ]

    def section_end(start: int) -> int:
        return next(
            (
                index
                for index in range(start + 1, len(lines))
                if re.match(r"\s*第[一二三四五六七八九十]+节", lines[index])
                and not issuer_heading.fullmatch(lines[index])
            ),
            len(lines),
        )

    issuer_info_start = -1
    issuer_info_lines = lines
    for heading_index in heading_indexes:
        candidate_lines = lines[heading_index : section_end(heading_index)]
        candidate_name, _, _ = _label_value_with_evidence(
            candidate_lines, _ISSUER_LEGAL_LABELS
        )
        if candidate_name:
            issuer_info_start = heading_index
            issuer_info_lines = candidate_lines
            break
    if issuer_info_start < 0 and heading_indexes:
        issuer_info_start = heading_indexes[0]
        issuer_info_lines = lines[issuer_info_start : section_end(issuer_info_start)]
    legal, legal_label, legal_context = _label_value_with_evidence(
        issuer_info_lines,
        _ISSUER_LEGAL_LABELS if issuer_info_start >= 0 else _LEGAL_LABELS,
    )
    if not legal and issuer_info_start < 0:
        fallback_end = next(
            (index for index, line in enumerate(lines[:500]) if line == "释义"),
            min(len(lines), 500),
        )
        legal, legal_label, legal_context = _label_value_with_evidence(
            lines[:fallback_end], _LEGAL_LABELS
        )
    if legal:
        result["legal_name_current_in_report"] = legal
        result["legal_name_at_year_end"] = legal
        result["failure_reason"] = ""
        result["matched_label"] = legal_label
        result["evidence_context"] = legal_context

    flag_labels = (
        "公司名称在报告期内是否变更",
        "报告期内公司名称是否变更",
        "公司名称是否发生变更",
        "公司名称是否变更",
        "报告期内公司名称变更情况",
    )
    flag_scope = issuer_info_lines if issuer_info_start >= 0 else lines
    for index, line in enumerate(flag_scope):
        flag_label = next(
            (
                label
                for label in flag_labels
                if re.match(rf"^{re.escape(label)}(?:\s*[:：|｜]\s*|\s+|$)", line)
            ),
            "",
        )
        if not flag_label:
            continue
        match = re.match(rf"^{re.escape(flag_label)}\s*[:：|｜]?\s*(.*)$", line)
        value_parts = [match.group(1)] if match else []
        if not "".join(value_parts).strip():
            next_line = next(
                (candidate.strip() for candidate in flag_scope[index + 1 :] if candidate.strip()),
                "",
            )
            if re.match(
                r"^(?:否|是|未变更|无变更|未发生(?:变更)?|有变更|发生变更)(?:$|[\s|｜,，。；;])",
                next_line,
            ):
                value_parts.append(next_line)
        value = " ".join(value_parts)
        if re.match(
            r"^(?:否|未变更|无变更|未发生(?:变更)?|(?:报告期内)?(?:公司名称)?(?:未变更|无变更|未发生变更))(?:$|[\s|｜,，。；;])",
            value.strip(),
        ):
            result["company_name_change_flag"] = "NO"
        elif re.match(
            r"^(?:是|有变更|发生变更|(?:报告期内)?(?:公司名称)?(?:有变更|发生变更))(?:$|[\s|｜,，。；;])",
            value.strip(),
        ):
            result["company_name_change_flag"] = "YES"
        break

    change_section_start = next(
        (
            index
            for index, line in enumerate(lines)
            if (
                re.match(r"\s*[（(][一二三四五六七八九十]+[）)]", line)
                or re.match(r"\s*[一二三四五六七八九十]+[、.．]", line)
            )
            and "公司名称变更" in line
        ),
        -1,
    )
    name_change_section = ""
    if change_section_start >= 0:
        change_section_end = next(
            (
                index
                for index in range(change_section_start + 1, len(lines))
                if re.match(r"\s*[（(][一二三四五六七八九十]+[）)]", lines[index])
            ),
            len(lines),
        )
        section_lines = lines[change_section_start:change_section_end]
        name_change_section = "\n".join(section_lines)
        result["legal_name_previous"] = _label_value(
            section_lines, ("原公司名称", "变更前公司名称")
        )
        result["legal_name_new"] = _label_value(
            section_lines, ("现更名为", "变更后公司名称", "新公司名称")
        )
        if (
            result["legal_name_previous"]
            and not result["legal_name_new"]
            and legal
            and legal != result["legal_name_previous"]
        ):
            result["legal_name_new"] = legal
    else:
        if result["company_name_change_flag"] == "YES":
            basic_lines = lines[:350]
            result["legal_name_previous"] = _label_value(
                basic_lines, ("变更前公司名称", "原公司名称")
            )
            result["legal_name_new"] = _label_value(
                basic_lines, ("变更后公司名称", "新公司名称", "现更名为")
            )
    issuer_change_line = ""
    issuer_change_match = None
    legal_name_pattern = (
        r"([\u4e00-\u9fffA-Za-z0-9（）()·.\-\s]{2,120}?"
        r"(?:股份有限公司|有限责任公司|有限公司|股份公司))"
    )
    issuer_name_change_pattern = re.compile(
        r"(?:本公司|公司全称|公司名称)[^，。；]{0,30}?由[“\"「『]?"
        + legal_name_pattern
        + r"[”\"」』]?[^，。；]{0,30}?变更为[“\"「『]?"
        + legal_name_pattern
        + r"[”\"」』]?"
    )
    explicit_report_period_change = False
    paragraphs = re.split(r"(?<=[。；;])", "\n".join(lines))
    for paragraph in paragraphs:
        if "公司名称" not in paragraph and "公司全称" not in paragraph:
            continue
        match = re.search(
            issuer_name_change_pattern,
            paragraph,
        )
        if (
            match
            and legal
            and _legal_name_key(match.group(2)) == _legal_name_key(legal)
            and not re.search(r"子公司|被购买方|被投资单位|客户|供应商", paragraph)
        ):
            issuer_change_line = paragraph
            issuer_change_match = match
            explicit_report_period_change = bool(
                re.search(r"报告期内.{0,20}$", paragraph[: match.start()])
            )
            break

    date_match = None
    if issuer_change_match:
        result["legal_name_previous"] = _normalize_legal_name(issuer_change_match.group(1))
        result["legal_name_new"] = _normalize_legal_name(issuer_change_match.group(2))
        date_matches = list(
            re.finditer(
                r"(20\d{2})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日",
                issuer_change_line,
            )
        )
        dates_before_event = [
            candidate
            for candidate in date_matches
            if candidate.end() <= issuer_change_match.start()
        ]
        if dates_before_event:
            date_match = dates_before_event[-1]
    if result["legal_name_previous"] and result["legal_name_new"]:
        if date_match:
            pass
        elif issuer_change_match:
            # A date elsewhere in the report is not evidence for this specific name pair.
            date_match = None
        elif name_change_section:
            date_match = re.search(
                r"名称.{0,20}自\s*(20\d{2})\s*年\s*(\d{1,2})"
                r"\s*月\s*(\d{1,2})\s*日",
                name_change_section,
            )
            if not date_match:
                date_match = re.search(
                    r"(?:名称变更|变更为|工商登记变更)[^\n。；]{0,80}?"
                    r"(20\d{2})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日",
                    name_change_section,
                )
        else:
            names = (
                str(result["legal_name_previous"]),
                str(result["legal_name_new"]),
            )
            for paragraph in re.split(r"\n\s*\n", "\n".join(lines)):
                if not any(name and name in paragraph for name in names):
                    continue
                if not re.search(r"名称.{0,12}(?:变更|登记)|变更为|工商", paragraph):
                    continue
                date_match = re.search(
                    r"[^\n。；]{0,100}?(20\d{2})\s*年\s*(\d{1,2})"
                    r"\s*月\s*(\d{1,2})\s*日",
                    paragraph,
                )
                if date_match:
                    break

    if date_match:
        date = (
            f"{int(date_match.group(1)):04d}-"
            f"{int(date_match.group(2)):02d}-{int(date_match.group(3)):02d}"
        )
        change_year = int(date_match.group(1))
        result.update(
            change_effective_date=date,
            date_precision="exact_date",
            temporal_match_uncertain=0,
            failure_reason="",
        )
        if legal == result["legal_name_new"]:
            result.update(valid_from=date, valid_to="")
            if change_year > expected_year:
                result["legal_name_at_year_end"] = str(result["legal_name_previous"])
            else:
                result["legal_name_at_year_end"] = str(result["legal_name_new"])
        elif legal == result["legal_name_previous"]:
            result.update(valid_from="", valid_to=date)
            if change_year <= expected_year:
                result["legal_name_at_year_end"] = str(result["legal_name_new"])
    if explicit_report_period_change and result["company_name_change_flag"] == "UNKNOWN":
        result["company_name_change_flag"] = "YES"
        if not date_match or int(date_match.group(1)) != expected_year:
            result["change_effective_date"] = ""
            result["date_precision"] = "year"
            result["temporal_match_uncertain"] = 0

    if result["company_name_change_flag"] == "NO" and legal:
        result.update(
            evidence_status="CONFIRMED_NO_CHANGE",
            date_precision=(
                result["date_precision"] if result["change_effective_date"] else "year"
            ),
            valid_from=(
                str(expected_year)
                if result["change_effective_date"]
                and int(str(result["change_effective_date"])[:4]) > expected_year
                else str(result["change_effective_date"] or expected_year)
            ),
            valid_to=(
                str(result["change_effective_date"])
                if result["change_effective_date"]
                and int(str(result["change_effective_date"])[:4]) > expected_year
                else str(expected_year)
            ),
            temporal_match_uncertain=0,
        )
    elif result["company_name_change_flag"] == "YES":
        if (
            not result["legal_name_previous"]
            or not result["legal_name_new"]
            or (
                not explicit_report_period_change
                and (not date_match or int(date_match.group(1)) != expected_year)
            )
        ):
            result.update(
                evidence_status="TEMPORAL_UNRESOLVED",
                failure_reason="change_not_fully_dated_within_report_year",
                temporal_match_uncertain=1,
                date_precision="year",
                valid_from=str(expected_year),
                valid_to=str(expected_year),
            )
        else:
            result.update(evidence_status="CONFIRMED_NAME_CHANGE", failure_reason="")
    elif legal and date_match and legal == result["legal_name_new"]:
        result.update(
            evidence_status="CONFIRMED_YEAR_END_NAME_ONLY",
            temporal_match_uncertain=0,
        )
    elif legal:
        result.update(
            evidence_status="CONFIRMED_YEAR_END_NAME_ONLY",
            date_precision="year",
            valid_from=str(expected_year),
            valid_to=str(expected_year),
            temporal_match_uncertain=1,
        )
    return result


def extract_company_name_change_announcement(
    text: str,
    *,
    expected_year: int,
    previous_legal_name: str,
    new_legal_name: str,
    announcement_date: str = "",
) -> dict[str, object]:
    """Validate an H2 notice for one known issuer and recover an explicit date."""
    compact = re.sub(r"\s+", "", unicodedata.normalize("NFKC", text))
    previous = re.sub(r"\s+", "", unicodedata.normalize("NFKC", previous_legal_name))
    new = re.sub(r"\s+", "", unicodedata.normalize("NFKC", new_legal_name))
    result: dict[str, object] = {
        "previous_legal_name": previous_legal_name,
        "new_legal_name": new_legal_name,
        "change_effective_date": "",
        "date_precision": "unknown",
        "temporal_match_uncertain": 1,
        "company_name_change_flag": "UNKNOWN",
        "legal_name_at_year_end": "",
        "evidence_status": "TEMPORAL_UNRESOLVED",
        "failure_reason": "explicit_registration_date_not_found",
    }
    if not previous or not new or previous == new:
        result["failure_reason"] = "invalid_old_new_name_pair"
        return result
    if (
        previous not in compact
        or new not in compact
        or not re.search(r"名称.{0,50}(?:变更|更名)|(?:变更|更名).{0,50}名称", compact)
    ):
        result["failure_reason"] = "notice_does_not_confirm_expected_name_pair"
        return result
    pair_patterns = (
        re.escape(previous)
        + r"[“”\"'「」『』:：,，;；、()（）-]{0,8}"
        + r"(?:变更为|更名为|变更成|更名成|变为)"
        + r"[“”\"'「」『』:：,，;；、()（）-]{0,8}"
        + re.escape(new),
        r"(?:原公司名称|原名称|变更前(?:公司名称)?)[:：]?"
        + re.escape(previous)
        + r"[，,；;|]{0,6}"
        + r"(?:新公司名称|新名称|现公司名称|变更后(?:公司名称)?)[:：]?"
        + re.escape(new),
    )
    if not any(re.search(pattern, compact) for pattern in pair_patterns):
        result["failure_reason"] = "notice_does_not_confirm_expected_name_pair"
        return result

    date_pattern = re.compile(
        r"(20\d{2})年(\d{1,2})月(\d{1,2})日"
        r"[^。；]{0,100}?(?:完成|办理|办妥)[^。；]{0,40}?工商变更登记"
    )
    date_match = date_pattern.search(compact)
    if not date_match:
        date_pattern = re.compile(
            r"工商变更登记[^。；]{0,80}?(20\d{2})年"
            r"(\d{1,2})月(\d{1,2})日"
        )
        date_match = date_pattern.search(compact)
    if not date_match:
        if "完成公司名称变更" in compact and announcement_date[:4] == str(expected_year):
            result.update(
                date_precision="year",
                company_name_change_flag="YES",
                legal_name_at_year_end=new_legal_name,
                evidence_status="CONFIRMED_NAME_CHANGE",
                failure_reason="",
                temporal_match_uncertain=1,
            )
        return result

    event_date = (
        f"{int(date_match.group(1)):04d}-"
        f"{int(date_match.group(2)):02d}-{int(date_match.group(3)):02d}"
    )
    event_year = int(date_match.group(1))
    result.update(
        change_effective_date=event_date,
        date_precision="exact_date",
        failure_reason="",
        temporal_match_uncertain=0,
    )
    if event_year == int(expected_year):
        result.update(
            company_name_change_flag="YES",
            legal_name_at_year_end=new_legal_name,
            evidence_status="CONFIRMED_NAME_CHANGE",
        )
    elif event_year > int(expected_year):
        result.update(
            company_name_change_flag="NO",
            legal_name_at_year_end=previous_legal_name,
            evidence_status="CONFIRMED_NO_CHANGE",
        )
    else:
        result.update(
            company_name_change_flag="UNKNOWN",
            legal_name_at_year_end=new_legal_name,
            evidence_status="CONFIRMED_YEAR_END_NAME_ONLY",
            failure_reason="name_change_predates_target_year",
        )
    return result


def validate_pdf_payload(
    payload: bytes, http_status: int = 200, minimum_bytes: int = 1024
) -> dict[str, object]:
    failure = ""
    if http_status < 200 or http_status >= 300:
        failure = f"http_error_{http_status}"
    elif not payload.startswith(b"%PDF-"):
        failure = "response_not_pdf"
    elif len(payload) < minimum_bytes:
        failure = "pdf_too_small"
    return {
        "http_status": int(http_status),
        "pdf_bytes": len(payload),
        "pdf_sha256": hashlib.sha256(payload).hexdigest() if not failure else "",
        "failure_reason": failure,
    }


def validate_firm_year_status_set(
    target: Iterable[tuple[str, int]], status: Iterable[tuple[str, int]]
) -> bool:
    return set(target) == set(status)


def is_change_related_candidate(
    row: Mapping[str, object], *, adjacent_year_name_change: bool = False
) -> bool:
    """Identify Pilot firm-year rows needing change-event review."""
    previous = str(row.get("legal_name_previous", "") or "").strip()
    new = str(row.get("legal_name_new", "") or "").strip()
    tier = str(row.get("change_evidence_tier", "") or "").upper()
    evidence_url = str(row.get("change_evidence_url", "") or "").strip()
    status = str(row.get("evidence_status", "") or "").upper()
    reason = str(row.get("failure_reason", "") or "")
    legacy_review = str(row.get("change_case_reviewed", "") or "").upper()
    context = str(row.get("evidence_context", "") or "")
    parser_pattern = bool(
        re.search(r"(?:公司名称|公司全称|本公司).{0,40}(?:由|从).{0,80}(?:变更为|更名为)", context)
    )
    unresolved_name_change = status == "TEMPORAL_UNRESOLVED" and bool(
        re.search(r"名称|name|legal|issuer", reason, re.IGNORECASE)
    )
    return bool(
        str(row.get("company_name_change_flag", "")).upper() == "YES"
        or previous
        or new
        or tier == "H2"
        or evidence_url
        or unresolved_name_change
        or adjacent_year_name_change
        or legacy_review == "YES"
        or parser_pattern
    )


def build_canonical_change_event_roster(
    rows: Iterable[Mapping[str, object]],
) -> tuple[list[dict[str, object]], dict[str, str]]:
    """Build event identities without conflating event counts and row counts."""
    ordered = sorted(
        (dict(row) for row in rows),
        key=lambda item: (str(item.get("firm_key", "")), str(item.get("year", ""))),
    )
    row_keys = [(str(row.get("firm_key", "")), str(row.get("year", ""))) for row in ordered]
    if len(row_keys) != len(set(row_keys)):
        raise ValueError("DUPLICATE_CHANGE_CANDIDATE_ROW_KEY")
    parent = list(range(len(ordered)))

    def find(index: int) -> int:
        while parent[index] != index:
            parent[index] = parent[parent[index]]
            index = parent[index]
        return index

    def official(row: Mapping[str, object]) -> bool:
        return str(row.get("change_evidence_tier", "")).upper() in {"H1", "H2"} and str(
            row.get("change_evidence_url", "")
        ).startswith("https://")

    def basis(row: Mapping[str, object]) -> tuple[str, str]:
        if not official(row):
            return "", ""
        precision = str(row.get("date_precision", "")).lower()
        effective = str(row.get("change_effective_date", "") or "")
        if precision == "exact_date" and re.fullmatch(r"20\d{2}-\d{2}-\d{2}", effective):
            return "exact", effective
        if precision == "year":
            event_year = (
                effective[:4] if re.fullmatch(r"20\d{2}", effective) else str(row.get("year", ""))
            )
            source_id = str(row.get("change_announcement_id", "") or "") or str(
                row.get("change_evidence_url", "") or ""
            )
            return ("year", f"{event_year}|{source_id}") if source_id else ("", "")
        return "", ""

    for left in range(len(ordered)):
        a = ordered[left]
        a_base = (
            str(a.get("firm_key", "") or ""),
            str(a.get("legal_name_previous", "") or ""),
            str(a.get("legal_name_new", "") or ""),
        )
        if not all(a_base):
            continue
        for right in range(left + 1, len(ordered)):
            b = ordered[right]
            b_base = (
                str(b.get("firm_key", "") or ""),
                str(b.get("legal_name_previous", "") or ""),
                str(b.get("legal_name_new", "") or ""),
            )
            if a_base != b_base or not official(a) or not official(b):
                continue
            ann_a = str(a.get("change_announcement_id", "") or "")
            ann_b = str(b.get("change_announcement_id", "") or "")
            basis_a, value_a = basis(a)
            basis_b, value_b = basis(b)
            corroborated = bool(
                (ann_a and ann_a == ann_b)
                or (basis_a == basis_b == "exact" and value_a == value_b)
                or (basis_a == basis_b == "year" and value_a == value_b)
            )
            if corroborated:
                parent[find(right)] = find(left)

    groups: dict[int, list[dict[str, object]]] = {}
    for index, row in enumerate(ordered):
        groups.setdefault(find(index), []).append(row)

    event_groups: list[tuple[str, list[dict[str, object]], str]] = []
    for members in groups.values():
        members = sorted(
            members,
            key=lambda item: (str(item.get("firm_key", "")), str(item.get("year", ""))),
        )
        first = members[0]
        bases = sorted(
            {f"{kind}:{value}" for item in members for kind, value in [basis(item)] if kind}
        )
        announcement_ids = sorted(
            {
                str(item.get("change_announcement_id", "") or "")
                for item in members
                if str(item.get("change_announcement_id", "") or "")
            }
        )
        if announcement_ids:
            link_basis = "announcement:" + "|".join(announcement_ids)
        elif bases:
            link_basis = "|".join(bases)
        else:
            link_basis = "row:" + ";".join(
                sorted(f"{item.get('firm_key', '')}|{item.get('year', '')}" for item in members)
            )
        identity = "|".join(
            (
                str(first.get("firm_key", "") or ""),
                str(first.get("legal_name_previous", "") or ""),
                str(first.get("legal_name_new", "") or ""),
                link_basis,
            )
        )
        verified = all(official(item) for item in members) and bool(bases or announcement_ids)
        event_groups.append((identity, members, "VERIFIED" if verified else "UNRESOLVED"))

    events: list[dict[str, object]] = []
    row_mapping: dict[str, str] = {}
    for identity, members, identity_status in sorted(event_groups, key=lambda item: item[0]):
        dates = sorted(
            {
                str(item.get("change_effective_date", ""))
                for item in members
                if str(item.get("date_precision", "")).lower() == "exact_date"
                and str(item.get("change_effective_date", ""))
            }
        )
        conflict = len(dates) > 1
        precision = (
            "exact_date"
            if len(dates) == 1
            else str(members[0].get("date_precision", "unknown") or "unknown")
        )
        effective_date = dates[0] if len(dates) == 1 else ""
        event_id = "EVT-" + hashlib.sha256(identity.encode("utf-8")).hexdigest()[:20]
        rows_text = ";".join(
            sorted({f"{item.get('firm_key', '')}|{item.get('year', '')}" for item in members})
        )
        for item in members:
            row_mapping[f"{item.get('firm_key', '')}|{item.get('year', '')}"] = event_id
        events.append(
            {
                "event_id": event_id,
                "firm_key": str(members[0].get("firm_key", "") or ""),
                "previous_legal_name": str(members[0].get("legal_name_previous", "") or ""),
                "new_legal_name": str(members[0].get("legal_name_new", "") or ""),
                "effective_date": effective_date,
                "date_precision": precision,
                "evidence_tier": "|".join(
                    sorted(
                        {
                            str(item.get("change_evidence_tier", "") or "")
                            for item in members
                            if str(item.get("change_evidence_tier", "") or "")
                        }
                    )
                ),
                "evidence_source": "|".join(
                    sorted(
                        {
                            str(item.get("change_evidence_source", "") or "")
                            for item in members
                            if str(item.get("change_evidence_source", "") or "")
                        }
                    )
                ),
                "evidence_url": "|".join(
                    sorted(
                        {
                            str(item.get("change_evidence_url", "") or "")
                            for item in members
                            if str(item.get("change_evidence_url", "") or "")
                        }
                    )
                ),
                "announcement_id": "|".join(
                    sorted(
                        {
                            str(item.get("change_announcement_id", "") or "")
                            for item in members
                            if str(item.get("change_announcement_id", "") or "")
                        }
                    )
                ),
                "event_verification_status": (
                    "UNRESOLVED_CONFLICT" if conflict else identity_status
                ),
                "manual_review_status": "PENDING",
                "source_firm_year_rows": rows_text,
                "event_notes": "identity_basis=" + link_basis,
            }
        )
    return events, row_mapping


def select_legal_name_pilot(
    firms,
    *,
    seed: str = "20260927",
    minimum_firms: int = 80,
    required_firm_keys: Iterable[str] = (),
):
    """Select a deterministic, stratified firm sample without taking leading keys."""
    import pandas as pd

    required = set(map(str, required_firm_keys))
    rows = firms.drop_duplicates("firm_key").copy()
    rows["firm_key"] = rows["firm_key"].astype(str)
    rows["market_listing_date"] = pd.to_datetime(rows["market_listing_date"], errors="coerce")
    rows["delisting_date"] = pd.to_datetime(rows["delisting_date"], errors="coerce")
    rows["pilot_stratum"] = ""

    strata = (
        (
            "SSE_current",
            rows.exchange.eq("SSE")
            & rows.delisting_date.isna()
            & rows.market_listing_date.lt("2020-01-01"),
            15,
        ),
        (
            "SZSE_current",
            rows.exchange.eq("SZSE")
            & rows.delisting_date.isna()
            & rows.market_listing_date.lt("2020-01-01"),
            15,
        ),
        ("SSE_delisted", rows.exchange.eq("SSE") & rows.delisting_date.notna(), 10),
        ("SZSE_delisted", rows.exchange.eq("SZSE") & rows.delisting_date.notna(), 10),
        (
            "recent_IPO",
            rows.exchange.isin(["SSE", "SZSE"]) & rows.market_listing_date.ge("2020-01-01"),
            20,
        ),
        (
            "long_listed",
            rows.exchange.isin(["SSE", "SZSE"])
            & rows.market_listing_date.lt("2000-01-01")
            & rows.delisting_date.isna(),
            10,
        ),
    )
    chosen: dict[str, str] = {}
    for key in sorted(required):
        if key in set(rows.firm_key):
            chosen[key] = "required_case"
    for label, mask, count in strata:
        candidates = rows.loc[mask & ~rows.firm_key.isin(chosen)].copy()
        candidates["_rank"] = candidates.firm_key.map(
            lambda key: hashlib.sha256(f"{seed}|{key}".encode("utf-8")).hexdigest()
        )
        for key in candidates.sort_values("_rank").firm_key.head(count):
            chosen[str(key)] = label
    if len(chosen) < minimum_firms:
        candidates = rows.loc[~rows.firm_key.isin(chosen)].copy()
        candidates["_rank"] = candidates.firm_key.map(
            lambda key: hashlib.sha256(f"{seed}|{key}".encode("utf-8")).hexdigest()
        )
        for key in candidates.sort_values("_rank").firm_key.head(minimum_firms - len(chosen)):
            chosen[str(key)] = "deterministic_fill"
    sample = rows.loc[rows.firm_key.isin(chosen)].copy()
    sample["pilot_stratum"] = sample.firm_key.map(chosen)
    return sample.sort_values("firm_key").reset_index(drop=True)
