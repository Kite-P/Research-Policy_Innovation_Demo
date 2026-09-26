from pathlib import Path

import pandas as pd
import pytest

from scripts.run_historical_province_full import _prepare_stata_export
from src.historical_province import (
    HISTORICAL_STATUSES,
    assign_historical_province_chunks,
    build_historical_province_target,
    build_policy_geography_coverage,
    choose_preferred_candidate,
    classify_static_profile,
    evaluate_historical_province_pilot_gate,
    infer_province_for_year,
    normalize_province,
    province_from_address,
    resolve_historical_province_panel,
    select_historical_province_pilot,
    summarize_historical_province_coverage,
)
from src.historical_province_sources import (
    CACHE_FORMAT_VERSION,
    CNINFOAnnualReportClient,
    SourceBlocked,
    classify_source_response,
    extract_registered_address,
    extract_registered_address_history,
    parse_address_change_events,
)


def _universe():
    rows = []
    for exchange in ("SSE", "SZSE", "BSE"):
        for i in range(12):
            firm_key = f"{exchange}:{i:06d}:2010-01-01"
            for year in range(2020, 2026):
                rows.append(
                    {
                        "firm_key": firm_key,
                        "exchange": exchange,
                        "stock_code_current": f"{i:06d}",
                        "company_name_legal": f"公司{i}",
                        "market_listing_date": pd.Timestamp("2010-01-01"),
                        "listing_date": pd.Timestamp("2010-01-01"),
                        "delisting_date": pd.NaT if i % 2 else pd.Timestamp("2022-06-01"),
                        "year": year,
                        "industry_known": True,
                        "is_financial_industry": False,
                    }
                )
    rows.append(
        {
            "firm_key": "SSE:999999:2019-01-01", "exchange": "SSE",
            "stock_code_current": "999999", "company_name_legal": "新上市",
            "market_listing_date": pd.Timestamp("2019-01-01"),
            "listing_date": pd.Timestamp("2019-01-01"), "delisting_date": pd.NaT,
            "year": 2019, "industry_known": True, "is_financial_industry": False,
        }
    )
    return pd.DataFrame(rows)


def test_target_preserves_only_legal_phase_a_firm_years():
    target = build_historical_province_target(_universe())
    assert len(target) == 144
    assert target.groupby("firm_key").size().eq(6).all()
    assert set(target.exchange) == {"SSE", "SZSE"}
    assert target.year.min() == 2020 and target.year.max() == 2025


def test_target_retains_only_actual_listing_years_and_exact_keys():
    universe = _universe()
    invalid = (universe.firm_key == "SSE:000000:2010-01-01") & (universe.year > 2022)
    universe = universe.loc[~invalid]
    target = build_historical_province_target(universe)
    observed = target.loc[target.firm_key.eq("SSE:000000:2010-01-01"), "year"].tolist()
    assert observed == [2020, 2021, 2022]
    assert target.duplicated(["firm_key", "year"]).sum() == 0


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("北京", "北京市"), ("沪", "上海市"), ("粤", "广东省"),
        ("内蒙古", "内蒙古自治区"), ("新疆", "新疆维吾尔自治区"),
        ("浙江省", "浙江省"),
    ],
)
def test_normalize_province_aliases(raw, expected):
    assert normalize_province(raw) == expected


@pytest.mark.parametrize(
    ("address", "expected"),
    [
        ("上海市浦东新区世纪大道", "上海市"),
        ("深圳市南山区科技园", "广东省"),
        ("苏州市工业园区", "江苏省"),
        ("武汉市洪山区", "湖北省"),
        ("浙江省衢州市凯旋南路", "浙江省"),
        ("中国北京海淀区西直门北大街", "北京市"),
        ("中国（上海）自由贸易试验区浦东大道", "上海市"),
        ("湛江市东海岛东海大道", "广东省"),
        ("龙岩市新罗区铁山镇", "福建省"),
    ],
)
def test_address_normalization_uses_explicit_municipality_and_city_maps(address, expected):
    assert province_from_address(address) == expected


def test_unknown_address_is_not_guessed():
    assert province_from_address("星河新区未来路一号") is None
    assert province_from_address(None) is None


def test_static_current_profile_cannot_become_historical_confirmed():
    result = classify_static_profile("广东省", year=2020)
    assert result["province_historical"] is None
    assert result["historical_status"] == "static_fallback_only"


