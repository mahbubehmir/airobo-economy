import tempfile
import unittest
from pathlib import Path
import dashboard_storage as ds

class DashboardStorageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.old_db, self.old_output = ds.DATABASE_PATH, ds.OUTPUT_DIR
        root = Path(self.temp.name)
        ds.DATABASE_PATH = root / "test.sqlite3"
        ds.OUTPUT_DIR = root / "output"
        ds.ensure_manual_tables()

    def tearDown(self):
        ds.DATABASE_PATH, ds.OUTPUT_DIR = self.old_db, self.old_output
        self.temp.cleanup()

    def test_save_economic_entry_and_export(self):
        entry_id = ds.save_economic_entry({
            "event_date":"2026-10-14", "event_type":"رشد/افت قیمت", "title":"تست ثبت تحلیل",
            "what_happened":"قیمت ۲ درصد تغییر کرد.", "why_hypothesis":"فرضیه آزمایشی",
            "evidence_for":"منبع A", "evidence_against":"منبع B", "effect_builder":"اثر",
            "effect_consumer":"اثر", "effect_investor":"اثر", "decision_implication":"مقایسه مجدد",
            "confidence":"متوسط", "references_text":"https://example.invalid", "status":"پیش‌نویس"})
        self.assertEqual(len(ds.list_economic_entries()), 1)
        self.assertEqual(ds.get_economic_entry(entry_id)["title"], "تست ثبت تحلیل")
        paths = ds.export_manual_documents()
        self.assertTrue(paths[0].exists())
        self.assertIn("تست ثبت تحلیل", paths[0].read_text(encoding="utf-8"))

    def test_save_media_post(self):
        post_id = ds.save_media_post({"post_type":"داده در برابر شایعه", "title":"تست تیتر", "body":"متن", "decision_line":"قبل از خرید بررسی کنید", "sources":"منبع", "status":"پیش‌نویس"})
        self.assertEqual(ds.get_media_post(post_id)["post_type"], "داده در برابر شایعه")
        paths = ds.export_manual_documents()
        self.assertTrue(paths[1].exists())
        self.assertIn("تست تیتر", paths[1].read_text(encoding="utf-8"))

if __name__ == "__main__":
    unittest.main()
