from __future__ import annotations

import hashlib
from pathlib import Path

import pandas as pd
import pytest

from src.cnipa_strict14_replay import (
    build_complete_row_predictions,
    build_event_roster,
    build_source_manifest,
    fetch_h1_sources,
    find_local_reusable_source,
    score_events,
    score_strict_rows,
    strict14_keys,
    validate_h1_document,
    verify_ground_truth_fingerprints,
)
from src.historical_province_sources import SourceBlocked


def _row_gt(n: int = 14) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "firm_key": [f"SZSE:{i:06d}:2000-01-01" for i in range(1, n + 1)],
            "year": [2020] * n,
            "review_legal_name_at_year_end": [f"Issuer {i} Co., Ltd." for i in range(1, n + 1)],
            "review_change_flag": ["UNKNOWN"] * n,
            "review_status": ["PASS"] * n,
        }
    )


def _evidence_gt(row_gt: pd.DataFrame | None = None) -> pd.DataFrame:
    source = row_gt if row_gt is not None else _row_gt()
    return source[["firm_key", "year"]].assign(review_expected_parser_flag="UNKNOWN")


def _manifest_row(index: int = 1, **overrides: object) -> dict[str, object]:
    record: dict[str, object] = {
        "firm_key": f"SZSE:{index:06d}:2000-01-01",
        "year": 2020,
        "stock_code": f"{index:06d}",
        "source_report_title": "Issuer 2020年年度报告全文",
        "source_url": f"https://static.cninfo.com.cn/finalpage/2021-04-01/{index:010d}.PDF",
        "source_announcement_id": f"{index:010d}",
        "source_tier": "H1",
        "source_is_official": True,
    }
    record.update(overrides)
    return record


def test_strict14_key_set_is_exact_and_matches_evidence_keys():
    keys, fingerprint = strict14_keys(_row_gt(), _evidence_gt())
    assert len(keys) == 14
    assert len(set(keys)) == 14
    assert len(fingerprint) == 64
    assert fingerprint == strict14_keys(_row_gt(), _evidence_gt())[1]


def test_strict14_key_loader_rejects_duplicate_row_keys():
    rows = pd.concat([_row_gt(), _row_gt().iloc[[0]]], ignore_index=True)
    with pytest.raises(ValueError, match="DUPLICATE_STRICT14_KEY|STRICT14_ROW_COUNT_MISMATCH"):
        strict14_keys(rows, _evidence_gt())


def test_strict14_key_loader_rejects_evidence_key_set_drift():
    evidence = _evidence_gt().iloc[:-1].copy()
    with pytest.raises(ValueError, match="STRICT14_EVIDENCE_KEY_SET_MISMATCH"):
        strict14_keys(_row_gt(), evidence)


def test_source_manifest_requires_exact_firm_year_provenance():
    rows = _row_gt().iloc[:1][["firm_key", "year"]]
    status = pd.DataFrame([_manifest_row(1)])
    manifest = build_source_manifest(rows.itertuples(index=False, name=None), [status])
    assert manifest[0]["source_url"] == _manifest_row(1)["source_url"]
    with pytest.raises(ValueError, match="STRICT14_SOURCE_PROVENANCE_MISSING"):
        build_source_manifest(rows.itertuples(index=False, name=None), [status.iloc[0:0]])


def test_source_manifest_rejects_non_official_or_non_pdf_urls():
    rows = _row_gt().iloc[:1][["firm_key", "year"]]
    bad = pd.DataFrame([_manifest_row(1, source_url="https://example.com/report.pdf")])
    with pytest.raises(ValueError, match="NON_OFFICIAL_H1_SOURCE_URL"):
        build_source_manifest(rows.itertuples(index=False, name=None), [bad])


def test_source_manifest_rejects_index_search_urls():
    rows = _row_gt().iloc[:1][["firm_key", "year"]]
    bad = pd.DataFrame(
        [_manifest_row(1, source_url="https://www.cninfo.com.cn/new/hisAnnouncement/query")]
    )
    with pytest.raises(ValueError, match="NON_DIRECT_H1_PDF_URL"):
        build_source_manifest(rows.itertuples(index=False, name=None), [bad])


