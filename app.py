"""Streamlit dashboard for the Rebar Price Observatory.

The application displays deterministic statistics and stores human-authored economic
interpretations/media posts. No LLM or AI text generation is used.
"""
from __future__ import annotations
from datetime import date, timedelta
from pathlib import Path
import pandas as pd
import plotly.express as px
import streamlit as st

from config import DATABASE_PATH, OUTPUT_DIR, PRODUCT_NAME
from database import load_observations, load_recent_runs
from analysis import daily_series, calculate_trends, detect_anomalies, calculate_divergence, latest_per_source
from dashboard_storage import (
    ensure_manual_tables, list_economic_entries, get_economic_entry, save_economic_entry,
    delete_economic_entry, list_media_posts, get_media_post, save_media_post,
    delete_media_post, render_economic_markdown, render_posts_markdown, export_manual_documents,
)

st.set_page_config(page_title="رصدخانه قیمت میلگرد", page_icon="📊", layout="wide")
st.markdown("""
<style>
  .block-container {padding-top: 1.2rem; padding-bottom: 2rem;}
  [data-testid="stAppViewContainer"] {direction: rtl;}
  [data-testid="stSidebar"] * {text-align: right;}
  h1, h2, h3, p, label {text-align: right;}
  div[data-testid="stMetric"] {direction: rtl; text-align: right;}
  .small-note {color: #666; font-size: .9rem;}
</style>
""", unsafe_allow_html=True)

SOURCE_LABELS = {"ahantime": "آهن‌تایم", "fooladsell": "فولادسل"}
ANALYSIS_TYPES = ["رشد/افت قیمت", "نوسان غیرعادی", "واگرایی بین منابع", "عرضه و تقاضا", "ارز/تورم", "خبر یا سیاست‌گذاری", "سایر"]
CONFIDENCE_LEVELS = ["کم", "متوسط", "زیاد"]
STATUSES = ["پیش‌نویس", "بازبینی‌شده", "آماده انتشار"]
POST_TYPES = ["تحلیل بازار", "داده در برابر شایعه", "راهنمای تصمیم"]


def source_label(value: str) -> str:
    return SOURCE_LABELS.get(str(value), str(value))


def fmt_price(value) -> str:
    if value is None or pd.isna(value):
        return "—"
    return f"{int(value):,}"


def fmt_percent(value) -> str:
    if value is None or pd.isna(value):
        return "—"
    return f"{float(value):+.2f}%"


def formatted_table(frame: pd.DataFrame, mapping: dict[str, str], price_cols: tuple[str, ...] = (), pct_cols: tuple[str, ...] = ()) -> pd.DataFrame:
    shown = frame.copy()
    for col in price_cols:
        if col in shown:
            shown[col] = shown[col].map(fmt_price)
    for col in pct_cols:
        if col in shown:
            shown[col] = shown[col].map(fmt_percent)
    if "source_id" in shown:
        shown["source_id"] = shown["source_id"].map(source_label)
    if "higher_source" in shown:
        shown["higher_source"] = shown["higher_source"].map(lambda v: "برابر" if v == "equal" else source_label(v))
    return shown.rename(columns=mapping)


def style_metric_delta(value: float | None) -> str | None:
    if value is None or pd.isna(value):
        return None
    return f"{float(value):+.2f}% نسبت به مرجع هفت‌روزه"


def show_manual_export_buttons() -> None:
    entries = list_economic_entries()
    posts = list_media_posts()
    c1, c2 = st.columns(2)
    with c1:
        st.download_button(
            "دانلود دفتر تحلیل اقتصادی (Markdown)",
            data=render_economic_markdown(entries),
            file_name="economic_journal.md", mime="text/markdown", use_container_width=True,
        )
    with c2:
        st.download_button(
            "دانلود پست‌های رسانه‌ای (Markdown)",
            data=render_posts_markdown(posts),
            file_name="media_posts.md", mime="text/markdown", use_container_width=True,
        )


ensure_manual_tables()
raw_observations = load_observations(DATABASE_PATH)
series = daily_series(raw_observations)
trend_records = calculate_trends(series)
anomaly_records = detect_anomalies(series)
divergence_records = calculate_divergence(series)
latest_records = latest_per_source(series)
entries = list_economic_entries()
posts = list_media_posts()

st.title("رصدخانه قیمت میلگرد")
st.caption(f"{PRODUCT_NAME} | واحد: تومان به‌ازای هر کیلوگرم | تحلیل آماری قطعی؛ تفسیر اقتصادی با نگارش انسانی")

