from __future__ import annotations

import re
import unicodedata

PATENT_TABLE = "`patents-public-data.patents.publications`"


def normalize_company_name(value: object) -> str:
    text = unicodedata.normalize("NFKC", str(value or ""))
    return re.sub(r"\s+", "", text)


def build_patent_schema_query() -> str:
    return """SELECT
  column_name,
  field_path,
  data_type
FROM
  `patents-public-data.patents.INFORMATION_SCHEMA.COLUMN_FIELD_PATHS`
WHERE
  table_name = 'publications'
ORDER BY
  field_path"""


def build_patent_freshness_query() -> str:
    return f"""SELECT
  MAX(filing_date) AS max_filing_date,
  COUNTIF(filing_date BETWEEN 20220101 AND 20221231) AS n_2022,
  COUNTIF(filing_date BETWEEN 20230101 AND 20231231) AS n_2023,
  COUNTIF(filing_date BETWEEN 20240101 AND 20241231) AS n_2024,
  COUNTIF(filing_date BETWEEN 20250101 AND 20251231) AS n_2025
FROM
  {PATENT_TABLE}
WHERE
  country_code = 'CN'"""


def _sql_string(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def build_company_patent_query(company_names: list[str]) -> str:
    if not company_names:
        raise ValueError("company_names must not be empty")
    literals = ", ".join(_sql_string(normalize_company_name(name)) for name in company_names)
    return f"""SELECT DISTINCT
  company_name AS query_company_name,
  COALESCE(harmonized.name, raw_assignee) AS matched_assignee,
  p.publication_number,
  p.application_number,
  p.filing_date,
  p.publication_date,
  p.kind_code,
  p.country_code
FROM
  {PATENT_TABLE} AS p
LEFT JOIN
  UNNEST(p.assignee) AS raw_assignee
LEFT JOIN
  UNNEST(p.assignee_harmonized) AS harmonized
CROSS JOIN
  UNNEST([{literals}]) AS company_name
WHERE
  p.country_code = 'CN'
  AND p.filing_date BETWEEN 20220101 AND 20241231
  AND (
    NORMALIZE(raw_assignee, NFKC) = company_name
    OR NORMALIZE(harmonized.name, NFKC) = company_name
  )"""
