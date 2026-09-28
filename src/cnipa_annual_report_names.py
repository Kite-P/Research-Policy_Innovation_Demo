from __future__ import annotations

import hashlib
import re
import unicodedata
from collections.abc import Iterable

_LEGAL_SUFFIX = re.compile(r"(?:股份有限公司|有限责任公司|有限公司|股份公司)$")
_LEGAL_LABELS = (
    "公司的中文名称", "公司中文名称", "公司名称", "公司全称",
)
_SHORT_LABELS = (
    "公司的中文简称", "公司中文简称", "公司简称", "证券简称", "股票简称",
    "A股简称", "英文简称", "外文名称", "英文名称",
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
    candidate = _clean(value)
    candidate = re.sub(r"^(?:全称|中文全称|名称)\s*", "", candidate)
    candidate = re.sub(r"^(?:是|否|无|不适用)\s*", "", candidate)
    candidate = re.split(r"[。；;，,\t]", candidate, maxsplit=1)[0]
    match = re.search(
        r"([\u4e00-\u9fffA-Za-z0-9（）()·.\-]{2,100}"
        r"(?:股份有限公司|有限责任公司|有限公司|股份公司))",
        candidate,
    )
    return match.group(1) if match else ""


def _label_value(lines: list[str], labels: tuple[str, ...], max_following: int = 3) -> str:
    return _label_value_with_evidence(lines, labels, max_following)[0]


def _label_value_with_evidence(
    lines: list[str], labels: tuple[str, ...], max_following: int = 3
) -> tuple[str, str, str]:
    for i, raw in enumerate(lines):
        line = raw.strip()
        for label in labels:
            pos = line.find(label)
            if pos < 0:
                continue
            remainder = line[pos + len(label):]
            # A short-name label must not match the contained legal-name label.
            if any(short in line[:pos] for short in _SHORT_LABELS):
                continue
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


def extract_annual_report_legal_name_evidence(
    text: str,
    *,
    expected_year: int,
    source_report_title: str = "",
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
    leading_lines = [line.strip() for line in text.splitlines()[:100] if line.strip()]
    observed_title = next(
        (line for line in leading_lines if "年度报告" in line), ""
    )
    title_for_check = title or observed_title
    result["source_report_title"] = title_for_check
    observed_year_match = re.search(r"(20\d{2})\s*年?年度报告", observed_title)
    if observed_year_match and int(observed_year_match.group(1)) != int(expected_year):
        result["failure_reason"] = "report_year_mismatch"
        return result
    full_title = re.search(r"20\d{2}\s*年?年度报告(?:全文)?", title_for_check)
    if re.search(r"年度报告摘要", observed_title or title_for_check) or (
        title_for_check and not full_title
    ):
        result["failure_reason"] = "annual_report_summary_rejected"
        return result
    if not title_for_check:
        result["failure_reason"] = "annual_report_title_not_found"
        return result
    years = {int(v) for v in re.findall(r"(?<!\d)(20\d{2})(?!\d)", title_for_check)}
    years |= {int(v) for v in re.findall(r"(?<!\d)(20\d{2})(?!\d)", text[:5000])}
    if years and int(expected_year) not in years:
        result["failure_reason"] = "report_year_mismatch"
        return result

    lines = [re.sub(r"\s+", " ", line).strip() for line in text.splitlines()]
    legal, legal_label, legal_context = _label_value_with_evidence(lines, _LEGAL_LABELS)
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
    change_line = next(
        (
            line for line in lines[:350]
            if any(label in line for label in flag_labels)
        ),
        "",
    )
    if change_line:
        flag_label = next(label for label in flag_labels if label in change_line)
        value = change_line.split(flag_label, maxsplit=1)[-1]
        if not value.strip():
            line_index = lines.index(change_line)
            value = " ".join(lines[line_index + 1 : line_index + 3])
        if re.search(r"否|未变更|无变更|未发生", value):
            result["company_name_change_flag"] = "NO"
        elif re.search(r"是|有变更|发生变更", value):
            result["company_name_change_flag"] = "YES"

    change_section_start = next(
        (
            index for index, line in enumerate(lines)
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
                index for index in range(change_section_start + 1, len(lines))
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
        r"([\u4e00-\u9fffA-Za-z0-9（）()·.\-]{2,100}?"
        r"(?:股份有限公司|有限责任公司|有限公司|股份公司))"
    )
    issuer_name_change_pattern = re.compile(
        r"(?:本公司|公司全称|公司名称)[^，。；]{0,30}?由"
        + legal_name_pattern
        + r"[^，。；]{0,30}?变更为"
        + legal_name_pattern
    )
    for index in range(len(lines)):
        window = "".join(lines[index : index + 3])
        compact_window = re.sub(r"\s+", "", window)
        if "公司名称" not in compact_window and "公司全称" not in compact_window:
            continue
        match = re.search(
            issuer_name_change_pattern,
            compact_window,
        )
        if (
            match
            and (match.group(2) == legal or match.group(1) == legal)
            and not re.search(r"子公司|被购买方|被投资单位|客户|供应商", compact_window)
        ):
            issuer_change_line = compact_window
            issuer_change_match = match
            break

    date_match = None
    if issuer_change_match:
        result["legal_name_previous"] = issuer_change_match.group(1)
        result["legal_name_new"] = issuer_change_match.group(2)
        date_matches = list(re.finditer(
            r"(20\d{2})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日",
            issuer_change_line,
        ))
        dates_before_event = [
            candidate for candidate in date_matches
            if candidate.end() <= issuer_change_match.start()
        ]
        if dates_before_event:
            date_match = dates_before_event[-1]
    if result["legal_name_previous"] and result["legal_name_new"]:
        if date_match:
            pass
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
        if result["company_name_change_flag"] == "UNKNOWN":
            if change_year == expected_year:
                result["company_name_change_flag"] = "YES"
            elif change_year == expected_year + 1:
                result["company_name_change_flag"] = "NO"

    if result["company_name_change_flag"] == "NO" and legal:
        result.update(
            evidence_status="CONFIRMED_NO_CHANGE",
            date_precision=(
                result["date_precision"]
                if result["change_effective_date"]
                else "year"
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
            or not date_match
            or int(date_match.group(1)) != expected_year
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
    previous = re.sub(
        r"\s+", "", unicodedata.normalize("NFKC", previous_legal_name)
    )
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
    if previous not in compact or new not in compact or not re.search(
        r"名称.{0,50}(?:变更|更名)|(?:变更|更名).{0,50}名称", compact
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
        if (
            "完成公司名称变更" in compact
            and announcement_date[:4] == str(expected_year)
        ):
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
        "http_status": int(http_status), "pdf_bytes": len(payload),
        "pdf_sha256": hashlib.sha256(payload).hexdigest() if not failure else "",
        "failure_reason": failure,
    }


def validate_firm_year_status_set(
    target: Iterable[tuple[str, int]], status: Iterable[tuple[str, int]]
) -> bool:
    return set(target) == set(status)


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
        ("SSE_current", rows.exchange.eq("SSE") & rows.delisting_date.isna()
         & rows.market_listing_date.lt("2020-01-01"), 15),
        ("SZSE_current", rows.exchange.eq("SZSE") & rows.delisting_date.isna()
         & rows.market_listing_date.lt("2020-01-01"), 15),
        ("SSE_delisted", rows.exchange.eq("SSE") & rows.delisting_date.notna(), 10),
        ("SZSE_delisted", rows.exchange.eq("SZSE") & rows.delisting_date.notna(), 10),
        ("recent_IPO", rows.exchange.isin(["SSE", "SZSE"])
         & rows.market_listing_date.ge("2020-01-01"), 20),
        ("long_listed", rows.exchange.isin(["SSE", "SZSE"])
         & rows.market_listing_date.lt("2000-01-01") & rows.delisting_date.isna(), 10),
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
        for key in candidates.sort_values("_rank").firm_key.head(minimum_firms-len(chosen)):
            chosen[str(key)] = "deterministic_fill"
    sample = rows.loc[rows.firm_key.isin(chosen)].copy()
    sample["pilot_stratum"] = sample.firm_key.map(chosen)
    return sample.sort_values("firm_key").reset_index(drop=True)