with st.sidebar:
    st.header("ناوبری")
    page = st.radio("بخش", [
        "نمای کلی", "روند و درصد تغییر", "نوسان غیرعادی (۲σ)", "واگرایی منابع",
        "دفتر تحلیل اقتصادی دستی", "پست‌های رسانه‌ای", "وضعیت داده و اجراها",
    ])
    st.divider()
    st.caption(f"دیتابیس فعال: {DATABASE_PATH}")
    if st.button("بازخوانی داده‌ها", use_container_width=True):
        st.rerun()

if not raw_observations:
    st.warning("در دیتابیس فعلی داده‌ای برای محصول هدف پیدا نشد. ابتدا `python main.py` را اجرا کنید.")

# Shared time/source filters (statistics are calculated before the display filter).
if series:
    all_dates = sorted({date.fromisoformat(row["market_date"]) for row in series})
    default_range = (all_dates[0], all_dates[-1])
else:
    today = date.today()
    default_range = (today - timedelta(days=30), today)
with st.sidebar:
    chosen_range = st.date_input("بازه نمایش", value=default_range, min_value=all_dates[0] if series else None, max_value=all_dates[-1] if series else None)
    source_ids = sorted({row["source_id"] for row in series})
    chosen_sources = st.multiselect("منابع", source_ids, default=source_ids, format_func=source_label)

if isinstance(chosen_range, tuple) and len(chosen_range) == 2:
    range_start, range_end = chosen_range
elif isinstance(chosen_range, list) and len(chosen_range) == 2:
    range_start, range_end = chosen_range
elif isinstance(chosen_range, (date,)):
    range_start = range_end = chosen_range
else:
    range_start, range_end = default_range

trend_df = pd.DataFrame(trend_records)
series_df = pd.DataFrame(series)
anomaly_df = pd.DataFrame(anomaly_records)
divergence_df = pd.DataFrame(divergence_records)
if not trend_df.empty:
    trend_df = trend_df[
        trend_df["source_id"].isin(chosen_sources)
        & (trend_df["market_date"] >= range_start.isoformat())
        & (trend_df["market_date"] <= range_end.isoformat())
    ].copy()
if not series_df.empty:
    series_df = series_df[
        series_df["source_id"].isin(chosen_sources)
        & (series_df["market_date"] >= range_start.isoformat())
        & (series_df["market_date"] <= range_end.isoformat())
    ].copy()
if not anomaly_df.empty:
    anomaly_df = anomaly_df[
        anomaly_df["source_id"].isin(chosen_sources)
        & (anomaly_df["market_date"] >= range_start.isoformat())
        & (anomaly_df["market_date"] <= range_end.isoformat())
    ].copy()
if not divergence_df.empty:
    divergence_df = divergence_df[
        divergence_df["ahantime_market_date"].between(range_start.isoformat(), range_end.isoformat())
        | divergence_df["fooladsell_market_date"].between(range_start.isoformat(), range_end.isoformat())
    ].copy()

if page == "نمای کلی":
    st.subheader("نمای کلی داده‌ها")
    columns = st.columns(4)
    columns[0].metric("مشاهدات خام", f"{len(raw_observations):,}")
    columns[1].metric("تاریخ‌های متمایز", f"{len({r['market_date'] for r in series}):,}")
    columns[2].metric("رویدادهای ۲σ", f"{len(anomaly_records):,}")
    columns[3].metric("تحلیل‌های دستی ثبت‌شده", f"{len(entries):,} از ۵ هدف")

    metric_cols = st.columns(max(1, len(latest_records)))
    if latest_records:
        for col, (source_id, row) in zip(metric_cols, sorted(latest_records.items())):
            source_trends = [r for r in trend_records if r["source_id"] == source_id]
            last_trend = max(source_trends, key=lambda r: r["market_date"]) if source_trends else None
            delta = last_trend.get("weekly_change_pct") if last_trend else None
            col.metric(f"آخرین قیمت — {source_label(source_id)}", f"{fmt_price(row['price_toman_per_kg'])} تومان", delta=style_metric_delta(delta), delta_color="off", help=f"تاریخ داده: {row['market_date']}; نوع رکورد: {row['record_type']}")
    else:
        st.info("هنوز قیمت قابل نمایش وجود ندارد.")

    if not series_df.empty:
        st.subheader("روند قیمت در بازه انتخاب‌شده")
        fig = px.line(series_df.sort_values("market_date"), x="market_date", y="price_toman_per_kg", color="source_id", markers=True,
                      labels={"market_date": "تاریخ", "price_toman_per_kg": "قیمت (تومان/کیلوگرم)", "source_id": "منبع"},
                      color_discrete_sequence=px.colors.qualitative.Safe)
        fig.update_layout(legend_title_text="منبع", hovermode="x unified")
        st.plotly_chart(fig, use_container_width=True)
    st.info("نکته تطبیق کالا: جدول فولادسل از صفحه اختصاصی میلگرد ۱۴ اصفهان استخراج شده؛ عنوان صفحه به‌تنهایی استاندارد A3 و کارخانه ذوب‌آهن را صریحاً اثبات نمی‌کند. پیش از نتیجه‌گیری اقتصادی درباره واگرایی، مشخصات محصول و شرایط قیمت‌گذاری را دستی تأیید کنید.")
    st.subheader("پیشرفت اقلام تحویلی")
    rumor_count = sum(1 for p in posts if p["post_type"] == "داده در برابر شایعه")
    p1, p2, p3 = st.columns(3)
    p1.metric("دفتر تحلیل اقتصادی", f"{min(len(entries), 5)}/5")
    p2.metric("پست‌های رسانه‌ای", f"{min(len(posts), 3)}/3")
    p3.metric("پست داده در برابر شایعه", "تکمیل" if rumor_count else "ثبت نشده")
    st.caption("این شمارنده‌ها فقط پیشرفت ثبت محتوا را نشان می‌دهند؛ کیفیت استدلال، منبع‌دهی و صحت ادعاها باید توسط خودتان بازبینی شود.")

