"""Generate technical markdown and CSV outputs without any generative AI."""
from __future__ import annotations
import csv
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
from typing import Iterable

from analysis import daily_series, calculate_trends, detect_anomalies, calculate_divergence, latest_per_source
from database import connect, load_observations

TEHRAN = ZoneInfo("Asia/Tehran")


def fmt_int(value):
    return "—" if value is None else f"{int(value):,}"


def fmt_pct(value):
    return "—" if value is None else f"{value:+.2f}%"


def write_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8-sig")
        return
    keys = list(rows[0].keys())
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=keys, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def _source_statuses(db_path: Path | str, latest_run_id: int | None = None) -> list[dict]:
    with connect(db_path) as conn:
        if latest_run_id is None:
            row = conn.execute("SELECT MAX(id) AS id FROM collection_runs").fetchone()
            latest_run_id = row["id"] if row else None
        if latest_run_id is None:
            return []
        rows = conn.execute("SELECT * FROM source_runs WHERE run_id=? ORDER BY source_id", (latest_run_id,)).fetchall()
    return [dict(r) for r in rows]


def build_reports(db_path: Path | str, output_dir: Path | str, latest_run_id: int | None = None) -> dict[str, Path]:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    observations = load_observations(db_path)
    series = daily_series(observations)
    trends = calculate_trends(series)
    anomalies = detect_anomalies(series)
    divergences = calculate_divergence(series)
    latest = latest_per_source(series)
    statuses = _source_statuses(db_path, latest_run_id)

    csv_history = output / "price_history.csv"
    csv_trends = output / "daily_weekly_trends.csv"
    csv_anomalies = output / "anomalies_2sigma.csv"
    csv_divergence = output / "source_divergence.csv"
    write_csv(csv_history, series)
    write_csv(csv_trends, trends)
    write_csv(csv_anomalies, anomalies)
    write_csv(csv_divergence, divergences)

    now = datetime.now(TEHRAN).isoformat(timespec="seconds")
    lines = [
        "# گزارش فنی رصدخانه قیمت میلگرد آجدار",
        "",
        f"- زمان تولید گزارش: `{now}`",
        "- محصول هدف: میلگرد آجدار ۱۴، استاندارد A3، ذوب‌آهن اصفهان",
        "- واحد مقایسه: تومان به‌ازای هر کیلوگرم",
        "- محاسبات بدون مدل زبانی و بر اساس داده ثبت‌شده در SQLite انجام شده‌اند.",
        "",
        "## ۱. وضعیت آخرین اجرای جمع‌آوری",
        "",
        "| منبع | وضعیت | تاریخچه جدید ذخیره‌شده | snapshot جدید | جزئیات |",
        "|---|---|---:|---:|---|",
    ]
    if statuses:
        for st in statuses:
            detail = str(st.get("detail", "")).replace("|", "\\|").replace("\n", " ")
            lines.append(f"| {st['source_id']} | {st['status']} | {st.get('archive_records', 0)} | {st.get('snapshot_records', 0)} | {detail} |")
    else:
        lines.append("| — | هنوز اجرا نشده | 0 | 0 | پس از اجرای collector وضعیت ثبت می‌شود. |")

    lines += ["", "## ۲. آخرین قیمت ثبت‌شده به تفکیک منبع", "", "| منبع | تاریخ مبنای قیمت | قیمت (تومان/کیلو) | نوع رکورد |", "|---|---|---:|---|"]
    if latest:
        for source_id, row in sorted(latest.items()):
            lines.append(f"| {source_id} | {row['market_date']} | {fmt_int(row['price_toman_per_kg'])} | {row['record_type']} |")
    else:
        lines.append("| — | — | — | هنوز داده‌ای در دیتابیس نیست |")

    lines += [
        "", "## ۳. روند روزانه و هفتگی", "",
        "| منبع | تاریخ | قیمت (تومان/کیلو) | تغییر نسبت به مشاهده قبلی | تغییر نسبت به آخرین مشاهده در/قبل از ۷ روز پیش |",
        "|---|---|---:|---:|---:|",
    ]
    if trends:
        for row in trends[-40:]:
            lines.append(f"| {row['source_id']} | {row['market_date']} | {fmt_int(row['price_toman_per_kg'])} | {fmt_pct(row['daily_change_pct'])} | {fmt_pct(row['weekly_change_pct'])} |")
        if len(trends) > 40:
            lines.append(f"| … | … | … | … | … |\n\n*فقط ۴۰ ردیف آخر در گزارش Markdown نمایش داده شده؛ CSV شامل کل سری روزانه است.*")
    else:
        lines.append("| — | — | — | — | داده‌ای برای محاسبه موجود نیست |")

    lines += [
        "", "## ۴. نوسان غیرعادی (قاعده ۲ انحراف معیار)", "",
        "**مبنای محاسبه:** تغییر روزانه درصدی هر منبع، نسبت به مشاهده روز قبل همان منبع. برای هر روز، میانگین و انحراف معیار نمونه‌ای از حداکثر ۲۰ بازده درصدیِ قبلی محاسبه می‌شود؛ بازده روز مورد آزمون در مبنا وارد نمی‌شود. حداقل ۵ بازده قبلی لازم است. رخداد زمانی علامت می‌خورد که `|بازده جاری − میانگین بازده‌های قبلی| > 2 × انحراف معیار نمونه‌ای` باشد. این پرچم آماری است و علت اقتصادی را اثبات نمی‌کند.",
        "", "| منبع | تاریخ | تغییر روزانه | میانگین مبنا | انحراف معیار مبنا | تعداد بازده در مبنا |",
        "|---|---|---:|---:|---:|---:|",
    ]
    if anomalies:
        for row in anomalies:
            lines.append(f"| {row['source_id']} | {row['market_date']} | {fmt_pct(row['daily_change_pct'])} | {fmt_pct(row['baseline_mean_pct'])} | {fmt_pct(row['baseline_sd_pct'])} | {row['prior_returns_used']} |")
    else:
        lines.append("| — | — | — | — | — | — | رخداد ۲σ شناسایی نشد یا تاریخچه برای حداقل ۵ بازده قبلی کافی نیست. |")

    lines += [
        "", "## ۵. واگرایی بین منابع", "",
        "مقایسه برای همان SKU انجام می‌شود. اگر تاریخ دو منبع یکسان باشد، ردیف `same_market_date` تولید می‌شود؛ اگر متفاوت باشد، فقط یک مقایسه جداگانه از آخرین قیمت‌های در دسترس با برچسب `latest_available_different_dates` درج می‌شود و دو تاریخ مستقل در جدول می‌آید. درصد واگرایی برابر `|قیمت منبع ۱ − قیمت منبع ۲| ÷ میانگین دو قیمت × ۱۰۰` است.",
        "قیمت‌ها از دو وب‌سایت تجاری‌اند؛ مالیات، محل تحویل، شرایط فروش و زمان به‌روزرسانی ممکن است یکسان نباشند. ردیف latest با تاریخ‌های متفاوت مقایسه هم‌زمان نیست. بنابراین اختلاف، مقایسه عددیِ اعلام قیمت است و لزوماً آربیتراژ یا اختلاف قیمت قابل معامله نیست.",
        "", "| نوع مقایسه | تاریخ آهن‌تایم | تاریخ فولادسل | قیمت آهن‌تایم (تومان/کیلو) | قیمت فولادسل (تومان/کیلو) | اختلاف مطلق (تومان/کیلو) | واگرایی نسبت به میانگین |",
        "|---|---|---|---:|---:|---:|---:|",
    ]
    if divergences:
        for row in divergences[-30:]:
            lines.append(f"| {row['comparison_type']} | {row['ahantime_market_date']} | {row['fooladsell_market_date']} | {fmt_int(row['ahantime_price'])} | {fmt_int(row['fooladsell_price'])} | {fmt_int(row['absolute_gap_toman'])} | {fmt_pct(row['divergence_pct_of_mean'])} |")
    else:
        lines.append("| — | — | — | — | — | — | هنوز تاریخ مشترک معتبر بین دو منبع برای SKU هدف وجود ندارد. |")

    lines += [
        "", "## ۶. محدودیت‌های داده", "",
        "- صفحه آهن‌تایم برای SKU منتخب دارای جدول تاریخ/قیمت نمودار است؛ ردیف‌های قابل‌استخراج به‌عنوان `archive` نگهداری می‌شوند و با اجرای بعدی دوباره تکرار نمی‌شوند.",
        "- فولادسل در این نسخه تاریخ‌های درج‌شده در جدول صفحه محصول را به‌عنوان تاریخچه می‌دهد؛ این داده‌ها آرشیو روزانه کامل نیستند و عنوان صفحه به‌تنهایی همه مشخصات فنی محصول را اثبات نمی‌کند.",
        "- اگر ساختار HTML، واحد قیمت یا عنوان کارخانه تغییر کند، collector خطای صریح ثبت می‌کند و قیمت جایگزین یا داده ساختگی وارد دیتابیس نمی‌شود.",
        "- اگر تاریخ صفحه قابل استخراج نباشد، تاریخ جمع‌آوری ذخیره می‌شود و `date_basis=collection` این موضوع را مشخص می‌کند؛ این تاریخ الزاماً تاریخ اعلام قیمت توسط فروشنده نیست.",
        "- بدون دست‌کم ۶ تاریخ قابل مقایسه برای هر منبع، الگوریتم ۲σ عملاً امکان ارزیابی کافی ندارد؛ برای روند هفتگی نیز حداقل یک تاریخ هفت روز یا بیشتر قبل لازم است.",
        "",
        "## فایل‌های داده",
        "- `price_history.csv`: سری روزانه منتخب به تفکیک منبع",
        "- `daily_weekly_trends.csv`: درصد تغییرات روزانه و هفتگی",
        "- `anomalies_2sigma.csv`: پرش‌های علامت‌خورده با مبنای ۲σ",
        "- `source_divergence.csv`: اختلاف قیمت در تاریخ‌های مشترک",
        "",
    ]
    report_path = output / "technical_report.md"
    report_path.write_text("\n".join(lines), encoding="utf-8")
    return {
        "technical_report": report_path,
        "price_history": csv_history,
        "trends": csv_trends,
        "anomalies": csv_anomalies,
        "divergence": csv_divergence,
    }
