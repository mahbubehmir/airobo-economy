"""Public-page collectors for one comparable rebar product from two Iranian sources."""
from __future__ import annotations
import re
from datetime import datetime
from zoneinfo import ZoneInfo
from typing import Iterable
import requests
from bs4 import BeautifulSoup

from config import (
    AHANTIME_URL, FOOLADSELL_URL, HTTP_TIMEOUT_SECONDS, USER_AGENT,
    PRODUCT_KEY, PRODUCT_NAME, PRODUCT_SIZE_MM, PRODUCT_STANDARD, PRODUCT_MANUFACTURER,
)
from models import PriceRecord, SourceResult
from parsing import normalize_text, parse_amount, parse_jalali_date, extract_price_after_keyword, extract_jalali_date_after_keyword, is_target_rebar

TEHRAN = ZoneInfo("Asia/Tehran")

class CollectionError(RuntimeError):
    pass


def now_tehran() -> datetime:
    return datetime.now(TEHRAN)


def fetch_html(url: str) -> str:
    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "fa-IR,fa;q=0.9,en;q=0.6",
    }
    try:
        response = requests.get(url, headers=headers, timeout=HTTP_TIMEOUT_SECONDS)
        response.raise_for_status()
        # Some Persian sites omit an explicit charset; avoid decoding their HTML
        # as ISO-8859-1 and silently losing the Persian product labels.
        if not response.encoding or response.encoding.lower() in {"iso-8859-1", "ascii"}:
            response.encoding = response.apparent_encoding or "utf-8"
    except requests.RequestException as exc:
        raise CollectionError(f"HTTP دریافت صفحه ناموفق بود: {type(exc).__name__}: {exc}") from exc
    if not response.text or len(response.text) < 500:
        raise CollectionError("پاسخ صفحه خالی یا غیرعادی کوتاه است.")
    return response.text


def _current_date_basis(soup: BeautifulSoup, full_text: str) -> tuple[str, str, str]:
    update_date = extract_jalali_date_after_keyword(full_text, "به روزرسانی")
    if not update_date:
        update_date = extract_jalali_date_after_keyword(full_text, "آخرین به روزرسانی")
    if update_date:
        return update_date[0], update_date[1], "source"
    today = now_tehran().date().isoformat()
    return today, today, "collection"


def collect_ahantime() -> SourceResult:
    """Collect current display price and the historical chart table from Ahantime."""
    url = AHANTIME_URL
    html = fetch_html(url)
    soup = BeautifulSoup(html, "html.parser")
    full_text = normalize_text(soup.get_text(" ", strip=True))
    records: list[PriceRecord] = []
    # The general page text contains several adjacent numeric columns (per-kg price,
    # price difference, and total cost). Extract current price only from the exact
    # target-manufacturer row; never parse a long concatenated page-text window.
    current_price = None
    for table in soup.find_all("table"):
        for row in table.find_all("tr"):
            cells = row.find_all(["th", "td"])
            if len(cells) < 2:
                continue
            manufacturer_text = normalize_text(cells[0].get_text(" ", strip=True))
            if manufacturer_text != normalize_text(PRODUCT_MANUFACTURER):
                continue
            candidate = parse_amount(cells[1].get_text(" ", strip=True))
            if candidate is not None and 10_000 <= candidate <= 1_000_000:
                current_price = candidate
                break
        if current_price is not None:
            break
    if current_price is None:
        raise CollectionError(
            "ردیف دقیق کارخانه ذوب‌آهن اصفهان یا قیمت معتبر هر کیلوگرم پیدا نشد؛ snapshot ذخیره نشد."
        )

    current_date, current_label, date_basis = _current_date_basis(soup, full_text)

    # The source chart has a visible table with Persian/Jalali date and price columns.
    archive_count = 0
    sequence = 0
    for table in soup.find_all("table"):
        table_text = normalize_text(table.get_text(" ", strip=True))
        if "تاریخ" not in table_text or "قیمت" not in table_text:
            continue
        for row in table.find_all("tr"):
            cells = row.find_all(["th", "td"])
            if len(cells) < 2:
                continue
            row_text = normalize_text(" | ".join(c.get_text(" ", strip=True) for c in cells))
            parsed_date = parse_jalali_date(cells[0].get_text(" ", strip=True))
            if not parsed_date:
                parsed_date = parse_jalali_date(row_text)
            if not parsed_date:
                continue
            price = parse_amount(cells[1].get_text(" ", strip=True))
            if price is None or not 10_000 <= price <= 1_000_000:
                price = parse_amount(row_text)
            if price is None or not 10_000 <= price <= 1_000_000:
                continue
            sequence += 1
            records.append(PriceRecord(
                source_id="ahantime", product_key=PRODUCT_KEY, product_name=PRODUCT_NAME,
                size_mm=PRODUCT_SIZE_MM, standard=PRODUCT_STANDARD, manufacturer=PRODUCT_MANUFACTURER,
                price_toman_per_kg=price, market_date=parsed_date[0], market_date_label=parsed_date[1],
                date_basis="source", record_type="archive", source_url=url, raw_text=row_text,
                source_sequence=sequence,
            ))
            archive_count += 1

    records.append(PriceRecord(
        source_id="ahantime", product_key=PRODUCT_KEY, product_name=PRODUCT_NAME,
        size_mm=PRODUCT_SIZE_MM, standard=PRODUCT_STANDARD, manufacturer=PRODUCT_MANUFACTURER,
        price_toman_per_kg=current_price, market_date=current_date, market_date_label=current_label,
        date_basis=date_basis, record_type="snapshot", source_url=url,
        raw_text=f"قیمت فعلی صفحه: {current_price} تومان/کیلوگرم؛ تاریخ مبنا: {current_label}",
        source_sequence=sequence + 1,
    ))
    note = f"قیمت جاری استخراج شد؛ {archive_count} ردیف تاریخی از جدول نمودار پیدا شد."
    if archive_count == 0:
        note += " هشدار: جدول تاریخچه در HTML دریافت‌شده پیدا نشد؛ فقط قیمت جاری ذخیره شد."
    return SourceResult(source_id="ahantime", source_url=url, records=records, note=note)