def test_effective_date_inference_respects_fiscal_year_boundary():
    events = [
        {"old_province": "北京市", "new_province": "四川省", "effective_date": "2021-05-25"}
    ]
    before = infer_province_for_year(events, 2020)
    during = infer_province_for_year(events, 2021)
    after = infer_province_for_year(events, 2022)
    assert (before["province"], before["historical_status"]) == ("北京市", "historical_inferred")
    assert (during["province"], during["historical_status"]) == ("四川省", "historical_inferred")
    assert after["province"] == "四川省"


def test_same_year_event_after_year_end_does_not_rewrite_that_year():
    events = [
        {"old_province": "辽宁省", "new_province": "北京市", "effective_date": "2024-01-15"}
    ]
    assert infer_province_for_year(events, 2023)["province"] == "辽宁省"
    assert infer_province_for_year(events, 2024)["province"] == "北京市"


def test_inference_without_effective_date_is_missing():
    result = infer_province_for_year([{"old_province": "上海市", "new_province": "山东省"}], 2021)
    assert result["province"] is None
    assert result["historical_status"] == "missing"


def test_conflict_candidates_are_preserved_and_same_tier_unresolved():
    candidates = [
        {"province": "北京市", "source_tier": "H1", "source_id": "a"},
        {"province": "四川省", "source_tier": "H1", "source_id": "b"},
    ]
    preferred, conflict = choose_preferred_candidate(candidates)
    assert preferred is None
    assert conflict is True
    assert HISTORICAL_STATUSES == {
        "historical_confirmed", "historical_inferred", "static_fallback_only", "missing"
    }


def test_higher_tier_selects_preferred_without_discarding_conflict():
    candidates = [
        {"province": "北京市", "source_tier": "H1", "source_id": "annual"},
        {"province": "河北省", "source_tier": "S", "source_id": "profile"},
    ]
    preferred, conflict = choose_preferred_candidate(candidates)
    assert preferred["source_id"] == "annual"
    assert conflict is True


def test_pilot_is_deterministic_unique_and_keeps_strata_separate():
    universe = _universe()
    base = universe.drop_duplicates("firm_key")
    sample = select_historical_province_pilot(base, seed="20260925")
    again = select_historical_province_pilot(base.sample(frac=1, random_state=7), seed="20260925")
    pd.testing.assert_frame_equal(sample, again)
    assert sample.firm_key.is_unique
    assert sample.pilot_stratum.notna().all()


def test_chunk_manifest_is_stable_sorted_and_limited_to_chunk_size():
    firms = pd.DataFrame({"firm_key": [f"SSE:{i:06d}:2000-01-01" for i in range(205)]})
    first = assign_historical_province_chunks(firms, chunk_size=100)
    second = assign_historical_province_chunks(firms.sample(frac=1, random_state=8), chunk_size=100)
    assert first == second
    assert [len(members) for members in first.values()] == [100, 100, 5]
    assert sum(map(len, first.values())) == 205


def test_policy_geography_audit_uses_only_primary_historical_provinces():
    panel = pd.DataFrame([
        {"firm_key": "SSE:000001:2000-01-01", "year": 2020,
         "province_historical": "北京市", "province_status": "historical_confirmed"},
        {"firm_key": "SSE:000001:2000-01-01", "year": 2021,
         "province_historical": None, "province_status": "static_fallback_only"},
        {"firm_key": "SSE:000002:2000-01-01", "year": 2020,
         "province_historical": "浙江省", "province_status": "historical_inferred"},
    ])
    result = build_policy_geography_coverage(panel, ["北京市"])
    assert result.set_index("province").loc["北京市", "firms"] == 1
    assert result.set_index("province").loc["北京市", "existing_policy_corpus_available"]
    assert not result.set_index("province").loc["浙江省", "existing_policy_corpus_available"]


def test_source_response_detects_access_blocks_without_retrying():
    with pytest.raises(SourceBlocked):
        classify_source_response(403, "blocked")
    with pytest.raises(SourceBlocked):
        classify_source_response(200, "请完成验证码后继续")
    assert classify_source_response(200, '{"announcements": []}') == "ok"


def test_annual_report_address_field_does_not_confuse_history_or_office_address():
    text = """
注册地址           北京市海淀区海淀南路 21 号四层
注册地址的邮政编码      100080
公司注册地址历史变更情况   2024年11月18日完成由江苏省苏州市迁至北京市海淀区
办公地址           江苏省苏州市苏站路 1588 号
"""
    assert extract_registered_address(text) == "北京市海淀区海淀南路21号四层"


