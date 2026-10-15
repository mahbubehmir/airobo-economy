"""Periodic runner: one immediate collection followed by daily snapshots."""
from __future__ import annotations
import time
import traceback
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo

from config import DATABASE_PATH, OUTPUT_DIR, COLLECTION_INTERVAL_HOURS, AHANTIME_URL, FOOLADSELL_URL
from collectors import collect_ahantime, collect_fooladsell
from database import create_run, save_source_result, save_source_failure, finish_run
from models import SourceFailure
from report import build_reports

TEHRAN = ZoneInfo("Asia/Tehran")


def run_once() -> None:
    started = datetime.now(TEHRAN).isoformat(timespec="seconds")
    run_id = create_run(DATABASE_PATH)
    print(f"\n{'=' * 72}\nشروع اجرای شماره {run_id} در {started}\nمحصول هدف: میلگرد آجدار ۱۴ A3 ذوب‌آهن اصفهان\n", flush=True)
    successes = 0
    failures = 0
    errors: list[str] = []
    source_jobs = [
        ("ahantime", AHANTIME_URL, collect_ahantime),
        ("fooladsell", FOOLADSELL_URL, collect_fooladsell),
    ]
    for source_id, source_url, collector in source_jobs:
        try:
            result = collector()
            inserted, archived = save_source_result(DATABASE_PATH, run_id, result)
            successes += 1
            print(f"[OK] {source_id}: {result.note} | رکورد جدید درج‌شده: {inserted} (تاریخچه: {archived})", flush=True)
        except Exception as exc:
            failures += 1
            error = f"{type(exc).__name__}: {exc}"
            errors.append(f"{source_id}: {error}")
            save_source_failure(DATABASE_PATH, run_id, SourceFailure(source_id, source_url, error))
            print(f"[ERROR] {source_id}: {error}", flush=True)
    message = " | ".join(errors) if errors else "جمع‌آوری کامل شد."
    finish_run(DATABASE_PATH, run_id, successes, failures, message)
    paths = build_reports(DATABASE_PATH, OUTPUT_DIR, latest_run_id=run_id)
    print(f"وضعیت اجرا: {'success' if failures == 0 else ('partial' if successes else 'failed')}")
    for label, path in paths.items():
        print(f"{label}: {path}")
    print("توجه: اگر منبعی شکست خورده باشد، جزئیات آن در گزارش فنی و دیتابیس ثبت شده است.", flush=True)


def main() -> None:
    DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    interval_seconds = COLLECTION_INTERVAL_HOURS * 3600
    print("رصدخانه قیمت میلگرد آماده است.", flush=True)
    print(f"فاصله اجراها: هر {COLLECTION_INTERVAL_HOURS} ساعت؛ اجرای اول بلافاصله انجام می‌شود.", flush=True)
    print("برای توقف از Ctrl+C استفاده کنید.\n", flush=True)
    while True:
        cycle_started = time.monotonic()
        try:
            run_once()
        except Exception as exc:
            print(f"[FATAL] اجرای گزارش‌ساز شکست خورد: {type(exc).__name__}: {exc}", flush=True)
            traceback.print_exc()
        elapsed = time.monotonic() - cycle_started
        sleep_for = max(60, interval_seconds - int(elapsed))
        print(f"اجرای بعدی حدود {sleep_for // 3600} ساعت و {(sleep_for % 3600) // 60} دقیقه دیگر آغاز می‌شود.\n", flush=True)
        try:
            time.sleep(sleep_for)
        except KeyboardInterrupt:
            print("توقف با درخواست کاربر.", flush=True)
            break

if __name__ == "__main__":
    main()
