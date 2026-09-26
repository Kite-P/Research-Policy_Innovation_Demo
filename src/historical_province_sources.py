from __future__ import annotations

import re
import shutil
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import requests


def atomic_replace_with_retry(source: Path, target: Path, attempts: int = 6) -> None:
    """Retry brief Windows sharing locks while atomically publishing a file."""
    for attempt in range(attempts):
        try:
            source.replace(target)
            return
        except PermissionError:
            if attempt == attempts - 1:
                raise
            time.sleep(min(0.2 * (2**attempt), 1.6))


class SourceBlocked(RuntimeError):
    """Public source requires a stop because access is restricted or challenged."""


def classify_source_response(status_code: int, body: str) -> str:
    if status_code in {401, 403, 429}:
        raise SourceBlocked(f"HTTP_{status_code}")
    lowered = str(body).lower()
    blocked_markers = (
        "验证码", "图形验证", "请完成验证", "访问验证", "安全验证", "captcha",
        "login required", "请登录", "登录后查看", "访问受限", "请求过于频繁",
    )
    if any(marker in lowered for marker in blocked_markers):
        raise SourceBlocked("CHALLENGE_OR_LOGIN_REQUIRED")
    if status_code < 200 or status_code >= 300:
        return f"http_error_{status_code}"
    return "ok"


CNINFO_STOCK_LIST_URL = "https://www.cninfo.com.cn/new/data/szse_stock.json"
CNINFO_ANNOUNCEMENT_QUERY_URL = "https://www.cninfo.com.cn/new/hisAnnouncement/query"
CNINFO_STATIC_BASE_URL = "https://static.cninfo.com.cn/"
CACHE_FORMAT_VERSION = "historical-province-cache-3"
READABLE_CACHE_FORMAT_VERSIONS = {"historical-province-cache-2", CACHE_FORMAT_VERSION}


def match_annual_report_title(title: object) -> int | None:
    """Return the report year for full annual reports, excluding summaries."""
    normalized = re.sub(r"<[^>]+>", "", str(title or "")).strip()
    match = re.search(
        r"(?P<year>20\d{2})\s*年?\s*年度报告(?:全文)?"
        r"(?:\s*[（(](?:修订(?:版|稿)?|更新(?:后|版)?|更正(?:后|版)?)[）)])?\s*$",
        normalized,
    )
    return int(match.group("year")) if match else None