elif page == "روند و درصد تغییر":
    st.subheader("روند قیمت و تغییرات روزانه/هفتگی")
    st.markdown("**تعریف:** تغییر روزانه یعنی درصد تغییر نسبت به مشاهده قبلی همان منبع، نه لزوماً روز تقویمی قبل. تغییر هفتگی با آخرین مشاهده موجود در یا قبل از ۷ روز پیش مقایسه می‌شود.")
    if trend_df.empty:
        st.info("برای فیلتر انتخاب‌شده داده‌ای وجود ندارد.")
    else:
        price_fig = px.line(trend_df, x="market_date", y="price_toman_per_kg", color="source_id", markers=True,
                            labels={"market_date":"تاریخ", "price_toman_per_kg":"قیمت (تومان/کیلوگرم)", "source_id":"منبع"})
        price_fig.update_layout(legend_title_text="منبع", hovermode="x unified")
        st.plotly_chart(price_fig, use_container_width=True)
        c1, c2 = st.columns(2)
        daily_plot = trend_df.dropna(subset=["daily_change_pct"])
        weekly_plot = trend_df.dropna(subset=["weekly_change_pct"])
        with c1:
            st.markdown("#### درصد تغییر نسبت به مشاهده قبلی")
            if not daily_plot.empty:
                fig = px.bar(daily_plot, x="market_date", y="daily_change_pct", color="source_id", barmode="group",
                             labels={"market_date":"تاریخ", "daily_change_pct":"تغییر (%)", "source_id":"منبع"})
                fig.add_hline(y=0, line_dash="dot", line_color="gray")
                st.plotly_chart(fig, use_container_width=True)
        with c2:
            st.markdown("#### درصد تغییر هفتگی")
            if not weekly_plot.empty:
                fig = px.line(weekly_plot, x="market_date", y="weekly_change_pct", color="source_id", markers=True,
                              labels={"market_date":"تاریخ", "weekly_change_pct":"تغییر هفتگی (%)", "source_id":"منبع"})
                fig.add_hline(y=0, line_dash="dot", line_color="gray")
                st.plotly_chart(fig, use_container_width=True)
        view = trend_df[["source_id", "market_date", "price_toman_per_kg", "daily_from_date", "daily_change_pct", "weekly_from_date", "weekly_change_pct", "record_type", "date_basis"]].copy()
        view["source_id"] = view["source_id"].map(source_label)
        view["price_toman_per_kg"] = view["price_toman_per_kg"].map(fmt_price)
        view["daily_change_pct"] = view["daily_change_pct"].map(fmt_percent)
        view["weekly_change_pct"] = view["weekly_change_pct"].map(fmt_percent)
        view = view.rename(columns={"source_id":"منبع", "market_date":"تاریخ", "price_toman_per_kg":"قیمت (تومان/کیلو)", "daily_from_date":"مرجع تغییر روزانه", "daily_change_pct":"تغییر نسبت به مشاهده قبلی", "weekly_from_date":"تاریخ مرجع هفتگی", "weekly_change_pct":"تغییر هفتگی", "record_type":"نوع رکورد", "date_basis":"مبنای تاریخ"})
        st.dataframe(view.sort_values("تاریخ", ascending=False), use_container_width=True, hide_index=True)
        st.download_button("دانلود جدول روند CSV", data=trend_df.to_csv(index=False).encode("utf-8-sig"), file_name="daily_weekly_trends_filtered.csv", mime="text/csv")

