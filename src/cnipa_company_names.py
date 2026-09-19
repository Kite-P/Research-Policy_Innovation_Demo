from __future__ import annotations

from collections.abc import Iterable


def normalize_company_name(value: object) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    return " ".join(text.split())


def normalize_company_names(values: Iterable[object]) -> list[str]:
    names = {name for value in values if (name := normalize_company_name(value))}
    return sorted(names, key=lambda name: name.encode("utf-8"))
