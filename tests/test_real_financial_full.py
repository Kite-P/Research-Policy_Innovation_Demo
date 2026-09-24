import json

import pandas as pd
import pytest

from scripts.finalize_phase_a_financial_panel import validate_panel_scope, validate_phase_a_complete
from scripts.run_cross_exchange_canary import write_canary_meta
from src.build_real_financial_panel import SourceBlocked
from src.real_financial_full import (
    assemble_full_financial_panel,
    assign_chunks,
    atomic_write_json,
    build_full_financial_target,
    classify_data_status,
    manifest_fingerprint,
    run_full_fetch,
    select_cross_exchange_canary,
    universe_fingerprint,
    upsert_firm_status,
)


def _universe():
    return pd.DataFrame(
        {
            "firm_key": ["SSE:1:2020-01-01"] * 2 + ["BSE:2:2021-11-15"] * 2 + ["SSE:3:2020-01-01"],
            "exchange": ["SSE", "SSE", "BSE", "BSE", "SSE"],
            "stock_code_current": ["000001", "000001", "920002", "920002", "000003"],
            "company_name_legal": ["A", "A", "B", "B", "F"],
            "market_listing_date": pd.to_datetime(
                ["2020-01-01", "2020-01-01", "2021-11-15", "2021-11-15", "2020-01-01"]
            ),
            "listing_date": pd.to_datetime(
                ["2020-01-01", "2020-01-01", "2021-11-15", "2021-11-15", "2020-01-01"]
            ),
            "delisting_date": [pd.NaT] * 5,
            "industry_csrc": ["制造业"] * 4 + ["金融业-银行"],
            "industry_known": [True] * 5,
            "is_financial_industry": [False, False, False, False, True],
            "year": [2020, 2021, 2021, 2022, 2020],
        }
    )


def _cross_manifest():
    base = _universe().iloc[[0]].copy()
    rows = []
    for exchange, prefix in (("SSE", "1"), ("SZSE", "2")):
        for index in range(100):
            row = base.copy()
            row["firm_key"] = f"{exchange}:{prefix}{index:05d}:2020-01-01"
            row["exchange"] = exchange
            row["stock_code_current"] = f"{index + 1:06d}"
            rows.append(row)
    return assign_chunks(build_full_financial_target(pd.concat(rows, ignore_index=True)))


def test_full_target_excludes_financial_firms_from_fetch():
    target = build_full_financial_target(_universe())
    assert target.loc[target["firm_key"].eq("SSE:3:2020-01-01"), "fetch_scope"].iloc[0] == (
        "excluded_financial"
    )
    assert (
        not target.loc[target["fetch_phase"].eq("sse_szse_nonfinancial"), "firm_key"]
        .eq("SSE:3:2020-01-01")
        .any()
    )


def test_full_target_retains_delisted_for_attempt():
    universe = _universe()
    universe.loc[1, "delisting_date"] = pd.Timestamp("2021-06-01")
    target = build_full_financial_target(universe)
    count = target.loc[target["firm_key"].eq("SSE:1:2020-01-01"), "valid_firm_year_count"].iloc[0]
    assert count == 2


def test_bse_is_pending_phase():
    target = build_full_financial_target(_universe())
    row = target.loc[target["exchange"].eq("BSE")].iloc[0]
    assert row["fetch_phase"] == "bse_nonfinancial_pending_mapping"
    assert not row["formal_ready"]
    assert row["bse_mapping_status"] == "BSE_MAPPING_REQUIRED"


def test_manifest_is_deterministic():
    a = build_full_financial_target(_universe())
    b = build_full_financial_target(_universe().sample(frac=1, random_state=7))
    pd.testing.assert_frame_equal(a, b)


def test_universe_fingerprint_is_stable():
    a = universe_fingerprint(_universe())
    b = universe_fingerprint(_universe().sample(frac=1, random_state=3))
    assert a == b