class CNINFOAnnualReportClient:
    """Serial access to freely accessible CNINFO disclosure search and PDFs."""

    def __init__(
        self,
        cache_dir: Path,
        request_spacing: float = 1.0,
        timeout: float = 40.0,
        retries: int = 2,
        session: requests.Session | None = None,
        sleep=time.sleep,
    ) -> None:
        if request_spacing < 1.0:
            raise ValueError("request_spacing must be at least 1.0 second")
        self.cache_dir = Path(cache_dir)
        self.request_spacing = request_spacing
        self.timeout = timeout
        self.retries = retries
        self.session = session or requests.Session()
        self.sleep = sleep
        self._last_request = 0.0
        self._stock_catalog: dict[str, str] | None = None
        self.last_annual_report_query_audit: list[dict[str, object]] = []
        self.session.headers.update(
            {"User-Agent": "Mozilla/5.0", "Referer": "https://www.cninfo.com.cn/"}
        )

    def _request(self, method: str, url: str, **kwargs: Any) -> requests.Response:
        for attempt in range(self.retries + 1):
            delay = self.request_spacing - (time.monotonic() - self._last_request)
            if delay > 0:
                self.sleep(delay)
            self._last_request = time.monotonic()
            try:
                response = self.session.request(method, url, timeout=self.timeout, **kwargs)
            except (requests.Timeout, requests.ConnectionError):
                if attempt >= self.retries:
                    raise
                continue
            classify_source_response(response.status_code, response.text[:10000])
            if response.status_code >= 500 and attempt < self.retries:
                continue
            return response
        raise RuntimeError("source request exhausted retries")

    def stock_catalog(self) -> dict[str, str]:
        if self._stock_catalog is not None:
            return self._stock_catalog
        response = self._request("GET", CNINFO_STOCK_LIST_URL)
        payload = response.json()
        stock_list = payload.get("stockList")
        if not isinstance(stock_list, list):
            raise ValueError("CNINFO stock list has an unexpected structure")
        self._stock_catalog = {
            str(item["code"]).zfill(6): str(item["orgId"])
            for item in stock_list
            if item.get("code") and item.get("orgId")
        }
        return self._stock_catalog

    def list_annual_reports(
        self,
        stock_code: str,
        start_date: str = "2020-01-01",
        end_date: str | None = None,
    ) -> list[dict[str, object]]:
        code = str(stock_code).strip().zfill(6)
        self.last_annual_report_query_audit = []
        org_id = self.stock_catalog().get(code)
        if org_id is None:
            return []
        params = {
            "pageNum": 1,
            "pageSize": 30,
            "column": "szse",
            "tabName": "fulltext",
            "plate": "",
            "stock": f"{code},{org_id}",
            "searchkey": "",
            "secid": "",
            "category": "category_ndbg_szsh",
            "trade": "",
            "seDate": f"{start_date}~{end_date or datetime.now().date().isoformat()}",
            "sortName": "",
            "sortType": "",
            "isHLtitle": "true",
        }
        results: list[dict[str, object]] = []
        page = 1
        while page <= 20:
            params["pageNum"] = page
            response = self._request("POST", CNINFO_ANNOUNCEMENT_QUERY_URL, data=params)
            payload = response.json()
            announcements = payload.get("announcements") or []
            for item in announcements:
                title = re.sub(r"<[^>]+>", "", str(item.get("announcementTitle", "")))
                report_year = match_annual_report_title(title)
                broad_match = re.search(r"(?P<year>20\d{2})\s*年?\s*年度报告", title)
                legacy_match = re.search(
                    r"(20\d{2})\s*年年度报告(?:全文)?\s*$", title
                )
                if broad_match:
                    self.last_annual_report_query_audit.append({
                        "stock_code": code,
                        "title": title,
                        "report_year": int(broad_match.group("year")),
                        "legacy_match": bool(legacy_match),
                        "current_match": report_year is not None,
                        "adjunct_url": item.get("adjunctUrl"),
                    })
                adjunct = item.get("adjunctUrl")
                if report_year is None or not adjunct:
                    continue
                results.append(
                    {
                        "stock_code": code,
                        "report_year": report_year,
                        "title": title,
                        "announcement_id": str(item.get("announcementId") or ""),
                        "announcement_time": item.get("announcementTime"),
                        "source_url": CNINFO_STATIC_BASE_URL + str(adjunct).lstrip("/"),
                        "source_type": "official_annual_report",
                        "source_tier": "H1",
                    }
                )
            total_pages = int(payload.get("totalpages") or 0)
            if page >= total_pages or not announcements:
                break
            page += 1
        latest: dict[int, dict[str, object]] = {}
        for item in results:
            year = int(item["report_year"])
            previous = latest.get(year)
            if previous is None or int(item.get("announcement_time") or 0) > int(
                previous.get("announcement_time") or 0
            ):
                latest[year] = item
        return [latest[year] for year in sorted(latest)]

    def extract_pdf_text(self, source_url: str) -> str:
        response = self._request("GET", source_url)
        if not response.content.startswith(b"%PDF-"):
            raise ValueError("CNINFO response is not a PDF document")
        executable = shutil.which("pdftotext")
        if executable is None:
            raise RuntimeError("pdftotext is required for text-layer PDF extraction")
        result = subprocess.run(
            [executable, "-layout", "-", "-"],
            input=response.content,
            capture_output=True,
            timeout=180,
            check=False,
        )
        if result.returncode != 0:
            raise RuntimeError(f"pdftotext failed with exit code {result.returncode}")
        return result.stdout.decode("utf-8", errors="replace")

    def fetch_firm_reports(
        self,
        firm: dict[str, object],
        years: Iterable[int] = range(2020, 2026),
        refresh_years: Iterable[int] = (),
    ) -> list[dict[str, object]]:
        firm_key = str(firm["firm_key"])
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        cache_path = self.cache_dir / (re.sub(r"[^A-Za-z0-9_.-]+", "_", firm_key) + ".json")
        import json

        requested_years = {int(year) for year in years}
        years_to_refresh = {int(year) for year in refresh_years} & requested_years
        cached_by_year: dict[int, dict[str, object]] = {}
        if cache_path.exists():
            try:
                cached = json.loads(cache_path.read_text(encoding="utf-8"))
                if cached.get("cache_format_version") in READABLE_CACHE_FORMAT_VERSIONS:
                    cached_by_year = {
                        int(row["source_report_year"]): row for row in cached["records"]
                    }
            except (OSError, ValueError, TypeError, KeyError, AttributeError):
                cached_by_year = {}
        if requested_years.issubset(cached_by_year) and not years_to_refresh:
            return [cached_by_year[int(year)] for year in years]
        reports = self.list_annual_reports(str(firm["stock_code_current"]))
        reports_by_year = {int(item["report_year"]): item for item in reports}
        output_by_year = dict(cached_by_year)
        for year in years:
            if int(year) in output_by_year and int(year) not in years_to_refresh:
                continue
            document = reports_by_year.get(int(year))
            if document is None:
                record = {
                    "firm_key": firm_key,
                    "stock_code_current": str(firm["stock_code_current"]),
                    "source_report_year": int(year),
                    "historical_status": "missing",
                    "missing_reason": "annual_report_not_found",
                    "retrieved_at": datetime.now(timezone.utc).isoformat(),
                }
            else:
                text = self.extract_pdf_text(str(document["source_url"]))
                address = extract_registered_address(text)
                history = extract_registered_address_history(text)
                record = {
                    "firm_key": firm_key,
                    "stock_code_current": str(firm["stock_code_current"]),
                    "source_report_year": int(year),
                    "province_raw": address,
                    "source_type": document["source_type"],
                    "source_tier": document["source_tier"],
                    "source_report_title": document.get("title"),
                    "source_name": "CNINFO official annual report",
                    "source_url_or_id": document["source_url"],
                    "source_announcement_id": document["announcement_id"],
                    "source_report_date": datetime.fromtimestamp(
                        int(document["announcement_time"]) / 1000, tz=timezone.utc
                    ).date().isoformat(),
                    "registered_address_history_raw": history,
                    "extraction_method": "pdftotext_layout_text_layer",
                    "historical_status": "missing",
                    "missing_reason": (
                        "unresolved_temporal_semantics"
                        if address
                        else "registered_address_field_not_found"
                    ),
                    "retrieved_at": datetime.now(timezone.utc).isoformat(),
                }
            output_by_year[int(year)] = record
            payload = {
                "cache_format_version": CACHE_FORMAT_VERSION,
                "records": [output_by_year[key] for key in sorted(output_by_year)],
            }
            temporary = cache_path.with_suffix(".tmp")
            temporary.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            atomic_replace_with_retry(temporary, cache_path)
        return [output_by_year[int(year)] for year in years]