def _candidate_nodes(soup: BeautifulSoup) -> list:
    """Collect table rows first, then likely card containers for differing HTML layouts."""
    nodes = list(soup.find_all("tr"))
    for node in soup.find_all(["article", "li"]):
        nodes.append(node)
    for node in soup.find_all(True, class_=re.compile(r"product|price|offer|row|item|card", re.I)):
        nodes.append(node)
    seen_ids = set()
    result = []
    # Prefer concise candidates; long page containers are last and can contain unrelated products.
    for node in sorted(nodes, key=lambda n: len(n.get_text(" ", strip=True))):
        if id(node) in seen_ids:
            continue
        seen_ids.add(id(node))
        txt = normalize_text(node.get_text(" ", strip=True))
        if txt and len(txt) <= 1800:
            result.append(node)
    return result


def _price_per_kg_from_text(text: str) -> int | None:
    """Require an explicit kg unit to avoid mistaking the price of a whole bar/offer."""
    text = normalize_text(text)
    patterns = [
        r"([0-9][0-9,٬،. ]{2,})\s*(?:تومان\s*/\s*کیلو(?:گرم)?|ت\s*/\s*کیلو(?:گرم)?|تومان\s*بر\s*کیلو(?:گرم)?)",
        r"([0-9][0-9,٬،. ]{2,})\s*(?:تومان\s*/\s*kg|IRR\s*/\s*kg)",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.I)
        if match:
            val = parse_amount(match.group(1))
            if val and val >= 1000:
                return val
    return None


def collect_fooladsell() -> SourceResult:
    """Collect dated price history from the dedicated FooladSell product page."""
    url = FOOLADSELL_URL
    html = fetch_html(url)
    soup = BeautifulSoup(html, "html.parser")
    title = normalize_text(soup.title.get_text(" ", strip=True) if soup.title else "")

    # This URL is the dedicated product page for 14-mm A3 Zobahan Esfahan rebar.
    # Keep a title guard to avoid silently ingesting an unexpected redirect/page.
    if "میلگرد" not in title or not re.search(r"(?<!\d)14(?!\d)", title) or "اصفهان" not in title:
        raise CollectionError(f"عنوان صفحه فولادسل با محصول هدف سازگار نیست: {title}")

    records: list[PriceRecord] = []
    sequence = 0
    for table in soup.find_all("table"):
        rows = table.find_all("tr")
        if not rows:
            continue
        header = normalize_text(rows[0].get_text(" ", strip=True))
        if "تاریخ" not in header or "قیمت" not in header:
            continue
        for row in rows[1:]:
            cells = row.find_all(["th", "td"])
            if len(cells) < 2:
                continue
            row_text = normalize_text(" | ".join(cell.get_text(" ", strip=True) for cell in cells))
            parsed_date = parse_jalali_date(cells[0].get_text(" ", strip=True))
            if not parsed_date:
                continue
            price = parse_amount(cells[1].get_text(" ", strip=True))
            if price is None or not 10_000 <= price <= 1_000_000:
                continue
            sequence += 1
            records.append(PriceRecord(
                source_id="fooladsell", product_key=PRODUCT_KEY, product_name=PRODUCT_NAME,
                size_mm=PRODUCT_SIZE_MM, standard=PRODUCT_STANDARD, manufacturer=PRODUCT_MANUFACTURER,
                price_toman_per_kg=price, market_date=parsed_date[0], market_date_label=parsed_date[1],
                date_basis="source", record_type="archive", source_url=url, raw_text=row_text,
                source_sequence=sequence,
            ))

    if not records:
        raise CollectionError("فولادسل دریافت شد، اما تاریخ و قیمت معتبر در جدول صفحه محصول پیدا نشد.")

    records.sort(key=lambda record: record.market_date)
    return SourceResult(
        source_id="fooladsell", source_url=url, records=records,
        note=f"{len(records)} ردیف تاریخی با تاریخ منبع استخراج شد؛ از {records[0].market_date} تا {records[-1].market_date}.",
    )


def collect_all() -> tuple[list[SourceResult], list[Exception]]:
    results: list[SourceResult] = []
    errors: list[Exception] = []
    for collector in (collect_ahantime, collect_fooladsell):
        try:
            results.append(collector())
        except Exception as exc:
            # One unavailable source must not discard data from the other source.
            errors.append(exc)
            print(f"[WARN] source collection failed: {exc}", flush=True)
    return results, errors