elif page == "نوسان غیرعادی (۲σ)":
    st.subheader("تشخیص پرش آماری")
    st.markdown("**قاعده:** بازده جاری خارج از میانگین ± دو انحراف معیار نمونه‌ایِ حداکثر ۲۰ بازده قبلی همان منبع باشد؛ حداقل ۵ بازده قبلی لازم است. بازده جاری در مبنا وارد نمی‌شود.")
    st.warning("علامت ۲σ فقط یک هشدار آماری است و علت اقتصادی، خبر خاص یا خطای بازار را اثبات نمی‌کند. داده پرت ناشی از خطای استخراج نیز باید قبل از تفسیر حذف یا اصلاح شود.")
    if anomaly_df.empty:
        st.info("در بازه و منابع انتخاب‌شده رویدادی برای قاعده ۲σ ثبت نشده یا داده تاریخی برای مبنا کافی نبوده است.")
    else:
        anomaly_view = anomaly_df.copy()
        anomaly_view["source_id"] = anomaly_view["source_id"].map(source_label)
        for col in ["daily_change_pct", "baseline_mean_pct", "baseline_sd_pct", "threshold_low_pct", "threshold_high_pct"]:
            anomaly_view[col] = anomaly_view[col].map(fmt_percent)
        anomaly_view["price_toman_per_kg"] = anomaly_view["price_toman_per_kg"].map(fmt_price)
        st.dataframe(anomaly_view.rename(columns={"source_id":"منبع", "market_date":"تاریخ", "price_toman_per_kg":"قیمت", "daily_change_pct":"تغییر روزانه", "baseline_mean_pct":"میانگین مبنا", "baseline_sd_pct":"انحراف معیار مبنا", "threshold_low_pct":"حد پایین ۲σ", "threshold_high_pct":"حد بالای ۲σ", "prior_returns_used":"تعداد بازده‌های مبنا", "method":"روش"}), use_container_width=True, hide_index=True)
        st.download_button("دانلود پرش‌های ۲σ CSV", data=anomaly_df.to_csv(index=False).encode("utf-8-sig"), file_name="anomalies_2sigma_filtered.csv", mime="text/csv")

elif page == "واگرایی منابع":
    st.subheader("مقایسه قیمت دو منبع")
    st.markdown("واگرایی درصدی = اختلاف مطلق دو قیمت ÷ میانگین دو قیمت × ۱۰۰. واگرایی با تغییر قیمت در طول زمان یکی نیست.")
    st.warning("اعتبار مقایسه وابسته به یکسان بودن سایز، استاندارد، کارخانه، واحد، مالیات، محل تحویل و شرایط عرضه است. فولادسل در صفحه بررسی‌شده عنوان عمومی «میلگرد ۱۴ اصفهان» دارد؛ مشخصات کامل را دستی کنترل و در دفتر تحلیل ثبت کنید.")
    same_only = st.checkbox("فقط تاریخ‌های مشترک (مقایسه هم‌زمان)", value=True)
    visible_div = divergence_df.copy()
    if same_only and not visible_div.empty:
        visible_div = visible_div[visible_div["comparison_type"] == "same_market_date"]
    if visible_div.empty:
        st.info("برای فیلتر انتخاب‌شده مقایسه‌ای موجود نیست.")
    else:
        visible_div["نوع مقایسه فارسی"] = visible_div["comparison_type"].map({"same_market_date":"تاریخ مشترک", "latest_available_different_dates":"آخرین قیمت‌های موجود با تاریخ متفاوت"})
        visible_div["منبع با قیمت بالاتر"] = visible_div["higher_source"].map(lambda v: "برابر" if v == "equal" else source_label(v))
        view = visible_div.rename(columns={"ahantime_market_date":"تاریخ آهن‌تایم", "fooladsell_market_date":"تاریخ فولادسل", "ahantime_price":"قیمت آهن‌تایم", "fooladsell_price":"قیمت فولادسل", "absolute_gap_toman":"اختلاف (تومان/کیلو)", "divergence_pct_of_mean":"واگرایی (%)", "note":"ملاحظه"})
        display_cols = ["نوع مقایسه فارسی", "تاریخ آهن‌تایم", "تاریخ فولادسل", "قیمت آهن‌تایم", "قیمت فولادسل", "اختلاف (تومان/کیلو)", "واگرایی (%)", "منبع با قیمت بالاتر"]
        view = view[display_cols].copy()
        for col in ["قیمت آهن‌تایم", "قیمت فولادسل", "اختلاف (تومان/کیلو)"]:
            view[col] = view[col].map(fmt_price)
        view["واگرایی (%)"] = view["واگرایی (%)"].map(fmt_percent)
        st.dataframe(view, use_container_width=True, hide_index=True)
        st.download_button("دانلود واگرایی CSV", data=visible_div.to_csv(index=False).encode("utf-8-sig"), file_name="source_divergence_filtered.csv", mime="text/csv")

