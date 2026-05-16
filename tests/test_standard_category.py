import unittest
from tempfile import TemporaryDirectory
from unittest.mock import patch

from marketplace.buyma.category import (
    _best_fuzzy_match,
    _category_recovery_aliases,
    _category_recovery_candidates,
    append_category_selection_event,
    build_buyma_category_plan,
    infer_buyma_category,
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
import json
from pathlib import Path


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
            ("From knee socks", "ACC_SOCKS"),
            ("SPORTY TRACK RIBBON BIKINI", "SWIMWEAR"),
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

    def test_append_category_selection_event_writes_jsonl(self):
        row = {
            "row_num": 969,
            "product_name_en": "From knee socks",
            "brand_en": "BNFROM",
            "musinsa_category_large": "여성",
            "musinsa_category_middle": "소품",
            "musinsa_category_small": "양말/레그웨어",
        }
        diag = {
            "category_selection_success": True,
            "final_result": "success",
            "standard_category": "ACC_SOCKS",
            "target_buyma_parent_category": "レディースファッション",
            "target_buyma_middle_category": "インナー・ルームウェア",
            "target_buyma_child_category": "タイツ・ソックス",
            "actual_selected_parent_category": "レディースファッション",
            "actual_selected_middle_category": "インナー・ルームウェア",
            "actual_selected_child_category": "タイツ・ソックス",
            "cat_source": "시트(W/X/Y)+stdmap",
            "mapping_table_used": True,
        }
        with TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "category_selection_events.jsonl"
            append_category_selection_event(row, diag, log_path=path)
            data = json.loads(path.read_text(encoding="utf-8").strip())

        self.assertEqual(data["row"], 969)
        self.assertEqual(data["standard_category"], "ACC_SOCKS")
        self.assertEqual(data["musinsa_category"], "여성 / 소품 / 양말/레그웨어")
        self.assertEqual(data["target_buyma_category"], "レディースファッション > インナー・ルームウェア > タイツ・ソックス")
        self.assertTrue(data["success"])

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

    def test_buyma_category_plan_maps_sports_outer_to_outer_jacket(self):
        row = {
            "product_name_kr": "",
            "product_name_en": "URBAN SUEDE JUMPER",
            "brand": "GLOWNY",
            "musinsa_category_large": "여성",
            "musinsa_category_middle": "스포츠/레저",
            "musinsa_category_small": "아우터",
        }

        plan = build_buyma_category_plan(row, category_corrector=_identity_corrector)

        self.assertEqual(plan["standard_category"], "OUTER_JACKET")
        self.assertEqual(plan["cat2"], "アウター")
        self.assertEqual(plan["cat3"], "ジャケット")

    def test_buyma_category_plan_maps_bikini_to_swimwear(self):
        row = {
            "product_name_kr": "SPORTY TRACK RIBBON BIKINI",
            "product_name_en": "",
            "brand": "BNFROM",
            "musinsa_category_large": "여성",
            "musinsa_category_middle": "스포츠/레저",
            "musinsa_category_small": "수영복/비치웨어",
        }

        plan = build_buyma_category_plan(row, category_corrector=_identity_corrector)

        self.assertEqual(plan["standard_category"], "SWIMWEAR")
        self.assertEqual(plan["cat2"], "水着・ビーチグッズ")
        self.assertEqual(plan["cat3"], "ビキニ")
        self.assertTrue(plan["category_path_valid"])
        self.assertTrue(plan["category_path_valid"])

    def test_buyma_category_plan_maps_sports_bag_to_crossbody_bag(self):
        row = {
            "product_name_kr": "맨티스 2 웨이스트 팩 - 24K",
            "product_name_en": "",
            "brand": "ARCTERYX",
            "musinsa_category_large": "남성",
            "musinsa_category_middle": "스포츠/레저",
            "musinsa_category_small": "가방",
        }

        plan = build_buyma_category_plan(row, category_corrector=_identity_corrector)

        self.assertEqual(plan["standard_category"], "BAG_CROSSBODY")
        self.assertEqual(plan["cat1"], "メンズファッション")
        self.assertEqual(plan["cat2"], "バッグ・カバン")
        self.assertEqual(plan["cat3"], "ショルダーバッグ")
        self.assertTrue(plan["category_path_valid"])

    def test_buyma_category_plan_maps_digital_to_tech_accessory(self):
        row = {
            "product_name_kr": "",
            "product_name_en": "GRAPHIC TEE AIRPODS CASE",
            "brand": "BRAND",
            "musinsa_category_large": "여성",
            "musinsa_category_middle": "디지털/가전",
            "musinsa_category_small": "",
        }

        plan = build_buyma_category_plan(row, category_corrector=_identity_corrector)

        self.assertEqual(plan["standard_category"], "TECH_ACCESSORY")
        self.assertEqual(plan["cat2"], "スマホケース・テックアクセサリー")
        self.assertEqual(plan["cat3"], "テックアクセサリー")
        self.assertTrue(plan["category_path_valid"])

    def test_buyma_category_plan_keeps_blouse_out_of_tshirt(self):
        row = {
            "product_name_kr": "",
            "product_name_en": "LACE SHORT SLEEVE BLOUSE",
            "brand": "GLOWNY",
            "musinsa_category_large": "여성",
            "musinsa_category_middle": "상의",
            "musinsa_category_small": "반팔 블라우스",
        }

        plan = build_buyma_category_plan(row, category_corrector=_identity_corrector)

        self.assertEqual(plan["standard_category"], "TOP_BLOUSE")
        self.assertEqual(plan["cat2"], "トップス")
        self.assertEqual(plan["cat3"], "ブラウス・シャツ")
        self.assertTrue(plan["category_path_valid"])

    def test_buyma_category_plan_keeps_sweatshirt_out_of_blouse(self):
        row = {
            "product_name_kr": "소프트 헤비 워싱 오버 핏 스웻 셔츠",
            "product_name_en": "Soft Heavy Washed Oversized Sweatshirt",
            "brand": "ETRE AU SOMMET",
            "musinsa_category_large": "여성",
            "musinsa_category_middle": "상의",
            "musinsa_category_small": "맨투맨/스웨트",
        }

        plan = build_buyma_category_plan(row, category_corrector=_identity_corrector)

        self.assertEqual(plan["standard_category"], "TOP_SWEAT")
        self.assertEqual(plan["cat2"], "トップス")
        self.assertEqual(plan["cat3"], "スウェット・トレーナー")
        self.assertTrue(plan["category_path_valid"])

    def test_buyma_category_plan_ignores_mismatched_auto_seed_mapping(self):
        row = {
            "product_name_kr": "",
            "product_name_en": "Lettering Hooded Slim-Fit Long Sleeve Top",
            "brand": "ETRE AU SOMMET",
            "musinsa_category_large": "여성",
            "musinsa_category_middle": "상의",
            "musinsa_category_small": "긴소매 티셔츠",
        }

        with patch("marketplace.buyma.category.standard_category_map_mod.resolve_standard_category_buyma_target") as resolve_mock:
            with patch("marketplace.buyma.category.standard_category_map_mod.get_resolved_mapping_row_source", return_value="auto_seed"):
                with patch("marketplace.buyma.category.standard_category_map_mod.get_runtime_mapping_source", return_value="google_sheet_auto_seed+default"):
                    resolve_mock.return_value = (
                        "レディースファッション",
                        "トップス",
                        "パーカー・フーディ",
                    )
                    plan = build_buyma_category_plan(row, category_corrector=_identity_corrector)

        self.assertEqual(plan["standard_category"], "TOP_TSHIRT")
        self.assertEqual(plan["cat2"], "トップス")
        self.assertEqual(plan["cat3"], "Tシャツ・カットソー")
        self.assertTrue(plan["category_path_valid"])

    def test_legacy_infer_buyma_category_keeps_blouse_out_of_tshirt(self):
        self.assertEqual(
            infer_buyma_category("여성 반팔 블라우스", "SHORT SLEEVE BLOUSE", "GLOWNY"),
            ("レディースファッション", "トップス", "ブラウス・シャツ"),
        )
        self.assertEqual(
            infer_buyma_category("여성 반팔 티셔츠", "LOGO T-SHIRT", "GLOWNY"),
            ("レディースファッション", "トップス", "Tシャツ・カットソー"),
        )
        self.assertEqual(
            infer_buyma_category("여성 상의 맨투맨/스웨트", "Soft Heavy Washed Oversized Sweatshirt", "ETRE AU SOMMET"),
            ("レディースファッション", "トップス", "スウェット・トレーナー"),
        )

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
