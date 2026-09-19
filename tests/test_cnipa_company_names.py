from src.cnipa_company_names import normalize_company_name, normalize_company_names


def test_normalize_company_name_does_not_create_aliases():
    assert normalize_company_name("  甲股份有限公司  ") == "甲股份有限公司"
    assert normalize_company_name(None) == ""


def test_normalize_company_names_is_unique_and_sorted():
    assert normalize_company_names(["乙有限公司", "甲有限公司", "乙有限公司"]) == [
        "乙有限公司",
        "甲有限公司",
    ]