elif page == "دفتر تحلیل اقتصادی دستی":
    st.subheader("دفتر تحلیل اقتصادی — نویسنده تحلیل شما هستید")
    st.caption("برای هر رویداد، عدد و روند را از داده‌ها ثبت کنید؛ سپس فرضیه علت، شواهد موافق/مخالف و پیامد تصمیم را با منابع مشخص بنویسید. هیچ مدل زبانی متنی تولید نمی‌کند.")
    entries = list_economic_entries()
    top = st.columns(3)
    top[0].metric("تعداد تحلیل‌ها", f"{len(entries)}/5 حداقل موردنیاز")
    top[1].metric("بازبینی‌شده", str(sum(1 for e in entries if e["status"] == "بازبینی‌شده")))
    top[2].metric("دارای ارجاع", str(sum(1 for e in entries if e["references_text"].strip())))
    edit_mode = st.radio("عملیات", ["ثبت تحلیل جدید", "ویرایش تحلیل ثبت‌شده"], horizontal=True, key="journal_mode")
    selected = None
    if edit_mode == "ویرایش تحلیل ثبت‌شده":
        if not entries:
            st.info("هنوز تحلیلی برای ویرایش ثبت نشده است.")
        else:
            entry_map = {f"#{e['id']} | {e['event_date']} | {e['title']}": e['id'] for e in entries}
            selected_label = st.selectbox("انتخاب تحلیل", list(entry_map), key="journal_select")
            selected = get_economic_entry(entry_map[selected_label])
    if edit_mode == "ثبت تحلیل جدید" or selected:
        key_suffix = str(selected["id"] if selected else "new")
        default_date = date.fromisoformat(selected["event_date"]) if selected else (date.fromisoformat(max((r["market_date"] for r in series), default=date.today().isoformat())))
        with st.form(f"economic_form_{key_suffix}"):
            c1, c2 = st.columns(2)
            event_date = c1.date_input("تاریخ رویداد", value=default_date, key=f"event_date_{key_suffix}")
            event_type = c2.selectbox("نوع رویداد", ANALYSIS_TYPES, index=ANALYSIS_TYPES.index(selected["event_type"]) if selected and selected["event_type"] in ANALYSIS_TYPES else 0, key=f"event_type_{key_suffix}")
            title = st.text_input("عنوان کوتاه رویداد", value=selected["title"] if selected else "", key=f"journal_title_{key_suffix}")
            what_happened = st.text_area("چه شد؟ — عدد، جهت روند، بازه و منبع", value=selected["what_happened"] if selected else "", height=100, key=f"what_{key_suffix}")
            why_hypothesis = st.text_area("چرا ممکن است رخ داده باشد؟ — فرضیه اقتصادی، نه ادعای قطعی", value=selected["why_hypothesis"] if selected else "", height=100, key=f"why_{key_suffix}")
            c3, c4 = st.columns(2)
            with c3:
                evidence_for = st.text_area("شواهد موافق فرضیه", value=selected["evidence_for"] if selected else "", height=90, key=f"for_{key_suffix}")
            with c4:
                evidence_against = st.text_area("شواهد مخالف یا توضیح جایگزین", value=selected["evidence_against"] if selected else "", height=90, key=f"against_{key_suffix}")
            c5, c6, c7 = st.columns(3)
            with c5:
                effect_builder = st.text_area("پیامد برای سازنده", value=selected["effect_builder"] if selected else "", height=90, key=f"builder_{key_suffix}")
            with c6:
                effect_consumer = st.text_area("پیامد برای مصرف‌کننده", value=selected["effect_consumer"] if selected else "", height=90, key=f"consumer_{key_suffix}")
            with c7:
                effect_investor = st.text_area("پیامد برای سرمایه‌گذار خرد", value=selected["effect_investor"] if selected else "", height=90, key=f"investor_{key_suffix}")
            decision_implication = st.text_area("این یعنی چه؟ — خط تصمیم / نتیجه عملی", value=selected["decision_implication"] if selected else "", height=85, key=f"decision_{key_suffix}")
            c8, c9 = st.columns(2)
            with c8:
                confidence_value = selected["confidence"] if selected and selected["confidence"] in CONFIDENCE_LEVELS else "متوسط"
                confidence = st.selectbox("میزان اطمینان", CONFIDENCE_LEVELS, index=CONFIDENCE_LEVELS.index(confidence_value), key=f"confidence_{key_suffix}")
            with c9:
                status_value = selected["status"] if selected and selected["status"] in STATUSES else "پیش‌نویس"
                status = st.selectbox("وضعیت", STATUSES, index=STATUSES.index(status_value), key=f"journal_status_{key_suffix}")
            references_text = st.text_area("منابع/پیوندها و تاریخ دسترسی", value=selected["references_text"] if selected else "", height=80, key=f"refs_{key_suffix}")
            submit = st.form_submit_button("ذخیره تحلیل", use_container_width=True)
        if submit:
            if not title.strip() or not what_happened.strip():
                st.error("عنوان و بخش «چه شد؟» الزامی است.")
            else:
                data = {"event_date": event_date.isoformat(), "event_type": event_type, "title": title.strip(), "what_happened": what_happened.strip(), "why_hypothesis": why_hypothesis.strip(), "evidence_for": evidence_for.strip(), "evidence_against": evidence_against.strip(), "effect_builder": effect_builder.strip(), "effect_consumer": effect_consumer.strip(), "effect_investor": effect_investor.strip(), "decision_implication": decision_implication.strip(), "confidence": confidence, "references_text": references_text.strip(), "status": status}
                saved_id = save_economic_entry(data, selected["id"] if selected else None)
                export_manual_documents()
                st.success(f"تحلیل شماره {saved_id} ذخیره شد.")
                st.rerun()
    if entries:
        st.markdown("#### تحلیل‌های ذخیره‌شده")
        for item in entries:
            with st.expander(f"{item['event_date']} — {item['title']} | {item['status']}"):
                st.markdown(f"**چه شد؟**\n\n{item['what_happened']}")
                st.markdown(f"**تفسیر احتمالی:**\n\n{item['why_hypothesis'] or '—'}")
                st.markdown(f"**شواهد موافق:**\n\n{item['evidence_for'] or '—'}")
                st.markdown(f"**شواهد مخالف/جایگزین:**\n\n{item['evidence_against'] or '—'}")
                st.markdown(f"**پیامد/خط تصمیم:**\n\n{item['decision_implication'] or '—'}")
                st.markdown(f"**منابع:**\n\n{item['references_text'] or '—'}")
        delete_id = st.selectbox("برای حذف (اختیاری) یک تحلیل را انتخاب کن", [e["id"] for e in entries], format_func=lambda i: next(f"#{e['id']} — {e['title']}" for e in entries if e['id'] == i), key="delete_journal_id")
        if st.checkbox("حذف این تحلیل را تأیید می‌کنم", key="confirm_delete_journal") and st.button("حذف تحلیل انتخاب‌شده", key="delete_journal_button"):
            delete_economic_entry(int(delete_id)); export_manual_documents(); st.success("تحلیل حذف شد."); st.rerun()
    show_manual_export_buttons()