def test_local_exact_source_is_reused_without_network(tmp_path: Path):
    record = _manifest_row()
    pdf_path, text_path = tmp_path / "p.pdf", tmp_path / "p.txt"
    pdf_path.write_bytes(b"%PDF-" + b"x" * 2048)
    text_path.write_text("annual report", encoding="utf-8")
    local = {
        "firm_key": record["firm_key"],
        "year": 2020,
        "source_url": record["source_url"],
        "pdf_path": str(pdf_path),
        "text_path": str(text_path),
        "pdf_sha256": hashlib.sha256(pdf_path.read_bytes()).hexdigest(),
        "text_sha256": hashlib.sha256(text_path.read_bytes()).hexdigest(),
        "source_is_official": True,
    }
    assert find_local_reusable_source(record, [local]) == {
        **local,
        "text_sha256": local["text_sha256"],
    }


def test_local_source_with_wrong_url_is_not_reused():
    record = _manifest_row()
    local = {
        "firm_key": record["firm_key"],
        "year": 2020,
        "source_url": "https://static.cninfo.com.cn/other.PDF",
        "pdf_path": "p.pdf",
        "text_path": "p.txt",
        "pdf_sha256": "a" * 64,
    }
    assert find_local_reusable_source(record, [local]) is None


def test_h1_document_rejects_annual_report_summary():
    record = _manifest_row(source_report_title="Issuer 2020年年度报告摘要")
    result = validate_h1_document(
        record, b"%PDF-" + b"x" * 2048, "股票代码：000001\n2020年年度报告摘要"
    )
    assert result["valid"] is False
    assert result["reason"] == "ANNUAL_REPORT_SUMMARY_REJECTED"


def test_h1_document_rejects_wrong_year():
    record = _manifest_row(source_report_title="Issuer 2019年年度报告全文")
    result = validate_h1_document(
        record, b"%PDF-" + b"x" * 2048, "股票代码：000001\n2019年年度报告全文"
    )
    assert result["reason"] == "REPORT_YEAR_MISMATCH"


def test_h1_document_rejects_wrong_issuer_stock_code():
    record = _manifest_row()
    result = validate_h1_document(
        record, b"%PDF-" + b"x" * 2048, "股票代码：000002\n2020年年度报告全文"
    )
    assert result["reason"] == "WRONG_ISSUER_STOCK_CODE"


def test_h1_document_accepts_exact_year_issuer_and_full_report():
    record = _manifest_row()
    text = "Issuer 2020年年度报告全文\n2020年年度报告\n证券代码：000001\n" + "正文内容\n" * 30
    result = validate_h1_document(record, b"%PDF-" + b"x" * 2048, text)
    assert result["valid"] is True


def test_h1_fetch_is_capped_at_fourteen_unique_gets(tmp_path: Path):
    records = [_manifest_row(i) for i in range(1, 16)]
    calls: list[str] = []

    def fetcher(url: str) -> dict[str, object]:
        calls.append(url)
        code = url.rsplit("/", 1)[1].split(".")[0][-6:]
        return {
            "http_status": 200,
            "pdf_bytes": b"%PDF-" + b"x" * 2048,
            "text": "2020年年度报告\n证券代码：" + code + "\n" + "正文内容\n" * 30,
        }

    result = fetch_h1_sources(records, fetcher, tmp_path, max_gets=14)
    assert len(calls) == 14
    assert result["h1_get_count"] == 14
    assert result["stopped_reason"] == "H1_GET_CAP_REACHED"


def test_source_block_stops_all_later_exact_h1_gets(tmp_path: Path):
    records = [_manifest_row(1), _manifest_row(2), _manifest_row(3)]
    calls: list[str] = []

    def fetcher(url: str) -> dict[str, object]:
        calls.append(url)
        if len(calls) == 2:
            raise SourceBlocked("HTTP_403")
        code = url.rsplit("/", 1)[1].split(".")[0][-6:]
        return {
            "http_status": 200,
            "pdf_bytes": b"%PDF-" + b"x" * 2048,
            "text": "2020年年度报告\n证券代码：" + code + "\n" + "正文内容\n" * 30,
        }

    result = fetch_h1_sources(records, fetcher, tmp_path, max_gets=14)
    assert len(calls) == 2
    assert result["source_block_count"] == 1
    assert result["stopped_reason"] == "SOURCE_BLOCKED"


def test_h1_fetch_rejects_h2_records_before_network(tmp_path: Path):
    record = _manifest_row(source_tier="H2")
    calls: list[str] = []
    with pytest.raises(ValueError, match="H2_NOT_ALLOWED_IN_H1_REPLAY"):
        fetch_h1_sources([record], lambda url: calls.append(url), tmp_path)
    assert calls == []