def extract_registered_address(report_text: str) -> str | None:
    """Extract a registered-address value even when PDF layout wraps the field."""
    text = report_text.replace("\u3000", " ").replace("\xa0", " ")
    lines = [line.strip() for line in text.splitlines()]
    label = re.compile(
        r"^\s*(?P<label>法定注册地址|(?:公司)?注册地址|公司注册地|(?:公司)?住所)"
        r"\s*[:：|]?\s*(?P<value>.*?)\s*$"
    )
    stop = re.compile(
        r"^(?:注册地址(?:的)?(?:邮政编码|历史变更)|(?:公司)?办公地址|办公地址|"
        r"公司网址|电子信箱|公司名称|法定代表人|经营范围|信息披露及备置地点)"
    )

    def clean_value(value: str) -> str | None:
        value = value.strip(" |\t:：，,；;")
        if not value or re.fullmatch(r"[\d\s-]+", value):
            return None
        if value.startswith(("的邮政编码", "邮政编码", "的历史", "历史变更")):
            return None
        return re.sub(r"\s+", "", value).strip("|:：，,；;") or None

    for index, line in enumerate(lines):
        if re.search(r"(?:公司)?注册地址(?:的)?历史变更(?:情况)?", line):
            continue
        match = label.search(line)
        if not match:
            continue
        value = clean_value(match.group("value"))
        if value and len(value) >= 3:
            return value

        # CNINFO's layout text frequently places the value before a standalone
        # label and wraps the remainder after it. Never cross another field.
        pieces = []
        previous = next((lines[i] for i in range(index - 1, -1, -1) if lines[i]), "")
        if previous and not stop.search(previous) and not label.search(previous):
            pieces.append(previous)
        for following in lines[index + 1 : index + 4]:
            if not following or stop.search(following) or label.search(following):
                break
            pieces.append(following)
        candidate = clean_value(" ".join(pieces))
        if candidate and len(candidate) >= 3:
            return candidate
    return None


