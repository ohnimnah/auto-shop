import unittest

from marketplace.buyma.validate import (
    extract_actual_measure_map,
    extract_actual_size_rows,
    is_blank_or_zero_measure_value,
    is_zero_measure_value,
    pick_measure_value_by_label,
)


class BuymaActualSizeValueTests(unittest.TestCase):
    def test_blank_and_zero_checks_are_separate(self):
        self.assertTrue(is_blank_or_zero_measure_value(""))
        self.assertTrue(is_blank_or_zero_measure_value("0"))
        self.assertFalse(is_zero_measure_value(""))
        self.assertTrue(is_zero_measure_value("0"))
        self.assertTrue(is_zero_measure_value("0.0"))
        self.assertFalse(is_zero_measure_value("32"))

    def test_extract_measure_map_keeps_zero_for_input_stage_skip(self):
        result = extract_actual_measure_map("waist 0 hip 38")

        self.assertEqual(result.get("waist"), "0")
        self.assertEqual(result.get("hip"), "38")

    def test_extract_size_rows_keeps_zero_for_input_stage_skip(self):
        result = extract_actual_size_rows("FREE: waist 0, hip 38")

        self.assertEqual(result["FREE"].get("waist"), "0")
        self.assertEqual(result["FREE"].get("hip"), "38")

    def test_pick_measure_value_can_return_zero_for_zero_skip_log(self):
        result = pick_measure_value_by_label("waist", {"waist": "0"})

        self.assertEqual(result, "0")

    def test_pick_measure_value_matches_korean_labels_from_japanese_keys(self):
        measure_map = {
            "肩幅": "45",
            "身幅": "55",
            "着丈": "70",
            "袖丈": "60",
        }

        self.assertEqual(pick_measure_value_by_label("어깨너비", measure_map), "45")
        self.assertEqual(pick_measure_value_by_label("가슴단면", measure_map), "55")
        self.assertEqual(pick_measure_value_by_label("총장", measure_map), "70")
        self.assertEqual(pick_measure_value_by_label("소매길이", measure_map), "60")

    def test_extract_measure_map_parses_plain_korean_actual_size_text(self):
        result = extract_actual_measure_map("총장 70 어깨너비 45 가슴단면 55 소매길이 60")

        self.assertEqual(result["총장"], "70")
        self.assertEqual(result["어깨너비"], "45")
        self.assertEqual(result["가슴단면"], "55")
        self.assertEqual(result["소매길이"], "60")

    def test_extract_measure_map_parses_plain_japanese_actual_size_text(self):
        result = extract_actual_measure_map("着丈 70 肩幅 45 身幅 55 袖丈 60")

        self.assertEqual(result["着丈"], "70")
        self.assertEqual(result["肩幅"], "45")
        self.assertEqual(result["身幅"], "55")
        self.assertEqual(result["袖丈"], "60")

    def test_extract_size_rows_parses_per_size_actual_size_text(self):
        result = extract_actual_size_rows("M: 총장 70, 어깨너비 45, 가슴단면 55 | L: 총장 72, 어깨너비 46, 가슴단면 57")

        self.assertEqual(result["M"]["총장"], "70")
        self.assertEqual(result["M"]["어깨너비"], "45")
        self.assertEqual(result["M"]["가슴단면"], "55")
        self.assertEqual(result["L"]["총장"], "72")
        self.assertEqual(result["L"]["어깨너비"], "46")
        self.assertEqual(result["L"]["가슴단면"], "57")

    def test_pick_measure_value_matches_buyma_japanese_bottom_labels(self):
        measures = {
            "허리 단면": "32",
            "엉덩이 단면": "45",
            "밑위 길이": "28",
            "밑 아래": "8",
            "허벅지 단면": "29",
            "밑단 단면": "27",
        }

        self.assertEqual(pick_measure_value_by_label("ウエスト", measures), "32")
        self.assertEqual(pick_measure_value_by_label("ヒップ", measures), "45")
        self.assertEqual(pick_measure_value_by_label("股上", measures), "28")
        self.assertEqual(pick_measure_value_by_label("股下", measures), "8")
        self.assertEqual(pick_measure_value_by_label("もも周り", measures), "29")
        self.assertEqual(pick_measure_value_by_label("すそ周り", measures), "27")


if __name__ == "__main__":
    unittest.main()