def test_report_history_field_and_effective_event_extraction():
    text = """
公司注册地址历史变更情况
公司于2024年11月18日完成注册地址由“江苏省苏州市吴中区”变更为“北京市海淀区海淀南路21号”。
"""
    history = extract_registered_address_history(text)
    assert history is not None
    events = parse_address_change_events(history)
    assert events == [
        {
            "effective_date": "2024-11-18",
            "old_address": "江苏省苏州市吴中区",
            "new_address": "北京市海淀区海淀南路21号",
        }
    ]


def test_registration_change_completion_date_wins_over_meeting_dates():
    history = (
        "公司于2024年10月28日、11月13日审议迁址议案，注册地址由"
        "江苏省苏州市吴中区变更为北京市海淀区，并于2024年11月18日完成工商变更登记。"
    )
    events = parse_address_change_events(history)
    assert len(events) == 1
    assert events[0]["effective_date"] == "2024-11-18"


def test_history_extraction_spans_wrapped_lines_until_next_profile_field():
    text = """
公司注册地址历史变更情况  2023年4月，公司完成登记，注册地址由广东省珠海市
变更为浙江省衢州市。具体见公司公告。
办公地址  深圳市福田区
"""
    history = extract_registered_address_history(text)
    assert history is not None
    assert "广东省珠海市" in history
    assert "办公地址" not in history
    event = parse_address_change_events(history)[0]
    assert event["effective_date"] == "2023-04-01"


def test_history_label_without_situation_word_is_supported():
    text = """
公司注册地址历史变更 公司住所由北京市海淀区地锦路9号院6号楼
迁址到四川省宜宾市叙州区金润产业园9栋
"""
    history = extract_registered_address_history(text)
    assert history is not None
    assert "北京市海淀区" in history
    assert parse_address_change_events(history) == []


def test_event_addresses_normalize_leading_quotes_and_city_only_origin():
    history = (
        "2023年4月公司注册地址由“珠海市高新区唐家湾镇”变更为"
        "“浙江省衢州市凯旋南路6号”，并于2023年4月完成登记。"
    )
    event = parse_address_change_events(history)[0]
    assert event["old_address"] == "珠海市高新区唐家湾镇"
    assert province_from_address(event["old_address"]) == "广东省"
    assert province_from_address(event["new_address"]) == "浙江省"


def test_firm_cache_checkpoints_each_year_and_resumes_without_refetch(tmp_path):
    firm = {"firm_key": "SSE:600000:1999-11-10", "stock_code_current": "600000"}

    class StubClient(CNINFOAnnualReportClient):
        fail_year = None

        def __init__(self, cache_dir, fail_year=None):
            super().__init__(cache_dir, request_spacing=1.0, sleep=lambda _: None)
            self.fail_year = fail_year
            self.list_calls = 0
            self.downloaded = []

        def list_annual_reports(self, stock_code, start_date="2020-01-01", end_date=None):
            self.list_calls += 1
            return [
                {
                    "report_year": year,
                    "source_url": str(year),
                    "source_type": "official_annual_report",
                    "source_tier": "H1",
                    "announcement_id": str(year),
                    "announcement_time": 1_650_000_000_000,
                }
                for year in (2020, 2021)
            ]

        def extract_pdf_text(self, source_url):
            self.downloaded.append(source_url)
            if self.fail_year and int(source_url) == self.fail_year:
                raise TimeoutError("interrupted download")
            return "注册地址 北京市海淀区知春路1号\n"

    first = StubClient(tmp_path, fail_year=2021)
    with pytest.raises(TimeoutError):
        first.fetch_firm_reports(firm, years=range(2020, 2022))
    cache_file = next(tmp_path.glob("*.json"))
    cache = __import__("json").loads(cache_file.read_text(encoding="utf-8"))
    assert cache["cache_format_version"] == CACHE_FORMAT_VERSION
    assert [row["source_report_year"] for row in cache["records"]] == [2020]

    resumed = StubClient(tmp_path)
    records = resumed.fetch_firm_reports(firm, years=range(2020, 2022))
    assert [row["source_report_year"] for row in records] == [2020, 2021]
    assert resumed.downloaded == ["2021"]

    cached = StubClient(tmp_path)
    assert cached.fetch_firm_reports(firm, years=range(2020, 2022)) == records
    assert cached.list_calls == 0