elif page == "پست‌های رسانه‌ای":
    st.subheader("کارگاه پست رسانه‌ای — متن را خودت می‌نویسی")
    st.caption("قواعد کنترل‌شونده: تیتر حداکثر ۷ کلمه؛ کل متن حداکثر ۱۲ خط؛ پایان با «خط تصمیم: ...». برای پست «داده در برابر شایعه»، منبع و داده واقعی را حتماً درج کن.")
    posts = list_media_posts()
    rumor_count = sum(1 for p in posts if p["post_type"] == "داده در برابر شایعه")
    c1, c2, c3 = st.columns(3)
    c1.metric("تعداد پست‌ها", f"{len(posts)}/3")
    c2.metric("پست شایعه‌سنجی", "بله" if rumor_count else "خیر")
    c3.metric("آماده انتشار", str(sum(1 for p in posts if p["status"] == "آماده انتشار")))
    post_mode = st.radio("عملیات پست", ["ساخت پست جدید", "ویرایش پست موجود"], horizontal=True, key="post_mode")
    selected_post = None
    if post_mode == "ویرایش پست موجود":
        if not posts:
            st.info("هنوز پستی ثبت نشده است.")
        else:
            post_map = {f"#{p['id']} | {p['post_type']} | {p['title']}": p['id'] for p in posts}
            post_label = st.selectbox("انتخاب پست", list(post_map), key="post_select")
            selected_post = get_media_post(post_map[post_label])
    if post_mode == "ساخت پست جدید" or selected_post:
        suffix = str(selected_post["id"] if selected_post else "new")
        with st.form(f"post_form_{suffix}"):
            type_val = selected_post["post_type"] if selected_post and selected_post["post_type"] in POST_TYPES else POST_TYPES[0]
            post_type = st.selectbox("نوع پست", POST_TYPES, index=POST_TYPES.index(type_val), key=f"post_type_{suffix}")
            title = st.text_input("تیتر (حداکثر ۷ کلمه)", value=selected_post["title"] if selected_post else "", key=f"post_title_{suffix}")
            body = st.text_area("بدنه پست (خطوط کوتاه و مستند)", value=selected_post["body"] if selected_post else "", height=240, key=f"post_body_{suffix}")
            decision_line = st.text_input("جمله پایانی خط تصمیم", value=selected_post["decision_line"] if selected_post else "", key=f"post_decision_{suffix}", placeholder="مثلاً: خط تصمیم: قبل از خرید، دو استعلام هم‌مشخصات بگیرید.")
            sources = st.text_area("منابع/پیوندها (برای شایعه‌سنجی الزامی)", value=selected_post["sources"] if selected_post else "", height=70, key=f"post_sources_{suffix}")
            status_val = selected_post["status"] if selected_post and selected_post["status"] in STATUSES else "پیش‌نویس"
            post_status = st.selectbox("وضعیت انتشار", STATUSES, index=STATUSES.index(status_val), key=f"post_status_{suffix}")
            save_post = st.form_submit_button("ذخیره پست", use_container_width=True)
        if save_post:
            title_words = len(title.strip().split())
            rendered_post = "\n".join([title.strip(), body.strip(), f"خط تصمیم: {decision_line.strip()}"]).strip()
            line_count = len(rendered_post.splitlines())
            validation_errors = []
            if not title.strip(): validation_errors.append("تیتر خالی است.")
            if title_words > 7: validation_errors.append(f"تیتر {title_words} کلمه است؛ حداکثر ۷ کلمه مجاز است.")
            if not body.strip(): validation_errors.append("بدنه پست خالی است.")
            if not decision_line.strip(): validation_errors.append("جمله خط تصمیم الزامی است.")
            if line_count > 12: validation_errors.append(f"متن نهایی {line_count} خط دارد؛ حداکثر ۱۲ خط مجاز است.")
            if post_type == "داده در برابر شایعه" and not sources.strip(): validation_errors.append("برای پست داده در برابر شایعه، منبع/پیوند الزامی است.")
            if validation_errors:
                for error in validation_errors: st.error(error)
            else:
                data = {"post_type": post_type, "title": title.strip(), "body": body.strip(), "decision_line": decision_line.strip().removeprefix("خط تصمیم:").strip(), "sources": sources.strip(), "status": post_status}
                saved_id = save_media_post(data, selected_post["id"] if selected_post else None)
                export_manual_documents()
                st.success(f"پست شماره {saved_id} ذخیره شد ({title_words} کلمه در تیتر، {line_count} خط).")
                st.rerun()
    if posts:
        st.markdown("#### پیش‌نمایش پست‌ها")
        for post in posts:
            rendered = f"**{post['title']}**\n\n{post['body']}\n\n**خط تصمیم:** {post['decision_line']}"
            with st.expander(f"#{post['id']} | {post['post_type']} | {post['status']} | {post['title']}"):
                st.markdown(rendered)
                if post["sources"]:
                    st.caption(f"منابع: {post['sources']}")
                count_words = len(post["title"].split())
                count_lines = len("\n".join([post["title"], post["body"].strip(), f"خط تصمیم: {post['decision_line']}"]).strip().splitlines())
                if count_words <= 7 and count_lines <= 12 and post["decision_line"].strip():
                    st.success(f"از نظر قالب: معتبر ({count_words} کلمه در تیتر، {count_lines} خط)")
                else:
                    st.warning(f"نیاز به اصلاح قالب ({count_words} کلمه در تیتر، {count_lines} خط)")
        delete_post_id = st.selectbox("برای حذف (اختیاری) یک پست را انتخاب کن", [p["id"] for p in posts], format_func=lambda i: next(f"#{p['id']} — {p['title']}" for p in posts if p['id'] == i), key="delete_post_id")
        if st.checkbox("حذف این پست را تأیید می‌کنم", key="confirm_delete_post") and st.button("حذف پست انتخاب‌شده", key="delete_post_button"):
            delete_media_post(int(delete_post_id)); export_manual_documents(); st.success("پست حذف شد."); st.rerun()
    show_manual_export_buttons()

