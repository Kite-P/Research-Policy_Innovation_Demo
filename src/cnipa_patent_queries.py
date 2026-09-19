from __future__ import annotations

from .cnipa_company_names import normalize_company_names


def build_applicant_query(names: list[str]) -> str:
    normalized = normalize_company_names(names)
    return " OR ".join(normalized)


def split_company_queries(
    names: list[str], max_names: int, max_chars: int
) -> list[list[str]]:
    if max_names <= 0 or max_chars <= 0:
        raise ValueError("max_names and max_chars must be positive")
    normalized = normalize_company_names(names)
    batches: list[list[str]] = []
    current: list[str] = []
    for name in normalized:
        candidate = current + [name]
        if current and (
            len(candidate) > max_names
            or len(build_applicant_query(candidate)) > max_chars
        ):
            batches.append(current)
            current = [name]
        elif not current and len(build_applicant_query(candidate)) > max_chars:
            raise ValueError(f"company name exceeds max_chars: {name!r}")
        else:
            current = candidate
    if current:
        batches.append(current)
    return batches