def test_firm_cache_retries_transient_windows_replace_permission_error(tmp_path, monkeypatch):
    firm = {"firm_key": "SSE:600000:1999-11-10", "stock_code_current": "600000"}

    class StubClient(CNINFOAnnualReportClient):
        def __init__(self):
            super().__init__(tmp_path, request_spacing=1.0, sleep=lambda _: None)

        def list_annual_reports(self, stock_code, start_date="2020-01-01", end_date=None):
            return []

    original_replace = Path.replace
    attempts = {"count": 0}

    def transient_lock_once(path, target):
        if str(path).endswith(".tmp") and str(target).endswith(".json"):
            attempts["count"] += 1
            if attempts["count"] == 1:
                raise PermissionError("temporary Windows file lock")
        return original_replace(path, target)

    monkeypatch.setattr(Path, "replace", transient_lock_once)
    client = StubClient()
    records = client.fetch_firm_reports(firm, years=range(2020, 2021))

    assert records[0]["missing_reason"] == "annual_report_not_found"
    assert attempts["count"] == 2
    assert len(list(tmp_path.glob("*.json"))) == 1


def test_stata_export_converts_all_missing_object_columns_to_empty_strings(tmp_path):
    panel = pd.DataFrame({
        "firm_key": ["SSE:600000:1999-11-10", "SSE:600001:1999-11-10"],
        "historical_stock_code": [None, None],
        "province_static_agrees": [True, None],
        "province_source_temporal_adjusted": [False, False],
    })

    result = _prepare_stata_export(panel)

    assert "province_source_temporal_adjusted" not in result
    assert result["historical_stock_code"].tolist() == ["", ""]
    assert result.loc[0, "province_static_agrees"] == 1.0
    assert pd.isna(result.loc[1, "province_static_agrees"])
    assert pd.isna(panel.loc[0, "historical_stock_code"])
    output = tmp_path / "historical_province.dta"
    result.to_stata(output, write_index=False, version=118)
    assert output.is_file()
    exported = pd.read_stata(output)
    assert exported["province_static_agrees"].tolist()[0] == 1
    assert pd.isna(exported["province_static_agrees"].tolist()[1])


def test_stale_firm_cache_version_is_refetched(tmp_path):
    firm = {"firm_key": "SSE:600000:1999-11-10", "stock_code_current": "600000"}
    path = tmp_path / "SSE_600000_1999-11-10.json"
    path.write_text('{"records": []}', encoding="utf-8")

    class StubClient(CNINFOAnnualReportClient):
        def __init__(self):
            super().__init__(tmp_path, request_spacing=1.0, sleep=lambda _: None)
            self.list_calls = 0

        def list_annual_reports(self, stock_code, start_date="2020-01-01", end_date=None):
            self.list_calls += 1
            return []

    client = StubClient()
    result = client.fetch_firm_reports(firm, years=range(2020, 2021))
    assert client.list_calls == 1
    assert result[0]["missing_reason"] == "annual_report_not_found"


def test_resolver_preserves_target_keys_and_keeps_unverified_province_missing():
    target = pd.DataFrame([
        {"firm_key": "SSE:600000:2000-01-01", "year": 2020, "exchange": "SSE",
         "province_profile": "广东省", "current_status": "current"},
        {"firm_key": "SSE:600000:2000-01-01", "year": 2021, "exchange": "SSE",
         "province_profile": "广东省", "current_status": "current"},
    ])
    records = [{
        "firm_key": "SSE:600000:2000-01-01", "source_report_year": 2020,
        "province_raw": "四川省成都市高新区", "source_tier": "H1",
        "source_name": "official annual report", "source_url_or_id": "report-2020",
    }]
    panel, conflicts = resolve_historical_province_panel(target, records)
    assert list(zip(panel.firm_key, panel.year)) == list(zip(target.firm_key, target.year))
    assert panel.loc[0, "province_historical"] == "四川省"
    assert panel.loc[0, "province_status"] == "historical_confirmed"
    assert pd.isna(panel.loc[1, "province_historical"])
    assert panel.loc[1, "province_status"] == "static_fallback_only"
    assert conflicts.empty