def test_chunk_assignment_is_deterministic():
    target = build_full_financial_target(_universe())
    a = assign_chunks(target, chunk_size=1)
    b = assign_chunks(target.sample(frac=1, random_state=4), chunk_size=1)
    pd.testing.assert_frame_equal(a, b)


def test_stale_cache_is_refetched(monkeypatch, tmp_path):
    universe = _universe().iloc[:2].copy()
    target = build_full_financial_target(universe)
    cache = tmp_path / "cache"
    cache.mkdir()
    stale = pd.DataFrame({"firm_key": [universe.loc[0, "firm_key"]], "year": [2020]})
    stale.to_parquet(cache / "SSE_1_2020-01-01.parquet", index=False)
    calls = {"n": 0}

    def fake_fetch(exchange, current, query, firm_key, valid_years):
        calls["n"] += 1
        return pd.DataFrame(
            {
                "exchange": [exchange] * len(valid_years),
                "firm_key": [firm_key] * len(valid_years),
                "stock_code_current": [current] * len(valid_years),
                "year": list(valid_years),
                "financial_query_code": [query] * len(valid_years),
                "total_assets": [1.0] * len(valid_years),
                "total_liabilities": [1.0] * len(valid_years),
                "cash": [1.0] * len(valid_years),
                "revenue": [1.0] * len(valid_years),
                "net_profit": [1.0] * len(valid_years),
                "rd_expense": [1.0] * len(valid_years),
                "employees": [1.0] * len(valid_years),
                "financial_success": [True] * len(valid_years),
                "failure_reason": [""] * len(valid_years),
            }
        )

    monkeypatch.setattr("src.real_financial_full.fetch_company_with_fallback", fake_fetch)
    run_full_fetch(universe, target, cache, "SSE-SZSE-A-0001", spacing=1, max_firms=1)
    assert calls["n"] == 1


def test_resume_only_fetches_missing_firms(monkeypatch, tmp_path):
    universe = _universe().iloc[:2].copy()
    target = build_full_financial_target(universe)
    calls = {"n": 0}

    def fake_fetch(exchange, current, query, firm_key, valid_years):
        calls["n"] += 1
        return pd.DataFrame(
            {
                "exchange": [exchange] * len(valid_years),
                "firm_key": [firm_key] * len(valid_years),
                "stock_code_current": [current] * len(valid_years),
                "year": list(valid_years),
                "financial_query_code": [query] * len(valid_years),
                "total_assets": [1.0] * len(valid_years),
                "total_liabilities": [1.0] * len(valid_years),
                "cash": [1.0] * len(valid_years),
                "revenue": [1.0] * len(valid_years),
                "net_profit": [1.0] * len(valid_years),
                "rd_expense": [1.0] * len(valid_years),
                "employees": [1.0] * len(valid_years),
                "financial_success": [True] * len(valid_years),
                "failure_reason": [""] * len(valid_years),
            }
        )

    monkeypatch.setattr("src.real_financial_full.fetch_company_with_fallback", fake_fetch)
    run_full_fetch(universe, target, tmp_path / "cache", "SSE-SZSE-A-0001", spacing=1)
    first = calls["n"]
    run_full_fetch(universe, target, tmp_path / "cache", "SSE-SZSE-A-0001", spacing=1)
    assert first == 1
    assert calls["n"] == first


def test_source_blocked_stops_run(monkeypatch, tmp_path):
    universe = _universe().iloc[:1].copy()
    target = build_full_financial_target(universe)

    def blocked(*args, **kwargs):
        raise SourceBlocked("HTTP 429")

    monkeypatch.setattr("src.real_financial_full.fetch_company_with_fallback", blocked)
    with pytest.raises(SourceBlocked):
        run_full_fetch(universe, target, tmp_path / "cache", "SSE-SZSE-A-0001", spacing=1)


def test_state_write_is_atomic(tmp_path):
    path = tmp_path / "run_state.json"
    atomic_write_json(path, {"ok": True})
    assert json.loads(path.read_text()) == {"ok": True}
    assert not path.with_suffix(".tmp").exists()


