import subprocess
import sys
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
GENERATOR = PROJECT_ROOT / "src" / "generate_training_data.py"


def has_non_ascii(series):
    values = series.dropna().astype(str)

    return values.map(
        lambda value: any(ord(char) > 127 for char in value)
    ).any()


def contains_question_mark(series):
    return (
        series.dropna()
        .astype(str)
        .str.contains(r"\?", regex=True)
        .any()
    )


def test_training_data_generator_creates_valid_files(tmp_path):
    result = subprocess.run(
        [
            sys.executable,
            str(GENERATOR),
            "--output-dir",
            str(tmp_path),
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr

    financials_path = tmp_path / "firm_financials.xlsx"
    profile_path = tmp_path / "firm_profile.csv"
    patents_path = tmp_path / "patents.csv"

    assert financials_path.exists()
    assert profile_path.exists()
    assert patents_path.exists()

    financials = pd.read_excel(financials_path)
    profile = pd.read_csv(profile_path, encoding="utf-8-sig")
    patents = pd.read_csv(patents_path, encoding="utf-8-sig")

    assert financials.shape == (260, 11)
    assert profile.shape == (42, 7)
    assert patents.shape == (225, 5)

    assert financials.columns.tolist() == [
        "stock_code",
        "company_name",
        "year",
        "total_assets",
        "total_liabilities",
        "revenue",
        "net_profit",
        "cash",
        "rd_expense",
        "roe",
        "employees",
    ]

    assert profile.columns.tolist() == [
        "stock_code",
        "company_name",
        "province",
        "city",
        "industry",
        "ownership",
        "listing_date",
    ]

    assert patents.columns.tolist() == [
        "stock_code",
        "year",
        "invention_patents",
        "utility_patents",
        "patent_citations",
    ]

    assert has_non_ascii(financials["company_name"])

    for column in [
        "company_name",
        "province",
        "city",
        "industry",
        "ownership",
    ]:
        assert has_non_ascii(profile[column])
        assert not contains_question_mark(profile[column])

    assert not contains_question_mark(financials["company_name"])

    year_text = financials["year"].dropna().astype(str)
    assert year_text.map(
        lambda value: any(ord(char) > 127 for char in value)
    ).any()

def test_training_data_contains_intentional_dirty_cases(tmp_path):
    result = subprocess.run(
        [
            sys.executable,
            str(GENERATOR),
            "--output-dir",
            str(tmp_path),
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr

    financials = pd.read_excel(
        tmp_path / "firm_financials.xlsx",
        dtype=object,
    )
    profile = pd.read_csv(
        tmp_path / "firm_profile.csv",
        encoding="utf-8-sig",
        dtype=str,
        keep_default_na=False,
    )
    patents = pd.read_csv(
        tmp_path / "patents.csv",
        encoding="utf-8-sig",
        dtype=str,
        keep_default_na=False,
    )

    # 1. 年份格式混杂，例如 2023 和 2023年
    assert financials["year"].astype(str).str.endswith("年").any()

    # 2. 公司名称存在空格、ST、*ST、简称等不一致问题
    company_names = financials["company_name"].astype(str)

    assert company_names.str.startswith(" ").any()
    assert company_names.str.endswith(" ").any()
    assert company_names.str.startswith("ST").any()
    assert company_names.str.startswith("*ST").any()

    # 3. 数值字段中存在字符串型脏值
    assert financials["total_assets"].astype(str).str.contains(",", regex=False).any()
    assert (financials["total_liabilities"].astype(str) == "-").any()
    assert financials["revenue"].astype(str).str.contains(",", regex=False).any()
    assert (financials["rd_expense"].astype(str) == "-").any()

    # 4. ROE 同时存在比例字符串和普通数值
    assert financials["roe"].astype(str).str.contains("%", regex=False).any()

    # 5. 财务表存在完全重复行
    assert financials.duplicated().sum() >= 10

    # 6. 企业属性表存在省份命名不统一
    province_values = set(profile["province"])

    assert "广东" in province_values
    assert "广东省" in province_values
    assert "浙江" in province_values
    assert "浙江省" in province_values

    # 7. 企业属性表存在产权性质缺失
    assert (profile["ownership"] == "").any()

    # 8. 专利数据存在缺失和异常值
    assert (patents["invention_patents"] == "").any()
    assert (patents["utility_patents"] == "").any()
    assert (patents["patent_citations"] == "").any()
    citation_values = pd.to_numeric(
        patents["patent_citations"],
        errors="coerce",
    )

    assert citation_values.eq(99_999).any()

    # 9. 专利表存在重复 firm-year
    assert patents.duplicated(
        subset=["stock_code", "year"],
        keep=False,
    ).any()
