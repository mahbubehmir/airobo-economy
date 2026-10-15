"""Small typed records shared by collectors, database, and reporting."""
from __future__ import annotations
from dataclasses import dataclass

@dataclass(frozen=True)
class PriceRecord:
    source_id: str
    product_key: str
    product_name: str
    size_mm: int
    standard: str
    manufacturer: str
    price_toman_per_kg: int
    market_date: str           # ISO Gregorian date used for calculations
    market_date_label: str     # date string as seen on source, if available
    date_basis: str            # "source" or "collection"
    record_type: str           # "archive" or "snapshot"
    source_url: str
    raw_text: str
    source_sequence: int = 0

@dataclass
class SourceResult:
    source_id: str
    source_url: str
    records: list[PriceRecord]
    note: str = ""

@dataclass
class SourceFailure:
    source_id: str
    source_url: str
    error: str
