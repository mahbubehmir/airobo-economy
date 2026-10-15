"""Deterministic time-series statistics for the target rebar SKU."""
from __future__ import annotations
from collections import defaultdict
from datetime import date, timedelta
from statistics import mean, stdev
from typing import Any


def daily_series(observations: list[dict]) -> list[dict]:
    """One observation per source/date. Snapshot beats archive; latest snapshot wins."""
    groups: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for row in observations:
        groups[(row["source_id"], row["market_date"])].append(row)
    chosen = []
    for (source_id, market_date), rows in groups.items():
        snapshots = [r for r in rows if r["record_type"] == "snapshot"]
        if snapshots:
            item = max(snapshots, key=lambda r: (r["collected_at"], r["id"]))
        else:
            item = max(rows, key=lambda r: (r.get("source_sequence", 0), r["collected_at"], r["id"]))
        chosen.append(dict(item))
    return sorted(chosen, key=lambda r: (r["source_id"], r["market_date"]))


def _pct_change(old: float, new: float) -> float | None:
    if old == 0:
        return None
    return (new / old - 1.0) * 100.0


def calculate_trends(series: list[dict]) -> list[dict]:
    by_source: dict[str, list[dict]] = defaultdict(list)
    for row in series:
        by_source[row["source_id"]].append(row)
    out: list[dict] = []
    for source_id, rows in by_source.items():
        rows.sort(key=lambda r: r["market_date"])
        for idx, row in enumerate(rows):
            previous = rows[idx - 1] if idx else None
            week_target = date.fromisoformat(row["market_date"]) - timedelta(days=7)
            prior_week = [r for r in rows[:idx] if date.fromisoformat(r["market_date"]) <= week_target]
            week_reference = prior_week[-1] if prior_week else None
            out.append({
                "source_id": source_id,
                "market_date": row["market_date"],
                "price_toman_per_kg": int(row["price_toman_per_kg"]),
                "daily_change_pct": _pct_change(previous["price_toman_per_kg"], row["price_toman_per_kg"]) if previous else None,
                "daily_from_date": previous["market_date"] if previous else None,
                "weekly_change_pct": _pct_change(week_reference["price_toman_per_kg"], row["price_toman_per_kg"]) if week_reference else None,
                "weekly_from_date": week_reference["market_date"] if week_reference else None,
                "source_url": row["source_url"],
                "record_type": row["record_type"],
                "date_basis": row["date_basis"],
            })
    return sorted(out, key=lambda r: (r["market_date"], r["source_id"]))


def detect_anomalies(series: list[dict], window: int = 20, min_prior_returns: int = 5) -> list[dict]:
    """Flag a daily return outside mean +/- 2 sample SD of prior returns only.

    A row needs at least 5 preceding daily percentage changes. Baseline window is
    at most the preceding 20 returns, and excludes the tested return (no look-ahead).
    """
    by_source: dict[str, list[dict]] = defaultdict(list)
    for row in series:
        by_source[row["source_id"]].append(row)
    anomalies: list[dict] = []
    for source_id, rows in by_source.items():
        rows.sort(key=lambda r: r["market_date"])
        returns: list[tuple[dict, float]] = []
        for previous, current in zip(rows, rows[1:]):
            old = float(previous["price_toman_per_kg"])
            new = float(current["price_toman_per_kg"])
            if old <= 0:
                continue
            returns.append((current, (new / old - 1.0) * 100.0))
        for i, (row, current_return) in enumerate(returns):
            baseline_pairs = returns[max(0, i - window):i]
            if len(baseline_pairs) < min_prior_returns:
                continue
            baseline = [ret for _, ret in baseline_pairs]
            avg = mean(baseline)
            sigma = stdev(baseline)  # sample standard deviation
            deviation = abs(current_return - avg)
            if deviation > 2.0 * sigma:
                anomalies.append({
                    "source_id": source_id,
                    "market_date": row["market_date"],
                    "price_toman_per_kg": int(row["price_toman_per_kg"]),
                    "daily_change_pct": current_return,
                    "baseline_mean_pct": avg,
                    "baseline_sd_pct": sigma,
                    "threshold_low_pct": avg - 2.0 * sigma,
                    "threshold_high_pct": avg + 2.0 * sigma,
                    "prior_returns_used": len(baseline_pairs),
                    "source_url": row["source_url"],
                    "method": "current daily return outside mean +/- 2 sample SD of up to 20 prior returns",
                })
    return sorted(anomalies, key=lambda r: (r["market_date"], r["source_id"]))


def calculate_divergence(series: list[dict]) -> list[dict]:
    """Compare same-date prices, plus a clearly-labelled latest available pair.

    Same-date pairs are preferred. When source dates differ, a latest-available
    comparison is still useful operationally, but the different dates are explicit.
    """
    by_date: dict[str, dict[str, dict]] = defaultdict(dict)
    for row in series:
        by_date[row["market_date"]][row["source_id"]] = row
    out: list[dict] = []

    def make_row(label: str, date1: str, date2: str, p1: int, p2: int) -> dict:
        avg = (p1 + p2) / 2.0
        return {
            "comparison_type": label,
            "market_date": date1 if date1 == date2 else "different_source_dates",
            "ahantime_market_date": date1,
            "fooladsell_market_date": date2,
            "ahantime_price": p1,
            "fooladsell_price": p2,
            "absolute_gap_toman": abs(p1 - p2),
            "divergence_pct_of_mean": abs(p1 - p2) / avg * 100.0 if avg else None,
            "higher_source": "ahantime" if p1 > p2 else ("fooladsell" if p2 > p1 else "equal"),
            "note": "اختلاف عددی؛ شمول مالیات/شرایط عرضه/تازگی نرخ باید جداگانه کنترل شود.",
        }

    for market_date, sources in sorted(by_date.items()):
        if "ahantime" in sources and "fooladsell" in sources:
            a, b = sources["ahantime"], sources["fooladsell"]
            out.append(make_row("same_market_date", market_date, market_date,
                                int(a["price_toman_per_kg"]), int(b["price_toman_per_kg"])))

    latest = latest_per_source(series)
    if "ahantime" in latest and "fooladsell" in latest:
        a, b = latest["ahantime"], latest["fooladsell"]
        d1, d2 = a["market_date"], b["market_date"]
        if d1 != d2:
            out.append(make_row("latest_available_different_dates", d1, d2,
                                int(a["price_toman_per_kg"]), int(b["price_toman_per_kg"])))
    return sorted(out, key=lambda r: (r["comparison_type"], r["market_date"], r["ahantime_market_date"]))


def latest_per_source(series: list[dict]) -> dict[str, dict]:
    latest: dict[str, dict] = {}
    for row in series:
        if row["source_id"] not in latest or row["market_date"] > latest[row["source_id"]]["market_date"]:
            latest[row["source_id"]] = row
    return latest
