"""Parsing helpers for Persian market pages. No sample prices are created here."""
from __future__ import annotations
import re
import unicodedata
from datetime import date
from typing import Optional
from datetime import date

_DIGIT_MAP = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")
_TRANSLATE_MAP = str.maketrans({"ي": "ی", "ك": "ک", "ۀ": "ه", "ة": "ه", "ـ": ""})
_DATE_RE = re.compile(r"(?<!\d)(\d{4})\s*[/\-.]\s*(\d{1,2})\s*[/\-.]\s*(\d{1,2})(?!\d)")


def normalize_text(value: object) -> str:
    text = unicodedata.normalize("NFKC", str(value or "")).translate(_DIGIT_MAP).translate(_TRANSLATE_MAP)
    text = text.replace("\u200c", " ").replace("\xa0", " ")
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def parse_jalali_date(text: str) -> Optional[tuple[str, str]]:
    """Return (Gregorian ISO date, Jalali label), or None."""
    text = normalize_text(text)
    match = _DATE_RE.search(text)
    if not match:
        return None
    year, month, day = map(int, match.groups())
    if not (1300 <= year <= 1500 and 1 <= month <= 12 and 1 <= day <= 31):
        return None
    try:
        gdate = jalali_to_gregorian(year, month, day)
        return gdate.isoformat(), f"{year:04d}/{month:02d}/{day:02d}"
    except ValueError:
        return None


def jalali_to_gregorian(jy: int, jm: int, jd: int) -> date:
    """Convert Jalali date to Gregorian using integer calendar arithmetic."""
    if not (1 <= jm <= 12 and 1 <= jd <= 31):
        raise ValueError("invalid Jalali date")
    jy -= 979
    days = 365 * jy + (jy // 33) * 8 + ((jy % 33 + 3) // 4) + 78 + jd
    if jm < 7:
        days += (jm - 1) * 31
    else:
        days += 186 + (jm - 7) * 30
    gy = 1600 + 400 * (days // 146097)
    days %= 146097
    leap = True
    if days >= 36525:
        days -= 1
        gy += 100 * (days // 36524)
        days %= 36524
        if days >= 365:
            days += 1
        else:
            leap = False
    gy += 4 * (days // 1461)
    days %= 1461
    if days >= 366:
        leap = False
        days -= 1
        gy += days // 365
        days %= 365
    gd = days + 1
    month_days = [31, 29 if leap else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
    gm = 1
    for count in month_days:
        if gd <= count:
            break
        gd -= count
        gm += 1
    if gm > 12:
        raise ValueError("invalid converted date")
    return date(gy, gm, gd)


def parse_amount(text: str) -> Optional[int]:
    """Parse the first plausible whole-number price from a cell or phrase."""
    normalized = normalize_text(text)
    # Prefer values adjacent to a currency/unit label to avoid picking the rebar size.
    price_patterns = [
        r"([0-9][0-9,٬،. ]{2,})\s*(?:تومان|ت\s*/\s*کیلو|تومان\s*/\s*کیلو(?:گرم)?|ت\s*/\s*کیلوگرم)",
        r"([0-9][0-9,٬،. ]{2,})\s*(?:IRR|تومان)",
    ]
    for pattern in price_patterns:
        match = re.search(pattern, normalized, flags=re.IGNORECASE)
        if match:
            digits = re.sub(r"\D", "", match.group(1))
            if digits:
                value = int(digits)
                if value >= 1000:
                    return value
    # Useful for chart cells where the unit is only shown in the table header.
    candidates = re.findall(r"(?<!\d)(\d[\d,٬،. ]{2,})", normalized)
    for candidate in candidates:
        digits = re.sub(r"\D", "", candidate)
        if digits:
            value = int(digits)
            if value >= 1000:
                return value
    return None


def extract_price_after_keyword(text: str, keyword: str, max_chars: int = 180) -> Optional[int]:
    normalized = normalize_text(text)
    idx = normalized.find(normalize_text(keyword))
    if idx < 0:
        return None
    return parse_amount(normalized[idx:idx + max_chars])


def extract_jalali_date_after_keyword(text: str, keyword: str, max_chars: int = 120) -> Optional[tuple[str, str]]:
    normalized = normalize_text(text)
    idx = normalized.find(normalize_text(keyword))
    if idx < 0:
        return None
    return parse_jalali_date(normalized[idx:idx + max_chars])


def is_target_rebar(text: str) -> bool:
    """Target exactly the comparable 14 mm A3 Zobahan Esfahan product."""
    text = normalize_text(text).lower()
    if "میلگرد" not in text:
        return False
    # Look for a standalone 14 to avoid matching 140 or a price containing 14.
    size_match = re.search(r"(?<!\d)14(?!\d)", text)
    if not size_match:
        return False
    if not re.search(r"\ba\s*[- ]?3\b", text) and "a3" not in text.replace(" ", ""):
        return False
    has_factory = ("ذوب آهن" in text or "ذوباهن" in text) and ("اصفهان" in text or "zobahan" in text.lower())
    return has_factory
