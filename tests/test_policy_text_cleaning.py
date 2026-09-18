from pathlib import Path

from src.policy_text_cleaning import (
    clean_html,
    decode_bytes,
    extract_industry_text,
    normalize_text,
    quality_flags,
    split_paragraphs,
)


def test_unicode_and_duplicate_whitespace():
    assert normalize_text("ＡＢＣ  \n\n  创新\t能力") == "ABC\n创新 能力"


def test_paragraph_splitting_and_keyword_rules():
    text = "支持人才引进。\n\n推进技术创新和制造业升级。"
    paragraphs = split_paragraphs(text)
    industry, core_hits, context_hits, total_hits, count = extract_industry_text(
        text, ["创新", "制造业"], ["人才"]
    )
    assert paragraphs == ["支持人才引进。", "推进技术创新和制造业升级。"]
    assert industry == "推进技术创新和制造业升级。"
    assert (core_hits, context_hits, total_hits, count) == (2, 1, 3, 1)


def test_context_only_is_excluded_and_mixed_is_included():
    industry, *_ = extract_industry_text("人才引进。\n\n人才与创新协同。", ["创新"], ["人才"])
    assert industry == "人才与创新协同。"


def test_decode_and_malformed_html():
    text, encoding, status = decode_bytes("政府工作报告".encode("gb18030"), "")
    assert text == "政府工作报告"
    assert encoding == "gb18030"
    assert status == "ok"
    cleaned, _, _ = clean_html("<html><script>x</script><p>报告正文</p></html>".encode())
    assert cleaned == "报告正文"


def test_quality_flags_and_empty_input():
    assert "empty_full_text" in quality_flags("", "", 0, "ok")
    assert "empty_industry_text" in quality_flags("short", "", 0, "warning")


def test_raw_fixture_is_not_mutated(tmp_path: Path):
    raw = tmp_path / "report.html"
    raw.write_bytes("<p>2020 政府工作报告</p>".encode())
    before = raw.read_bytes()
    clean_html(before)
    assert raw.read_bytes() == before
