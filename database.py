"""SQLite persistence layer. All collected observations carry run provenance."""
from __future__ import annotations
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
from typing import Iterable

from models import PriceRecord, SourceFailure, SourceResult

TEHRAN = ZoneInfo("Asia/Tehran")

SCHEMA = """
PRAGMA foreign_keys=ON;
CREATE TABLE IF NOT EXISTS collection_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    status TEXT NOT NULL DEFAULT 'running',
    sources_succeeded INTEGER NOT NULL DEFAULT 0,
    sources_failed INTEGER NOT NULL DEFAULT 0,
    observations_inserted INTEGER NOT NULL DEFAULT 0,
    message TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS source_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id INTEGER NOT NULL REFERENCES collection_runs(id) ON DELETE CASCADE,
    source_id TEXT NOT NULL,
    source_url TEXT NOT NULL,
    status TEXT NOT NULL,
    archive_records INTEGER NOT NULL DEFAULT 0,
    snapshot_records INTEGER NOT NULL DEFAULT 0,
    detail TEXT NOT NULL DEFAULT '',
    UNIQUE(run_id, source_id)
);
CREATE TABLE IF NOT EXISTS price_observations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_id TEXT NOT NULL,
    product_key TEXT NOT NULL,
    product_name TEXT NOT NULL,
    size_mm INTEGER NOT NULL,
    standard TEXT NOT NULL,
    manufacturer TEXT NOT NULL,
    price_toman_per_kg INTEGER NOT NULL CHECK(price_toman_per_kg > 0),
    market_date TEXT NOT NULL,
    market_date_label TEXT NOT NULL,
    date_basis TEXT NOT NULL CHECK(date_basis IN ('source','collection')),
    record_type TEXT NOT NULL CHECK(record_type IN ('archive','snapshot')),
    collected_at TEXT NOT NULL,
    run_id INTEGER REFERENCES collection_runs(id),
    source_url TEXT NOT NULL,
    raw_text TEXT NOT NULL DEFAULT '',
    source_sequence INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_price_series ON price_observations(product_key, source_id, market_date);
CREATE INDEX IF NOT EXISTS idx_price_runs ON price_observations(run_id, source_id);
CREATE INDEX IF NOT EXISTS idx_price_collected ON price_observations(collected_at);
"""


def now_iso() -> str:
    return datetime.now(TEHRAN).isoformat(timespec="seconds")


@contextmanager
def connect(db_path: Path | str):
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), timeout=30)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.executescript(SCHEMA)
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def create_run(db_path: Path | str) -> int:
    with connect(db_path) as conn:
        cursor = conn.execute(
            "INSERT INTO collection_runs(started_at,status) VALUES(?, 'running')",
            (now_iso(),),
        )
        return int(cursor.lastrowid)


def _archive_exists(conn: sqlite3.Connection, record: PriceRecord) -> bool:
    row = conn.execute(
        """SELECT 1 FROM price_observations
           WHERE source_id=? AND product_key=? AND market_date=? AND price_toman_per_kg=? AND record_type='archive'
           LIMIT 1""",
        (record.source_id, record.product_key, record.market_date, record.price_toman_per_kg),
    ).fetchone()
    return row is not None


def save_source_result(db_path: Path | str, run_id: int, result: SourceResult, collected_at: str | None = None) -> tuple[int, int]:
    collected_at = collected_at or now_iso()
    archive_count = snapshot_count = inserted_count = 0
    with connect(db_path) as conn:
        for record in result.records:
            if record.record_type == "archive" and _archive_exists(conn, record):
                # Re-fetching the same historic chart must not create duplicate backfill rows.
                continue
            conn.execute(
                """INSERT INTO price_observations(
                    source_id, product_key, product_name, size_mm, standard, manufacturer,
                    price_toman_per_kg, market_date, market_date_label, date_basis, record_type,
                    collected_at, run_id, source_url, raw_text, source_sequence
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    record.source_id, record.product_key, record.product_name, record.size_mm,
                    record.standard, record.manufacturer, record.price_toman_per_kg,
                    record.market_date, record.market_date_label, record.date_basis,
                    record.record_type, collected_at, run_id, record.source_url, record.raw_text,
                    record.source_sequence,
                ),
            )
            inserted_count += 1
            if record.record_type == "archive":
                archive_count += 1
            else:
                snapshot_count += 1
        conn.execute(
            """INSERT INTO source_runs(run_id, source_id, source_url, status, archive_records,
                       snapshot_records, detail) VALUES(?,?,?,?,?,?,?)
               ON CONFLICT(run_id, source_id) DO UPDATE SET
                   status=excluded.status, archive_records=excluded.archive_records,
                   snapshot_records=excluded.snapshot_records, detail=excluded.detail""",
            (run_id, result.source_id, result.source_url, "success", archive_count, snapshot_count, result.note),
        )
        conn.execute(
            "UPDATE collection_runs SET observations_inserted=observations_inserted+? WHERE id=?",
            (inserted_count, run_id),
        )
    return inserted_count, archive_count


def save_source_failure(db_path: Path | str, run_id: int, failure: SourceFailure) -> None:
    with connect(db_path) as conn:
        conn.execute(
            """INSERT INTO source_runs(run_id, source_id, source_url, status, detail)
               VALUES(?,?,?,?,?)
               ON CONFLICT(run_id, source_id) DO UPDATE SET
                 status=excluded.status, detail=excluded.detail""",
            (run_id, failure.source_id, failure.source_url, "failed", failure.error),
        )


def finish_run(db_path: Path | str, run_id: int, succeeded: int, failed: int, message: str = "") -> None:
    status = "success" if failed == 0 else ("partial" if succeeded else "failed")
    with connect(db_path) as conn:
        conn.execute(
            """UPDATE collection_runs SET finished_at=?, status=?, sources_succeeded=?,
               sources_failed=?, message=? WHERE id=?""",
            (now_iso(), status, succeeded, failed, message, run_id),
        )


def load_observations(db_path: Path | str) -> list[dict]:
    with connect(db_path) as conn:
        rows = conn.execute(
            """SELECT * FROM price_observations
               WHERE product_key='rebar_14_a3_zobahan_esfahan'
               ORDER BY source_id, market_date, source_sequence, collected_at, id"""
        ).fetchall()
    return [dict(row) for row in rows]


def load_recent_runs(db_path: Path | str, limit: int = 20) -> list[dict]:
    with connect(db_path) as conn:
        rows = conn.execute(
            """SELECT r.*, s.source_id, s.source_url, s.status AS source_status,
                      s.archive_records, s.snapshot_records, s.detail AS source_detail
               FROM collection_runs r LEFT JOIN source_runs s ON s.run_id=r.id
               ORDER BY r.id DESC LIMIT ?""",
            (limit,),
        ).fetchall()
    return [dict(row) for row in rows]
