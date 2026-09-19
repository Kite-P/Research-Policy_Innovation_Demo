import csv
import re
from pathlib import Path

ROOT = Path(__file__).parents[1]
SCOPE_PATH = ROOT / "metadata" / "real_data_scope.csv"
SCHEMA_PATH = ROOT / "metadata" / "real_data_schema.csv"


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def test_primary_patent_end_year_is_frozen_at_2024():
    rows = {row["item"]: row for row in read_csv(SCOPE_PATH)}
    assert rows["primary_patent_end_year"]["value"] == "2024"
    assert rows["primary_patent_end_year"]["status"] == "frozen"


def test_required_profile_fields_exist():
    required = {
        "stock_code",
        "company_name",
        "year",
        "exchange",
        "listing_date",
        "province",
        "industry_code",
        "industry_name",
    }
    fields = {
        row["field_name"]
        for row in read_csv(SCHEMA_PATH)
        if row["dataset"] == "profile" and row["required"] == "yes"
    }
    assert required <= fields


def test_nonblocking_st_and_rd_fields_are_optional():
    rows = {
        row["field_name"]: row
        for row in read_csv(SCHEMA_PATH)
        if row["dataset"] == "profile"
    }
    assert rows["st_flag"]["required"] == "no"
    assert rows["st_flag"]["availability"] == "unavailable_free_source"
    financial = {
        row["field_name"]: row
        for row in read_csv(SCHEMA_PATH)
        if row["dataset"] == "financial"
    }
    assert financial["rd_expense"]["required"] == "no"
    assert financial["rd_expense"]["availability"] == "partial"


def test_patent_source_and_entity_scope_are_cnipa_listed_entity_only():
    rows = {
        row["field_name"]: row
        for row in read_csv(SCHEMA_PATH)
        if row["dataset"] == "patent"
    }
    assert rows["patent_source"]["preferred_source"] == "CNIPA official patent data"
    assert rows["patent_entity_scope"]["definition"] == "listed_entity_only"


def test_required_financial_fields_exist():
    required = {
        "stock_code",
        "year",
        "total_assets",
        "total_liabilities",
        "revenue",
        "net_profit",
        "cash",
        "employees",
    }
    fields = {
        row["field_name"]
        for row in read_csv(SCHEMA_PATH)
        if row["dataset"] == "financial" and row["required"] == "yes"
    }
    assert required <= fields


def test_required_patent_fields_exist():
    required = {
        "stock_code",
        "year",
        "invention_patents",
        "utility_patents",
        "patent_total",
    }
    fields = {
        row["field_name"]
        for row in read_csv(SCHEMA_PATH)
        if row["dataset"] == "patent" and row["required"] == "yes"
    }
    assert required <= fields


def test_dataset_and_field_name_are_unique():
    rows = read_csv(SCHEMA_PATH)
    keys = [(row["dataset"], row["field_name"]) for row in rows]
    assert len(keys) == len(set(keys))


def test_public_metadata_has_no_credentials_or_absolute_windows_paths():
    text = "\n".join(path.read_text(encoding="utf-8") for path in (SCOPE_PATH, SCHEMA_PATH))
    assert not re.search(r"(?i)(password|token|cookie|secret)\s*[:=]", text)
    assert not re.search(r"[A-Za-z]:\\\\", text)