def test_verified_local_h1_is_preferred_over_network(tmp_path: Path):
    pdf_path, text_path = tmp_path / "issuer.pdf", tmp_path / "issuer.txt"
    pdf_path.write_bytes(b"%PDF-" + b"x" * 2048)
    text_path.write_text("2020年年度报告\n证券代码：000001\n" + "正文\n" * 30, encoding="utf-8")
    record = _manifest_row()
    local = {
        "firm_key": record["firm_key"],
        "year": 2020,
        "source_url": record["source_url"],
        "pdf_path": str(pdf_path),
        "text_path": str(text_path),
        "pdf_sha256": hashlib.sha256(pdf_path.read_bytes()).hexdigest(),
        "text_sha256": hashlib.sha256(text_path.read_bytes()).hexdigest(),
        "source_is_official": True,
    }
    calls: list[str] = []
    result = fetch_h1_sources(
        [record], lambda url: calls.append(url), tmp_path, local_records=[local]
    )
    assert calls == []
    assert result["local_reused_count"] == 1


def test_candidate_subset_cannot_shrink_frozen_row_prediction_denominator():
    keys, _ = strict14_keys(_row_gt(), _evidence_gt())
    partial = pd.DataFrame(
        [
            {
                "firm_key": keys[0][0],
                "year": keys[0][1],
                "parser_change_flag": "UNKNOWN",
                "parser_legal_name_at_year_end": "Issuer 1 Co., Ltd.",
            }
        ]
    )
    complete = build_complete_row_predictions(keys, partial)
    assert len(complete) == 14
    assert set(zip(complete.firm_key, complete.year)) == set(keys)


def test_row_predictions_never_copy_review_fields_from_ground_truth():
    keys, _ = strict14_keys(_row_gt(), _evidence_gt())
    parsed = pd.DataFrame(
        [
            {
                "firm_key": keys[0][0],
                "year": 2020,
                "parser_change_flag": "UNKNOWN",
                "parser_legal_name_at_year_end": "Predicted Name",
                "review_legal_name_at_year_end": "GT Name",
            }
        ]
    )
    predictions = build_complete_row_predictions(keys, parsed)
    assert "review_legal_name_at_year_end" not in predictions.columns
    assert (
        predictions.loc[predictions.firm_key.eq(keys[0][0]), "parser_legal_name_at_year_end"].item()
        == "Predicted Name"
    )


def test_strict_row_evidence_accuracy_uses_all_fourteen_frozen_keys():
    rows = _row_gt()
    evidence = _evidence_gt(rows)
    predictions = rows[["firm_key", "year"]].assign(
        parser_change_flag="UNKNOWN",
        parser_legal_name_at_year_end=rows.review_legal_name_at_year_end,
    )
    scores = score_strict_rows(predictions, rows, evidence)
    assert scores["evidence_state_denominator"] == 14
    assert scores["evidence_state_correct"] == 14


def test_strict_row_year_end_accuracy_uses_all_fourteen_frozen_keys():
    rows = _row_gt()
    predictions = rows[["firm_key", "year"]].assign(
        parser_change_flag="UNKNOWN",
        parser_legal_name_at_year_end=rows.review_legal_name_at_year_end,
    )
    scores = score_strict_rows(predictions, rows, _evidence_gt(rows))
    assert scores["year_end_denominator"] == 14
    assert scores["year_end_correct"] == 14


def test_event_roster_is_built_from_predictions_not_event_ground_truth():
    row = {
        "firm_key": "SZSE:000001:2000-01-01",
        "year": 2020,
        "parser_change_flag": "YES",
        "parser_previous_name": "Old Issuer Co., Ltd.",
        "parser_new_name": "New Issuer Co., Ltd.",
        "parser_effective_date": "2020-06-01",
        "parser_date_precision": "exact_date",
        "change_evidence_tier": "H1",
        "change_evidence_url": "https://static.cninfo.com.cn/finalpage/2021-01-01/0000000001.PDF",
        "source_announcement_id": "",
    }
    events = build_event_roster(pd.DataFrame([row]), [])
    assert len(events) == 1
    assert events.iloc[0].parser_previous_legal_name == "Old Issuer Co., Ltd."
    assert events.iloc[0].parser_new_legal_name == "New Issuer Co., Ltd."