def test_resolver_corrects_snapshot_using_later_effective_dated_move():
    target = pd.DataFrame([
        {"firm_key": "SSE:600715:1996-07-01", "year": 2023, "exchange": "SSE",
         "current_status": "current"},
        {"firm_key": "SSE:600715:1996-07-01", "year": 2024, "exchange": "SSE",
         "current_status": "current"},
    ])
    records = [
        {"firm_key": "SSE:600715:1996-07-01", "source_report_year": 2023,
         "province_raw": "北京市朝阳区", "source_tier": "H1", "source_url_or_id": "report-2023",
         "registered_address_history_raw": (
             "2024年1月1日完成注册地址由辽宁省沈阳市变更为北京市朝阳区"
         )},
        {"firm_key": "SSE:600715:1996-07-01", "source_report_year": 2024,
         "province_raw": "北京市朝阳区", "source_tier": "H1", "source_url_or_id": "report-2024",
         "registered_address_history_raw": (
             "2024年1月1日完成注册地址由辽宁省沈阳市变更为北京市朝阳区"
         )},
    ]
    panel, _ = resolve_historical_province_panel(target, records)
    assert panel.province_historical.tolist() == ["辽宁省", "北京市"]
    assert panel.province_status.tolist() == ["historical_inferred", "historical_inferred"]
    assert panel.province_source_temporal_adjusted.tolist() == [True, False]


def test_resolver_keeps_same_tier_conflicting_snapshots_unresolved():
    target = pd.DataFrame([
        {"firm_key": "SZSE:000001:1991-01-01", "year": 2020, "exchange": "SZSE",
         "current_status": "current"},
    ])
    records = [
        {"firm_key": "SZSE:000001:1991-01-01", "source_report_year": 2020,
         "province_raw": "北京市海淀区", "source_tier": "H1", "source_url_or_id": "a"},
        {"firm_key": "SZSE:000001:1991-01-01", "source_report_year": 2020,
         "province_raw": "四川省成都市", "source_tier": "H1", "source_url_or_id": "b"},
    ]
    panel, conflicts = resolve_historical_province_panel(target, records)
    assert panel.loc[0, "province_status"] == "missing"
    assert panel.loc[0, "province_conflict"]
    assert set(conflicts.candidate_province) == {"北京市", "四川省"}


def test_pilot_gate_uses_current_exchange_coverage_and_semantic_audit():
    target = pd.DataFrame([
        {"firm_key": f"SSE:{i:06d}:2000-01-01", "year": 2020, "exchange": "SSE",
         "current_status": "current", "province_status": "historical_confirmed",
         "province_conflict": False}
        for i in range(10)
    ] + [
        {"firm_key": f"SZSE:{i:06d}:2000-01-01", "year": 2020, "exchange": "SZSE",
         "current_status": "current", "province_status": "historical_inferred",
         "province_conflict": False}
        for i in range(10)
    ])
    status, gate = evaluate_historical_province_pilot_gate(target, change_cases_verified=5)
    coverage = summarize_historical_province_coverage(target).set_index("stratum")
    assert status == "HISTORICAL_PROVINCE_PILOT_PASS"
    assert gate["SSE_current_coverage"] == 1.0
    assert gate["SZSE_current_coverage"] == 1.0
    assert coverage.loc["all", "firm_years"] == 20


def test_full_coverage_derives_recent_ipo_subgroups_from_listing_date():
    panel = pd.DataFrame([
        {"firm_key": "SSE:600001:2018-01-01", "year": 2022, "exchange": "SSE",
         "current_status": "current", "market_listing_date": "2018-01-01",
         "province_status": "historical_confirmed", "province_conflict": False},
        {"firm_key": "SSE:688001:2021-01-01", "year": 2022, "exchange": "SSE",
         "current_status": "current", "market_listing_date": "2021-01-01",
         "province_status": "historical_inferred", "province_conflict": False},
        {"firm_key": "SZSE:300001:2020-01-01", "year": 2022, "exchange": "SZSE",
         "current_status": "current", "market_listing_date": "2020-01-01",
         "province_status": "static_fallback_only", "province_conflict": False},
    ])

    coverage = summarize_historical_province_coverage(panel).set_index("stratum")

    assert coverage.loc["SSE_recent_IPO", "firms"] == 1
    assert coverage.loc["SSE_recent_IPO", "firm_years"] == 1
    assert coverage.loc["SSE_current", "firms"] == 2
    assert coverage.loc["SZSE_recent_IPO", "historical_coverage"] == 0.0