def extract_registered_address_history(report_text: str) -> str | None:
    text = report_text.replace("\u3000", " ").replace("\xa0", " ")
    lines = text.splitlines()
    stop = re.compile(
        r"^\s*(?:办公地址|公司办公地址|办公地址的邮政编码|公司网址|电子信箱|"
        r"信息披露及备置地点|四、信息披露|五、公司股票简况)"
    )
    for index, line in enumerate(lines):
        match = re.search(
            r"(?:公司)?注册地址(?:的)?历史变更(?:情况)?\s*[:：|]?\s*(.*)$", line
        )
        if not match:
            continue
        pieces = [match.group(1).strip(" |\t:：")]
        for following in lines[index + 1 :]:
            if stop.search(following):
                break
            pieces.append(following.strip())
            if sum(map(len, pieces)) >= 1400:
                break
        value = re.sub(r"\s+", " ", " ".join(pieces)).strip(" |\t:：")
        return value or None
    return None


def parse_address_change_events(history_text: str | None) -> list[dict[str, str]]:
    """Parse explicit dated old/new address statements; ambiguous prose is ignored."""
    if not history_text:
        return []
    text = re.sub(r"\s+", "", history_text)
    events: list[dict[str, str]] = []
    transition = re.compile(
        r"(?:注册地址|注册地|公司住所|住所)[^。；;]{0,100}?"
        r"(?:由|从)[“\"‘']?(?P<old>[^”\"’'到至变更]{2,100})[”\"’']?"
        r"(?:变更为|变更至|迁至|迁址到|迁至现址|迁往|迁到)[“\"‘']?(?P<new>[^”\"’'。；;]{2,160})"
    )
    for sentence in re.split(r"[。；;]", text):
        match = transition.search(sentence)
        if not match:
            continue
        old = match.group("old").strip("“”‘’\"'：:，,")
        new = re.split(r"并于|并完成|并取得|同时", match.group("new"), maxsplit=1)[0]
        new = new.strip("“”‘’\"'：:，,")
        dates = list(
            re.finditer(r"(?P<year>20\d{2})年(?P<month>\d{1,2})月(?:(?P<day>\d{1,2})日)?", sentence)
        )
        if not dates or not old or not new:
            continue
        completion = re.search(r"(?:完成|办结|办理完毕|取得.{0,12}?营业执照|核准登记)", sentence)
        if completion:
            date_match = next(
                (item for item in reversed(dates) if item.start() < completion.start()), dates[-1]
            )
        else:
            date_match = dates[-1]
        year = int(date_match.group("year"))
        month = int(date_match.group("month"))
        day = int(date_match.groupdict().get("day") or 1)
        events.append(
            {
                "effective_date": f"{year:04d}-{month:02d}-{day:02d}",
                "old_address": old,
                "new_address": new,
            }
        )
    unique = {tuple(sorted(event.items())): event for event in events}
    return sorted(unique.values(), key=lambda event: event["effective_date"])
