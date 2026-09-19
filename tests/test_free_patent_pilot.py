from src.free_patent_pilot import (
    build_company_patent_query,
    build_patent_freshness_query,
    build_patent_schema_query,
    normalize_company_name,
)


def test_query_builders_use_current_publications_table():
    assert "patents-public-data.patents.publications" in build_patent_freshness_query()
    assert "COLUMN_FIELD_PATHS" in build_patent_schema_query()


def test_company_query_uses_exact_name_matching_and_year_filter():
    query = build_company_patent_query(["甲 乙股份有限公司"])
    assert "filing_date BETWEEN 20220101 AND 20241231" in query
    assert "NORMALIZE(assignee" in query
    assert "fuzzy" not in query.lower()
    assert "LIKE" not in query


def test_company_name_normalization_is_not_fuzzy():
    assert normalize_company_name(" 甲　乙股份有限公司 ") == "甲乙股份有限公司"