def test_h2_carry_forward_requires_resolved_source_url_id_and_hash():
    row = {
        "firm_key": "SZSE:000001:2000-01-01",
        "year": 2020,
        "status": "RESOLVED_H2",
        "notice_url": "https://static.cninfo.com.cn/finalpage/2021-01-01/0000000001.PDF",
        "announcement_id": "0000000001",
        "notice_pdf_sha256": hashlib.sha256(b"h2").hexdigest(),
        "notice_pdf_bytes": 1000,
        "previous_legal_name": "Old Issuer Co., Ltd.",
        "new_legal_name": "New Issuer Co., Ltd.",
        "change_effective_date": "2020-06-01",
        "date_precision": "exact_date",
    }
    assert len(build_event_roster(pd.DataFrame(), [row])) == 1
    row["status"] = "PENDING"
    assert build_event_roster(pd.DataFrame(), [row]).empty


def test_six_event_metrics_are_scored_against_all_six_frozen_events():
    gt = pd.DataFrame(
        [
            {
                "event_id": f"E{i}",
                "review_previous_legal_name": f"Old{i}",
                "review_new_legal_name": f"New{i}",
                "review_effective_date": "2020-06-01",
                "review_date_precision": "exact_date",
                "review_status": "PASS",
            }
            for i in range(6)
        ]
    )
    pred = gt.iloc[:5].rename(
        columns={
            "review_previous_legal_name": "parser_previous_legal_name",
            "review_new_legal_name": "parser_new_legal_name",
            "review_effective_date": "parser_effective_date",
            "review_date_precision": "parser_date_precision",
        }
    )[
        [
            "event_id",
            "parser_previous_legal_name",
            "parser_new_legal_name",
            "parser_effective_date",
            "parser_date_precision",
        ]
    ]
    scores = score_events(pred, gt)
    assert scores["event_denominator"] == 6
    assert scores["event_old_correct"] == 5
    assert scores["unresolved_event_count"] == 1


def test_frozen_gt_fingerprints_match_historical_binding():
    row_gt = _row_gt()
    event_gt = pd.DataFrame([{"event_id": "E1"}])
    evidence_gt = _evidence_gt(row_gt)
    binding = {
        "row_ground_truth_fingerprint": "x",
        "event_ground_truth_fingerprint": "y",
        "evidence_state_ground_truth_fingerprint": "z",
    }
    with pytest.raises(ValueError, match="FROZEN_GT_FINGERPRINT_MISMATCH"):
        verify_ground_truth_fingerprints(row_gt, event_gt, evidence_gt, binding)


def test_frozen45_parser_regression_remains_45_of_45_when_local_corpus_exists():
    from scripts.replay_cnipa_strict14_v3 import _run_frozen45

    result = _run_frozen45()
    assert result["denominator"] == 45
    assert result["issuer_correct"] == 45
    assert result["year_end_correct"] == 45
    assert result["evidence_state_correct"] == 45
    assert result["prior_correct25_denominator"] == 25
    assert result["prior_correct25_regressions"] == 0


def test_real_frozen_strict14_key_fingerprint_and_gt_files_are_unchanged():
    root = Path(__file__).resolve().parents[1]
    base = root / "results/cnipa_legal_name_recovery"
    row_gt = pd.read_csv(
        base / "pilot_change_row_ground_truth.csv", dtype={"firm_key": str}, keep_default_na=False
    )
    evidence_gt = pd.read_csv(
        base / "pilot_change_evidence_state_ground_truth.csv",
        dtype={"firm_key": str},
        keep_default_na=False,
    )
    keys, fingerprint = strict14_keys(row_gt, evidence_gt)
    assert len(keys) == 14
    assert fingerprint == "9a5dcbf6099c43b41711518d5dd5772d2d9eb20346e98fe632d5be178161bee1"
    assert (
        hashlib.sha256((base / "pilot_change_row_ground_truth.csv").read_bytes()).hexdigest()
        == "81eb18d82611ce7bddf7d9895ed57237026b9b5d97b0dd258dda7d0ba266d342"
    )
    assert (
        hashlib.sha256((base / "pilot_change_event_ground_truth.csv").read_bytes()).hexdigest()
        == "e1900a01fff61610e1325623ec59870d9063a14c6925e4075639855745d5e174"
    )


def test_wide_resume_remains_blocked():
    root = Path(__file__).resolve().parents[1]
    source = (root / "scripts/run_cninfo_legal_name_recovery_20260929.py").read_text(
        encoding="utf-8"
    )
    assert "FULL_WIDE_REPARSE_BLOCKED" in source