def test_fingerprint_mismatch_stops(tmp_path):
    universe = _universe().iloc[:2].copy()
    target = build_full_financial_target(universe)
    with pytest.raises(ValueError, match="UNIVERSE_FINGERPRINT_MISMATCH"):
        run_full_fetch(
            universe,
            target,
            tmp_path / "cache",
            "SSE-SZSE-A-0001",
            spacing=1,
            state_path=tmp_path / "state.json",
            expected_fingerprint="different",
        )


def test_canary_contains_no_financial_firms():
    target = build_full_financial_target(_universe())
    canary = assign_chunks(target, chunk_size=200)
    assert not canary.loc[canary["formal_ready"], "is_financial_industry"].any()


def test_canary_contains_only_sse_szse():
    target = build_full_financial_target(_universe())
    canary = assign_chunks(target, chunk_size=200)
    assert set(canary.loc[canary["formal_ready"], "exchange"]) <= {"SSE", "SZSE"}


def test_assemble_panel_preserves_target_keys(tmp_path):
    universe = _universe().iloc[:2].copy()
    target = build_full_financial_target(universe)
    panel = assemble_full_financial_panel(universe, tmp_path / "cache", target)
    expected = set(map(tuple, universe[["firm_key", "year"]].to_numpy()))
    actual = set(map(tuple, panel[["firm_key", "year"]].to_numpy()))
    assert actual == expected


def test_failed_cache_is_cache_hit_but_query_failed(tmp_path):
    frame = pd.DataFrame({"financial_success": [False, False]})
    assert classify_data_status(frame) == "QUERY_FAILED"


def test_manifest_fingerprint_uses_stable_manifest_fields():
    target = assign_chunks(build_full_financial_target(_universe()), chunk_size=2)
    shuffled = target.sample(frac=1, random_state=9)
    assert manifest_fingerprint(target) == manifest_fingerprint(shuffled)


def test_status_upsert_preserves_manifest_order_and_latest_row():
    target = assign_chunks(build_full_financial_target(_universe()), chunk_size=2)
    old = pd.DataFrame([{"firm_key": "SSE:1:2020-01-01", "data_status": "QUERY_FAILED"}])
    new = pd.DataFrame([
        {"firm_key": "SSE:3:2020-01-01", "data_status": "COMPLETE"},
        {"firm_key": "SSE:1:2020-01-01", "data_status": "PARTIAL"},
    ])
    result = upsert_firm_status(old, new, target)
    expected_order = target["firm_key"].drop_duplicates().loc[
        target["firm_key"].drop_duplicates().isin(result["firm_key"])
    ].tolist()
    assert result["firm_key"].tolist() == expected_order
    assert result.loc[result["firm_key"].eq("SSE:1:2020-01-01"), "data_status"].iloc[0] == "PARTIAL"


def test_chunk_selection_is_ordered_by_chunk_before_position():
    target = assign_chunks(build_full_financial_target(_universe()), chunk_size=1)
    phase_a = target.loc[target["formal_ready"]].copy()
    ordered = phase_a.sort_values(["chunk_id", "chunk_position", "firm_key"])
    assert ordered["chunk_id"].tolist() == sorted(ordered["chunk_id"].tolist())


def test_partial_is_not_counted_as_success():
    frame = pd.DataFrame({"financial_success": [True, False]})
    assert classify_data_status(frame) == "PARTIAL"


def test_legacy_partial_status_migrates_correctly():
    target = assign_chunks(build_full_financial_target(_universe()), chunk_size=1)
    old = pd.DataFrame([{
        "firm_key": "SSE:1:2020-01-01", "status": "PARTIAL",
        "complete_firm_years": 1, "failed_firm_years": 1,
    }])
    result = upsert_firm_status(old, pd.DataFrame(), target)
    assert result.iloc[0]["retrieval_status"] == "FETCHED"
    assert result.iloc[0]["data_status"] == "PARTIAL"


