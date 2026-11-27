from __future__ import annotations

import re
from typing import Optional


def normalize_product_code(value: str) -> str:
    """Return the comparison key for supplier product codes.

    Product identity is case-insensitive and ignores whitespace, while the
    original stored/display code is preserved for auditability.
    Examples: ``BE-HLS7050`` == ``BE-HLS 7050`` == ``be-hls7050``.
    """
    return re.sub(r"\s+", "", (value or "").strip()).upper()


def normalize_unit_code(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    unit = value.strip().upper()
    if not unit:
        return None
    if unit in {"C62", "PZ"}:
        return "PZ"
    return unit


def normalize_customer_name(value: str | None) -> str:
    """Normalize customer display names by removing supplier numeric/punctuation prefixes.

    Examples: ``924 - Azienda Ospedaliera Papardo`` ->
    ``Azienda Ospedaliera Papardo`` and ``--- Azienda Ospedaliera Papardo`` ->
    ``Azienda Ospedaliera Papardo``. Internal punctuation and the actual name
    are preserved.
    """
    if value is None:
        return ""
    name = re.sub(r"\s+", " ", value.strip())
    # Ignore only a leading code made of digits/spaces/dots/underscores/hyphens
    # when it is followed by a separator or whitespace before the actual name.
    name = re.sub(r"^\s*[\d._-]+\s*(?:[-:|]\s*)?", "", name)
    return re.sub(r"\s+", " ", name).strip(" -")


def normalize_vat_number(value: str | None) -> str:
    """Canonical VAT comparison key: ignore country prefix IT and whitespace/punctuation."""
    raw = re.sub(r"[^A-Z0-9]", "", (value or "").upper())
    if raw.startswith("IT"):
        raw = raw[2:]
    return raw
