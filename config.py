"""Configuration for the rebar price observatory."""
from __future__ import annotations
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = Path(os.getenv("DATA_DIR", str(BASE_DIR / "data")))
OUTPUT_DIR = Path(os.getenv("OUTPUT_DIR", str(BASE_DIR / "output")))
DATABASE_PATH = Path(os.getenv("DATABASE_PATH", str(DATA_DIR / "rebar_observatory.sqlite3")))

AHANTIME_URL = os.getenv(
    "AHANTIME_URL",
    "https://ahantime.com/prices/rebar/deformed/rebar-14-a3-zobahan",
)
FOOLADSELL_URL = os.getenv(
    "FOOLADSELL_URL",
    "https://fooladsell.com/product/%D9%85%DB%8C%D9%84%DA%AF%D8%B1%D8%AF-%D8%A2%D8%AC%D8%AF%D8%A7%D8%B1-%D8%B0%D9%88%D8%A8-%D8%A2%D9%87%D9%86-%D8%A7%D8%B5%D9%81%D9%87%D8%A7%D9%86-a3-%D8%B3%D8%A7%DB%8C%D8%B2-14/",
)
COLLECTION_INTERVAL_HOURS = max(1, int(os.getenv("COLLECTION_INTERVAL_HOURS", "24")))
HTTP_TIMEOUT_SECONDS = max(5, int(os.getenv("HTTP_TIMEOUT_SECONDS", "25")))
USER_AGENT = os.getenv(
    "USER_AGENT",
    "RebarPriceObservatory/1.0 (educational research; contact: project owner)",
)

PRODUCT_KEY = "rebar_14_a3_zobahan_esfahan"
PRODUCT_NAME = "میلگرد آجدار ۱۴ ذوب‌آهن اصفهان"
PRODUCT_SIZE_MM = 14
PRODUCT_STANDARD = "A3"
PRODUCT_MANUFACTURER = "ذوب‌آهن اصفهان"