def test_legacy_query_failed_status_migrates_correctly():
    target = assign_chunks(build_full_financial_target(_universe()), chunk_size=1)
    old = pd.DataFrame([{
        "firm_key": "SSE:1:2020-01-01", "status": "QUERY_FAILED",
        "complete_firm_years": 0, "failed_firm_years": 2,
    }])
    result = upsert_firm_status(old, pd.DataFrame(), target)
    assert result.iloc[0]["retrieval_status"] == "FETCHED"
    assert result.iloc[0]["data_status"] == "QUERY_FAILED"


def test_partial_processing_does_not_complete_chunk():
    universe = _universe().iloc[[0]].copy()
    extra = universe.copy()
    extra["firm_key"] = "SSE:2:2020-01-01"
    extra["stock_code_current"] = "000002"
    target = assign_chunks(build_full_financial_target(pd.concat([universe, extra])), chunk_size=2)
    statuses = pd.DataFrame([{
        "firm_key": target.loc[target.formal_ready, "firm_key"].iloc[0],
        "retrieval_status": "FETCHED", "data_status": "PARTIAL",
    }])
    chunk_is_complete = __import__(
        "src.real_financial_full", fromlist=["chunk_is_complete"]
    ).chunk_is_complete
    assert not chunk_is_complete(
        target.loc[target.formal_ready, "chunk_id"].iloc[0], target, statuses
    )


def test_source_blocked_preserves_rows_processed_earlier_in_same_run(monkeypatch, tmp_path):
    base = _universe().iloc[[0]].copy()
    second = base.copy()
    second["firm_key"] = "SSE:2:2020-01-01"
    second["stock_code_current"] = "000002"
    third = base.copy()
    third["firm_key"] = "SSE:4:2020-01-01"
    third["stock_code_current"] = "000004"
    universe = pd.concat([base, second, third], ignore_index=True)
    target = assign_chunks(build_full_financial_target(universe), chunk_size=100)
    calls = {"n": 0}

    def fake_fetch(exchange, current, query, firm_key, valid_years):
        calls["n"] += 1
        if calls["n"] == 3:
            raise SourceBlocked("HTTP 429")
        years = valid_years
        return pd.DataFrame({
            "exchange": [exchange] * len(years), "firm_key": [firm_key] * len(years),
            "stock_code_current": ["000001"] * len(years), "year": list(years),
            "financial_query_code": ["000001"] * len(years),
            **{field: [1.0] * len(years) for field in (
                "total_assets", "total_liabilities", "cash", "revenue", "net_profit",
                "rd_expense", "employees")},
            "financial_success": [True] * len(years), "failure_reason": [""] * len(years),
        })

    monkeypatch.setattr("src.real_financial_full.fetch_company_with_fallback", fake_fetch)
    status_path = tmp_path / "firm_status.csv"
    with pytest.raises(SourceBlocked):
        run_full_fetch(
            universe,
            target,
            tmp_path / "cache",
            "SSE-SZSE-A-0001",
            state_path=tmp_path / "state.json",
            status_path=status_path,
            spacing=1,
        )
    statuses = pd.read_csv(status_path)
    assert set(statuses["firm_key"]) == {
        "SSE:1:2020-01-01", "SSE:2:2020-01-01", "SSE:4:2020-01-01"
    }
    assert statuses.loc[
        statuses["firm_key"].eq("SSE:1:2020-01-01"), "data_status"
    ].iloc[0] == "COMPLETE"


def test_cross_exchange_canary_has_100_sse_100_szse():
    selected = select_cross_exchange_canary(_cross_manifest())
    assert selected["exchange"].value_counts().to_dict() == {"SSE": 100, "SZSE": 100}


def test_cross_exchange_canary_uses_complete_chunks():
    selected = select_cross_exchange_canary(_cross_manifest())
    assert selected.groupby(["chunk_id", "exchange"]).size().eq(100).all()


def test_cross_exchange_canary_is_deterministic():
    target = _cross_manifest()
    assert select_cross_exchange_canary(target).equals(
        select_cross_exchange_canary(target.sample(frac=1))
    )


