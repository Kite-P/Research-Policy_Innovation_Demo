from src.cnipa_patent_queries import build_applicant_query, split_company_queries


def test_build_applicant_query_is_exact_and_deterministic():
    assert build_applicant_query(["  甲股份有限公司", "乙有限公司", "甲股份有限公司"]) == (
        "乙有限公司 OR 甲股份有限公司"
    )


def test_split_company_queries_respects_count_and_character_limits():
    names = ["甲有限公司", "乙有限公司", "丙有限公司", "丁有限公司"]
    batches = split_company_queries(names, max_names=2, max_chars=15)
    assert batches == [["丁有限公司", "丙有限公司"], ["乙有限公司", "甲有限公司"]]
    assert all(len(batch) <= 2 for batch in batches)
    assert all(len(build_applicant_query(batch)) <= 15 for batch in batches)


def test_split_company_queries_rejects_invalid_limits():
    try:
        split_company_queries(["甲有限公司"], max_names=0, max_chars=100)
    except ValueError as exc:
        assert "positive" in str(exc)
    else:
        raise AssertionError("expected ValueError")
