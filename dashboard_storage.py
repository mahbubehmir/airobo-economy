"""Manual economic journal and media-post persistence for the Streamlit UI."""
from __future__ import annotations
import sqlite3
from datetime import datetime
from contextlib import contextmanager
from pathlib import Path
from zoneinfo import ZoneInfo
from typing import Any

from config import DATABASE_PATH, OUTPUT_DIR

TEHRAN = ZoneInfo("Asia/Tehran")


def _now() -> str:
    return datetime.now(TEHRAN).isoformat(timespec="seconds")


def _connect() -> sqlite3.Connection:
    path = Path(DATABASE_PATH)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout=30000")
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


@contextmanager
def _managed_connection():
    conn = _connect()
    try:
        with conn:
            yield conn
    finally:
        conn.close()


def ensure_manual_tables() -> None:
    with _managed_connection() as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS economic_journal (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_date TEXT NOT NULL,
            event_type TEXT NOT NULL,
            title TEXT NOT NULL,
            what_happened TEXT NOT NULL,
            why_hypothesis TEXT NOT NULL DEFAULT '',
            evidence_for TEXT NOT NULL DEFAULT '',
            evidence_against TEXT NOT NULL DEFAULT '',
            effect_builder TEXT NOT NULL DEFAULT '',
            effect_consumer TEXT NOT NULL DEFAULT '',
            effect_investor TEXT NOT NULL DEFAULT '',
            decision_implication TEXT NOT NULL DEFAULT '',
            confidence TEXT NOT NULL DEFAULT 'متوسط',
            references_text TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT 'پیش‌نویس',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_economic_journal_date ON economic_journal(event_date);
        CREATE TABLE IF NOT EXISTS media_posts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            post_type TEXT NOT NULL,
            title TEXT NOT NULL,
            body TEXT NOT NULL,
            decision_line TEXT NOT NULL,
            sources TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT 'پیش‌نویس',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_media_posts_type ON media_posts(post_type);
        """)


def list_economic_entries() -> list[dict[str, Any]]:
    with _managed_connection() as conn:
        rows = conn.execute("SELECT * FROM economic_journal ORDER BY event_date DESC, id DESC").fetchall()
    return [dict(row) for row in rows]


def get_economic_entry(entry_id: int) -> dict[str, Any] | None:
    with _managed_connection() as conn:
        row = conn.execute("SELECT * FROM economic_journal WHERE id=?", (entry_id,)).fetchone()
    return dict(row) if row else None


def save_economic_entry(data: dict[str, Any], entry_id: int | None = None) -> int:
    now = _now()
    fields = [
        "event_date", "event_type", "title", "what_happened", "why_hypothesis",
        "evidence_for", "evidence_against", "effect_builder", "effect_consumer",
        "effect_investor", "decision_implication", "confidence", "references_text", "status",
    ]
    values = [str(data.get(field, "") or "") for field in fields]
    with _managed_connection() as conn:
        if entry_id is None:
            placeholders = ",".join("?" for _ in fields)
            cursor = conn.execute(
                f"INSERT INTO economic_journal({','.join(fields)},created_at,updated_at) VALUES({placeholders},?,?)",
                (*values, now, now),
            )
            return int(cursor.lastrowid)
        assignments = ",".join(f"{field}=?" for field in fields)
        conn.execute(f"UPDATE economic_journal SET {assignments},updated_at=? WHERE id=?", (*values, now, entry_id))
        return entry_id


def delete_economic_entry(entry_id: int) -> None:
    with _managed_connection() as conn:
        conn.execute("DELETE FROM economic_journal WHERE id=?", (entry_id,))


def list_media_posts() -> list[dict[str, Any]]:
    with _managed_connection() as conn:
        rows = conn.execute("SELECT * FROM media_posts ORDER BY updated_at DESC, id DESC").fetchall()
    return [dict(row) for row in rows]


def get_media_post(post_id: int) -> dict[str, Any] | None:
    with _managed_connection() as conn:
        row = conn.execute("SELECT * FROM media_posts WHERE id=?", (post_id,)).fetchone()
    return dict(row) if row else None


def save_media_post(data: dict[str, Any], post_id: int | None = None) -> int:
    now = _now()
    fields = ["post_type", "title", "body", "decision_line", "sources", "status"]
    values = [str(data.get(field, "") or "") for field in fields]
    with _managed_connection() as conn:
        if post_id is None:
            placeholders = ",".join("?" for _ in fields)
            cursor = conn.execute(
                f"INSERT INTO media_posts({','.join(fields)},created_at,updated_at) VALUES({placeholders},?,?)",
                (*values, now, now),
            )
            return int(cursor.lastrowid)
        assignments = ",".join(f"{field}=?" for field in fields)
        conn.execute(f"UPDATE media_posts SET {assignments},updated_at=? WHERE id=?", (*values, now, post_id))
        return post_id


def delete_media_post(post_id: int) -> None:
    with _managed_connection() as conn:
        conn.execute("DELETE FROM media_posts WHERE id=?", (post_id,))


def render_economic_markdown(entries: list[dict[str, Any]]) -> str:
    lines = ["# دفتر تحلیل اقتصادی قیمت میلگرد", "", "این دفتر با تحلیل دستی نوشته شده است؛ متن‌ها توسط مدل زبانی تولید نشده‌اند.", ""]
    if not entries:
        lines.append("هنوز تحلیلی ثبت نشده است.")
    for item in entries:
        lines.extend([
            f"## {item['event_date']} — {item['title']}",
            f"- نوع رویداد: {item['event_type']}",
            f"- وضعیت: {item['status']} | اطمینان: {item['confidence']}",
            "", "### چه شد؟", item["what_happened"] or "—",
            "", "### چرا ممکن است رخ داده باشد؟", item["why_hypothesis"] or "—",
            "", "### شواهد موافق", item["evidence_for"] or "—",
            "", "### شواهد مخالف / توضیح جایگزین", item["evidence_against"] or "—",
            "", "### پیامد برای سازنده", item["effect_builder"] or "—",
            "", "### پیامد برای مصرف‌کننده نهایی", item["effect_consumer"] or "—",
            "", "### پیامد برای سرمایه‌گذار خرد", item["effect_investor"] or "—",
            "", "### خط تصمیم", item["decision_implication"] or "—",
            "", "### منابع", item["references_text"] or "—", "", "---", "",
        ])
    return "\n".join(lines)


def render_posts_markdown(posts: list[dict[str, Any]]) -> str:
    lines = ["# پست‌های رسانه‌ای رصدخانه قیمت میلگرد", "", "پست‌ها بر اساس داده ثبت‌شده و توسط نویسنده انسانی تنظیم می‌شوند.", ""]
    if not posts:
        lines.append("هنوز پستی ثبت نشده است.")
    for post in posts:
        lines.extend([
            f"## {post['title']}",
            f"- نوع: {post['post_type']} | وضعیت: {post['status']}",
            "", post["body"].strip(), f"خط تصمیم: {post['decision_line'].strip()}",
            "", f"منابع: {post['sources'] or '—'}", "", "---", "",
        ])
    return "\n".join(lines)


def export_manual_documents() -> tuple[Path, Path]:
    output = Path(OUTPUT_DIR)
    output.mkdir(parents=True, exist_ok=True)
    journal_path = output / "economic_journal.md"
    posts_path = output / "media_posts.md"
    journal_path.write_text(render_economic_markdown(list_economic_entries()), encoding="utf-8")
    posts_path.write_text(render_posts_markdown(list_media_posts()), encoding="utf-8")
    return journal_path, posts_path
