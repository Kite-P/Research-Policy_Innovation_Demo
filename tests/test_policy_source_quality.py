import pandas as pd

from src.policy_source_quality import classify_source, enrich_manifest


def test_source_tier_is_explicit_and_reasoned():
    tier, label, reason = classify_source("hubei_2022", "http://hb.china.com.cn/report")
    assert tier == 4
    assert label == "other_complete_reprint"
    assert len(reason) > 20


def test_official_provincial_sources_get_tier_one():
    tier, label, _ = classify_source(
        "heilongjiang_2019", "https://www.hlj.gov.cn/hlj/szfgzbg/201901/report.shtml"
    )
    assert tier == 1
    assert label == "direct_provincial_official"


def test_other_government_and_state_media_domains_are_classified():
    tier_two = classify_source("hainan_2025", "https://fg.sanya.gov.cn/report.html")
    tier_three = classify_source("qinghai_2025", "https://qh.people.com.cn/report.html")
    assert tier_two[:2] == (2, "other_government_official")
    assert tier_three[:2] == (3, "official_or_state_media_reprint")


def test_reliable_nonofficial_full_report_domains_are_explicit_tier_four():
    tier, label, _ = classify_source(
        "hainan_2019", "https://www.gcs66.com/document_detail/8511.html"
    )
    assert tier == 4
    assert label == "other_complete_reprint"
    hainan_tier = classify_source(
        "hainan_2024", "https://news.hainan.net/hainan/full-report.html"
    )
    assert hainan_tier[:2] == (4, "other_complete_reprint")
    qinghai_tier = classify_source(
        "qinghai_2024", "https://www.eesia.cn/upload/files/2024/2/report.pdf"
    )
    assert qinghai_tier[:2] == (4, "other_complete_reprint")
    sina_tier = classify_source(
        "anhui_2025",
        "https://finance.sina.com.cn/jjxw/2025-01-26/report.shtml",
    )
    assert sina_tier[:2] == (4, "other_complete_reprint")


def test_jianpincn_and_tianjin_government_report_tiers():
    third_party = classify_source(
        "qinghai_2023",
        "https://www.jianpincn.com/zgjpsjk/zcwj/dfzc/qh/672953.html",
    )
    direct = classify_source(
        "tianjin_2025", "https://www.tj.gov.cn/zwgk/zfgzbg/report.html"
    )
    hunan = classify_source(
        "hunan_2019", "https://www.hunan.gov.cn/hnszf/szf/zfgzbg/report.html"
    )
    xinjiang = classify_source(
        "xinjiang_2019", "https://www.xinjiang.gov.cn/xinjiang/report.html"
    )
    guangxi = classify_source(
        "guangxi_2020",
        "https://byte.gxnews.com.cn/www.gxzf.gov.cn/zwgk/gzbg/report.html",
    )
    guangxi_new = [
        classify_source(
            f"guangxi_{year}",
            f"https://byte.gxnews.com.cn/www.gxzf.gov.cn/report-{year}.html",
        )
        for year in (2023, 2024, 2025)
    ]
    assert third_party[:2] == (4, "other_complete_reprint")
    assert direct[:2] == (1, "direct_provincial_official")
    assert hunan[:2] == (1, "direct_provincial_official")
    assert xinjiang[:2] == (1, "direct_provincial_official")
    assert guangxi[:2] == (1, "direct_provincial_official")
    assert all(item[:2] == (1, "direct_provincial_official") for item in guangxi_new)


def test_guangxi_tier_one_requires_official_mirror_host():
    official_mirror = classify_source(
        "guangxi_2023",
        "https://byte.gxnews.com.cn/www.gxzf.gov.cn/zwgk/gzbg/report.html",
    )
    third_party_pdf = classify_source(
        "guangxi_2025",
        "https://www.zgoog.com/uploadfile/2025/report.pdf",
    )
    assert official_mirror[:2] == (1, "direct_provincial_official")
    assert third_party_pdf[:2] == (4, "other_complete_reprint")


def test_new_reprint_domains_keep_report_tiers_conservative():
    anhui_media = classify_source(
        "anhui_2023", "https://www.ahnews.com.cn/anhui/pc/con/report.html"
    )
    independent_reprints = [
        classify_source("guangxi_2024", "https://www.0797cx.cn/zc?article_id=112806"),
        classify_source("hebei_2023", "https://www.yjysbg.com/1904.html"),
        classify_source(
            "qinghai_2021", "https://www.ccement.com/news/content/report.html"
        ),
    ]
    assert anhui_media[:2] == (3, "official_or_state_media_reprint")
    assert all(item[:2] == (4, "other_complete_reprint") for item in independent_reprints)


def test_manifest_rows_without_discovered_source_remain_unclassified():
    result = enrich_manifest(
        pd.DataFrame(
            {
                "policy_id": ["anhui_2019"],
                "source_url": [""],
                "notes": ["source not discovered"],
            }
        )
    )
    assert pd.isna(result.loc[0, "source_tier"])
    assert pd.isna(result.loc[0, "source_tier_verified"])


def test_enrich_manifest_separates_historical_fetch_issue():
    manifest = pd.DataFrame(
        {
            "policy_id": ["beijing_2019"],
            "source_url": ["https://www.beijing.gov.cn/report"],
            "source_domain": ["beijing.gov.cn"],
            "retrieval_status": ["success"],
            "notes": ["fetch_error=PermissionError"],
        }
    )
    result = enrich_manifest(manifest)
    assert result.loc[0, "source_tier"] == 1
    assert result.loc[0, "source_tier_verified"] == 1
    assert result.loc[0, "retrieval_history_note"] == "fetch_error=PermissionError"
    assert "fetch_error" not in str(result.loc[0, "notes"])