def test_finalizer_refuses_incomplete_phase_a():
    manifest = _cross_manifest()
    statuses = pd.DataFrame([{
        "firm_key": manifest.loc[manifest.formal_ready, "firm_key"].iloc[0],
        "retrieval_status": "FETCHED", "data_status": "COMPLETE",
    }])
    with pytest.raises(RuntimeError, match="PHASE_A_NOT_COMPLETE"):
        validate_phase_a_complete(manifest, statuses)


def test_finalizer_refuses_source_blocked_phase_a():
    manifest = _cross_manifest()
    statuses = manifest.loc[manifest.formal_ready, ["firm_key", "chunk_id"]].copy()
    statuses["retrieval_status"] = "FETCHED"
    statuses["data_status"] = "COMPLETE"
    statuses.loc[0, "retrieval_status"] = "SOURCE_BLOCKED"
    with pytest.raises(RuntimeError, match="PHASE_A_NOT_COMPLETE"):
        validate_phase_a_complete(manifest, statuses)


def test_finalizer_allows_terminal_complete_phase_a():
    manifest = _cross_manifest()
    statuses = manifest.loc[manifest.formal_ready, ["firm_key", "chunk_id"]].copy()
    statuses["retrieval_status"] = "FETCHED"
    statuses["data_status"] = "QUERY_FAILED"
    validate_phase_a_complete(manifest, statuses)


def test_finalizer_compares_exact_firm_year_keys():
    universe = _universe().iloc[[0]].copy()
    manifest = assign_chunks(build_full_financial_target(universe))
    target = manifest.loc[manifest.formal_ready]
    panel = universe.assign(
        industry_known=True, is_financial_industry=False,
        financial_success=True, total_assets=1.0,
    ).iloc[0:0]
    with pytest.raises(RuntimeError, match="PHASE_A_PANEL_KEY_MISMATCH"):
        validate_panel_scope(panel, universe, target)


def test_finalizer_refuses_financial_firm():
    universe = _universe().iloc[[0]].copy()
    manifest = assign_chunks(build_full_financial_target(universe))
    panel = universe.assign(industry_known=True, is_financial_industry=True)
    with pytest.raises(RuntimeError, match="PHASE_A_PANEL_SCOPE_MISMATCH"):
        validate_panel_scope(panel, universe, manifest.loc[manifest.formal_ready])


def test_finalizer_refuses_unknown_industry():
    universe = _universe().iloc[[0]].copy()
    manifest = assign_chunks(build_full_financial_target(universe))
    panel = universe.assign(industry_known=False, is_financial_industry=False)
    with pytest.raises(RuntimeError, match="PHASE_A_PANEL_SCOPE_MISMATCH"):
        validate_panel_scope(panel, universe, manifest.loc[manifest.formal_ready])


def test_canary_meta_does_not_overwrite_run_state(tmp_path):
    from src.real_financial_full import atomic_write_json

    state_path = tmp_path / "state.json"
    state = {"universe_fingerprint": "u", "manifest_fingerprint": "m", "completed_chunks": ["x"]}
    atomic_write_json(state_path, state)
    write_canary_meta(tmp_path / "meta.json", 1, "CROSS_EXCHANGE_CANARY_FIRST_PASS")
    assert __import__("json").loads(state_path.read_text(encoding="utf-8")) == state


def test_second_canary_resume_keeps_fingerprints(tmp_path):
    from src.real_financial_full import atomic_write_json

    state_path = tmp_path / "state.json"
    atomic_write_json(state_path, {"universe_fingerprint": "u", "manifest_fingerprint": "m"})
    write_canary_meta(tmp_path / "meta.json", 2, "CROSS_EXCHANGE_CANARY_READY")
    state = __import__("json").loads(state_path.read_text(encoding="utf-8"))
    assert state["universe_fingerprint"] == "u"
    assert state["manifest_fingerprint"] == "m"
