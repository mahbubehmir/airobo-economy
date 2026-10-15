import unittest
from analysis import daily_series, calculate_trends, calculate_divergence

class AnalysisTests(unittest.TestCase):
    def row(self, source, day, price, kind="archive", idx=1):
        return {"id": idx, "source_id": source, "product_key": "rebar_14_a3_zobahan_esfahan",
                "market_date": day, "price_toman_per_kg": price, "record_type": kind,
                "collected_at": f"{day}T10:00:00+03:30", "source_sequence": idx,
                "source_url": "https://example.invalid", "date_basis": "source"}

    def test_trend_percent(self):
        series = daily_series([self.row("ahantime", "2026-10-01", 100000, idx=1),
                               self.row("ahantime", "2026-10-02", 110000, idx=2)])
        trends = calculate_trends(series)
        self.assertAlmostEqual(trends[-1]["daily_change_pct"], 10.0)

    def test_divergence_same_date(self):
        series = daily_series([self.row("ahantime", "2026-10-01", 100000, idx=1),
                               self.row("fooladsell", "2026-10-01", 110000, idx=2)])
        div = calculate_divergence(series)
        self.assertEqual(len(div), 1)
        self.assertAlmostEqual(div[0]["divergence_pct_of_mean"], 10000 / 105000 * 100)

    def test_latest_comparison_labels_different_dates(self):
        series = daily_series([self.row("ahantime", "2026-10-01", 100000, idx=1),
                               self.row("fooladsell", "2026-10-02", 110000, idx=2)])
        div = calculate_divergence(series)
        self.assertEqual(len(div), 1)
        self.assertEqual(div[0]["comparison_type"], "latest_available_different_dates")
        self.assertEqual(div[0]["ahantime_market_date"], "2026-10-01")
        self.assertEqual(div[0]["fooladsell_market_date"], "2026-10-02")

if __name__ == "__main__":
    unittest.main()
