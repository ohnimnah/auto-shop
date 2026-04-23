import unittest
from unittest.mock import patch

from marketplace.buyma.category import (
    _best_fuzzy_match,
    _category_recovery_aliases,
    _category_recovery_candidates,
    build_buyma_category_plan,
)
from marketplace.buyma.standard_category import (
    StandardCategory,
    explain_standard_category_mapping,
    normalize_standard_category,
    resolve_standard_category,
    validate_buyma_category_path,
)
import standard_category_map
from standard_category_map import CategoryMappingRow


def _identity_corrector(base_category: str, product_name: str, musinsa_category: str) -> str:
    return base_category or ""


class StandardCategoryTests(unittest.TestCase):
    def test_standard_category_has_operational_resolution(self):
        self.assertGreaterEqual(len(StandardCategory), 50)

    def test_resolves_granular_outer_pants_and_shoes(self):
        cases = [
            ("다운 패딩 재킷", "OUTER_PADDING"),
            ("데님 청바지", "PANTS_DENIM"),
            ("카고 조거 팬츠", "PANTS_JOGGER"),
            ("러닝 스니커즈", "SHOES_RUNNING"),
            ("레더 로퍼", "SHOES_LOAFER"),
        ]
        for name, expected in cases:
            with self.subTest(name=name):
                std, _text = resolve_standard_category("", "", "", name)
                self.assertEqual(std.value, expected)

    def test_legacy_aliases_still_resolve(self):
        self.assertEqual(normalize_standard_category(StandardCategory.OUTER), StandardCategory.OUTER_JACKET)
        self.assertEqual(normalize_standard_category(StandardCategory.PANTS), StandardCategory.PANTS_REGULAR)
        self.assertEqual(normalize_standard_category(StandardCategory.SNEAKER), StandardCategory.SHOES_SNEAKER)

    def test_default_mapping_contains_granular_rows_for_both_genders(self):
        rows = standard_category_map.build_default_mapping_rows()
        keys = {(row.standard_category, row.gender) for row in rows}

        self.assertIn(("OUTER_PADDING", "women"), keys)
        self.assertIn(("OUTER_PADDING", "men"), keys)
        self.assertIn(("PANTS_DENIM", "women"), keys)
        self.assertIn(("SHOES_LOAFER", "men"), keys)

    def test_runtime_mapping_prefers_verified_google_sheet_rows(self):
        standard_category_map.reset_runtime_mapping_cache()
        sheet_rows = [
            CategoryMappingRow(
                "PANTS_DENIM",
                "women",
                "レディースファッション",
                "ボトムス",
                "パンツ",
                "",
                "",
                "verified",
                "",
                "",
            )
        ]
        local_rows = [
            CategoryMappingRow("PANTS_DENIM", "women", "レディースファッション", "ボトムス", "デニム・ジーパン", "", "", "json", "", "")
        ]

        with patch.object(standard_category_map, "load_mapping_rows_from_google_sheet", return_value=sheet_rows):
            with patch.object(standard_category_map, "load_mapping_rows_from_json", return_value=local_rows):
                rows = standard_category_map.get_runtime_mapping_rows()

        self.assertIn("google_sheet_verified", standard_category_map.get_runtime_mapping_source())
        match = standard_category_map.resolve_buyma_category_from_mapping(
            rows,
            standard_category=StandardCategory.PANTS_DENIM,
            gender="women",
        )
        self.assertIsNotNone(match)
        self.assertEqual(match.buyma_child_category, "パンツ")
        self.assertEqual(match.source, "verified")
        standard_category_map.reset_runtime_mapping_cache()

    def test_runtime_mapping_places_auto_seed_after_local_json(self):
        standard_category_map.reset_runtime_mapping_cache()
        sheet_rows = [
            CategoryMappingRow("PANTS_DENIM", "women", "レディースファッション", "ボトムス", "パンツ", "", "", "auto_seed", "", "")
        ]
        local_rows = [
            CategoryMappingRow("PANTS_DENIM", "women", "レディースファッション", "ボトムス", "デニム・ジーパン", "", "", "json", "", "")
        ]

        with patch.object(standard_category_map, "load_mapping_rows_from_google_sheet", return_value=sheet_rows):
            with patch.object(standard_category_map, "load_mapping_rows_from_json", return_value=local_rows):
                rows = standard_category_map.get_runtime_mapping_rows()

        self.assertIn("local_json", standard_category_map.get_runtime_mapping_source())
        self.assertIn("google_sheet_auto_seed", standard_category_map.get_runtime_mapping_source())
        match = standard_category_map.resolve_buyma_category_from_mapping(
            rows,
            standard_category=StandardCategory.PANTS_DENIM,
            gender="women",
        )
        self.assertIsNotNone(match)
        self.assertEqual(match.buyma_child_category, "デニム・ジーパン")
        self.assertEqual(match.source, "local_json")
        standard_category_map.reset_runtime_mapping_cache()

    def test_runtime_mapping_ignores_invalid_sheet_rows_and_falls_back_to_local_json(self):
        standard_category_map.reset_runtime_mapping_cache()
        invalid_sheet_rows = [
            CategoryMappingRow("PANTS_DENIM", "women", "レディースファッション", "INVALID", "", "", "", "google_sheet", "", "")
        ]
        local_rows = [
            CategoryMappingRow("PANTS_DENIM", "women", "レディースファッション", "ボトムス", "デニム・ジーパン", "", "", "json", "", "")
        ]

        with patch.object(standard_category_map, "load_mapping_rows_from_google_sheet", return_value=invalid_sheet_rows):
            with patch.object(standard_category_map, "load_mapping_rows_from_json", return_value=local_rows):
                rows = standard_category_map.get_runtime_mapping_rows()

        self.assertIn("local_json", standard_category_map.get_runtime_mapping_source())
        match = standard_category_map.resolve_buyma_category_from_mapping(
            rows,
            standard_category=StandardCategory.PANTS_DENIM,
            gender="women",
        )
        self.assertIsNotNone(match)
        self.assertEqual(match.buyma_child_category, "デニム・ジーパン")
        standard_category_map.reset_runtime_mapping_cache()

    def test_buyma_path_validator_and_diagnostics(self):
        diag = explain_standard_category_mapping(StandardCategory.PANTS_DENIM, is_mens=False)

        self.assertEqual(diag["buyma_middle"], "ボトムス")
        self.assertEqual(diag["buyma_child"], "デニム・ジーパン")
        self.assertTrue(diag["validator_passed"])
        self.assertTrue(validate_buyma_category_path(diag["buyma_parent"], diag["buyma_middle"], diag["buyma_child"]))

    def test_buyma_category_plan_uses_granular_standard_category(self):
        row = {
            "product_name_kr": "와이드 데님 청바지",
            "product_name_en": "",
            "brand": "",
            "musinsa_category_large": "여성",
            "musinsa_category_middle": "바지",
            "musinsa_category_small": "데님",
        }

        plan = build_buyma_category_plan(row, category_corrector=_identity_corrector)

        self.assertEqual(plan["standard_category"], "PANTS_DENIM")
        self.assertEqual(plan["cat2"], "ボトムス")
        self.assertEqual(plan["cat3"], "デニム・ジーパン")
        self.assertTrue(plan["category_path_valid"])

    def test_category_recovery_aliases(self):
        self.assertIn("デニム・ジーンズ", _category_recovery_aliases("デニム・ジーパン"))
        self.assertIn("スウェット", _category_recovery_aliases("スウェット・トレーナー"))

    def test_category_recovery_fuzzy_match(self):
        label, score = _best_fuzzy_match("デニム・ジーパン", ["パンツ", "デニム・ジーンズ", "スラックス"])

        self.assertEqual(label, "デニム・ジーンズ")
        self.assertGreaterEqual(score, 78)

    def test_category_recovery_candidates_same_parent(self):
        plan = {
            "cat1": "レディースファッション",
            "cat2": "ボトムス",
            "cat3": "デニム・ジーパン",
            "standard_category": "PANTS_DENIM",
        }

        middle_candidates = _category_recovery_candidates(plan, 1, parent="レディースファッション")
        child_candidates = _category_recovery_candidates(plan, 2, parent="レディースファッション", middle="ボトムス")

        self.assertIn("ボトムス", middle_candidates)
        self.assertIn("デニム・ジーパン", child_candidates)
        self.assertIn("スラックス", child_candidates)


if __name__ == "__main__":
    unittest.main()