elif page == "وضعیت داده و اجراها":
    st.subheader("کیفیت داده و سابقه اجرا")
    if raw_observations:
        quality = []
        for row in raw_observations:
            if not 10_000 <= int(row["price_toman_per_kg"]) <= 1_000_000:
                quality.append({"severity":"خطا", "date":row["market_date"], "source_id":row["source_id"], "message":f"قیمت خارج از دامنه کنترل: {row['price_toman_per_kg']}"})
            if row.get("date_basis") == "collection":
                quality.append({"severity":"بررسی", "date":row["market_date"], "source_id":row["source_id"], "message":"تاریخ از زمان جمع‌آوری آمده، نه تاریخ اعلام‌شده در صفحه."})
        ids = sorted({row["source_id"] for row in raw_observations})
        for source_id in ids:
            src = [row for row in raw_observations if row["source_id"] == source_id]
            dates = sorted({r["market_date"] for r in src})
            st.write(f"**{source_label(source_id)}:** {len(src)} رکورد خام، {len(dates)} تاریخ متمایز، از {dates[0]} تا {dates[-1]}.")
        if quality:
            st.dataframe(pd.DataFrame(quality).rename(columns={"severity":"سطح", "date":"تاریخ", "source_id":"منبع", "message":"ملاحظه"}), use_container_width=True, hide_index=True)
        else:
            st.success("هیچ قیمت خارج از دامنه ساده ۱۰٬۰۰۰ تا ۱٬۰۰۰٬۰۰۰ تومان در رکوردهای فعلی پیدا نشد. این کنترل دامنه، تضمین کامل صحت منبع نیست.")
        raw_view = pd.DataFrame(raw_observations)
        raw_view["source_id"] = raw_view["source_id"].map(source_label)
        raw_view["price_toman_per_kg"] = raw_view["price_toman_per_kg"].map(fmt_price)
        raw_view = raw_view.rename(columns={"source_id":"منبع", "market_date":"تاریخ بازار", "price_toman_per_kg":"قیمت (تومان/کیلو)", "record_type":"نوع رکورد", "date_basis":"مبنای تاریخ", "collected_at":"زمان جمع‌آوری", "source_url":"نشانی منبع", "raw_text":"متن خام"})
        display_cols = [c for c in ["منبع", "تاریخ بازار", "قیمت (تومان/کیلو)", "نوع رکورد", "مبنای تاریخ", "زمان جمع‌آوری", "نشانی منبع", "متن خام"] if c in raw_view]
        st.dataframe(raw_view[display_cols].sort_values("تاریخ بازار", ascending=False), use_container_width=True, hide_index=True)
    st.markdown("#### ۲۰ اجرای اخیر")
    runs = load_recent_runs(DATABASE_PATH, 20)
    if runs:
        run_df = pd.DataFrame(runs)
        rename = {"id":"شناسه اجرا", "started_at":"شروع", "finished_at":"پایان", "status":"وضعیت اجرا", "sources_succeeded":"منابع موفق", "sources_failed":"منابع ناموفق", "source_id":"منبع", "source_status":"وضعیت منبع", "archive_records":"رکورد آرشیو", "snapshot_records":"snapshot", "source_detail":"جزئیات"}
        available = [c for c in ["id", "started_at", "finished_at", "status", "sources_succeeded", "sources_failed", "source_id", "source_status", "archive_records", "snapshot_records", "source_detail"] if c in run_df]
        run_df = run_df[available].rename(columns=rename)
        if "منبع" in run_df: run_df["منبع"] = run_df["منبع"].map(lambda v: source_label(v) if pd.notna(v) else "—")
        st.dataframe(run_df, use_container_width=True, hide_index=True)
    paths = export_manual_documents()
    st.caption(f"خروجی‌های دفتر دستی هنگام ذخیره به‌روزرسانی می‌شوند: {paths[0]} و {paths[1]}.")

# Footer with system properties
st.divider()
st.caption("نسخه محلی داشبورد | آمار به‌صورت برنامه‌نویسی‌شده محاسبه می‌شود؛ تحلیل علّی و توصیه اقتصادی فقط با قضاوت و استناد انسانی ثبت می‌شود.")
