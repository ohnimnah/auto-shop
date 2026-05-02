import unittest

from marketplace.buyma.validate import (
    extract_actual_measure_map,
    extract_actual_size_rows,
    is_blank_or_zero_measure_value,
    pick_measure_value_by_label,
)


class BuymaActualSizeValueTests(unittest.TestCase):
    def test_zero_measure_values_are_treated_as_blank(self):
        self.assertTrue(is_blank_or_zero_measure_value(""))
        self.assertTrue(is_blank_or_zero_measure_value("0"))
        self.assertTrue(is_blank_or_zero_measure_value("0.0"))
        self.assertFalse(is_blank_or_zero_measure_value("32"))

    def test_extract_measure_map_skips_zero_values(self):
        result = extract_actual_measure_map("waist 0 hip 38")

        self.assertNotIn("waist", result)
        self.assertEqual(result.get("hip"), "38")

    def test_extract_size_rows_skips_zero_values(self):
        result = extract_actual_size_rows("FREE: waist 0, hip 38")

        self.assertNotIn("waist", result["FREE"])
        self.assertEqual(result["FREE"].get("hip"), "38")

    def test_pick_measure_value_skips_zero_values(self):
        result = pick_measure_value_by_label("waist", {"waist": "0"})

        self.assertEqual(result, "")

    def test_pick_measure_value_matches_buyma_japanese_bottom_labels(self):
        measures = {
            "허리단면": "32",
            "엉덩이단면": "45",
            "밑위": "28",
            "밑아래": "8",
            "허벅지단면": "29",
            "밑단단면": "27",
        }

        self.assertEqual(pick_measure_value_by_label("ウエスト", measures), "32")
        self.assertEqual(pick_measure_value_by_label("ヒップ", measures), "45")
        self.assertEqual(pick_measure_value_by_label("股上", measures), "28")
        self.assertEqual(pick_measure_value_by_label("股下", measures), "8")
        self.assertEqual(pick_measure_value_by_label("もも周り", measures), "29")
        self.assertEqual(pick_measure_value_by_label("すそ周り", measures), "27")


if __name__ == "__main__":
    unittest.main()
