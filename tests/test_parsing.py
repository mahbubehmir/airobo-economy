import unittest
from parsing import normalize_text, parse_jalali_date, parse_amount, is_target_rebar

class ParsingTests(unittest.TestCase):
    def test_persian_digits_and_date(self):
        self.assertEqual(normalize_text("۱۴۰۵/۰۷/۱۴"), "1405/07/14")
        self.assertEqual(parse_jalali_date("۱۴۰۵/۰۷/۱۴")[1], "1405/07/14")

    def test_price(self):
        self.assertEqual(parse_amount("۱۱۶٬۸۰۰ تومان/کیلوگرم"), 116800)

    def test_target_match(self):
        self.assertTrue(is_target_rebar("میلگرد ۱۴ آجدار A3 ذوب‌آهن اصفهان ۱۱۶٬۸۰۰ تومان/کیلو"))
        self.assertFalse(is_target_rebar("میلگرد ۱۶ آجدار A3 ذوب‌آهن اصفهان ۱۱۶٬۸۰۰ تومان/کیلو"))
        self.assertFalse(is_target_rebar("میلگرد ۱۴ آجدار A2 ذوب‌آهن اصفهان ۱۱۶٬۸۰۰ تومان/کیلو"))

if __name__ == "__main__":
    unittest.main()
