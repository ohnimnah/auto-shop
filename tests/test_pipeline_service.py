import unittest

from services.pipeline_service import (
    LauncherPipelineService,
    WatchPolicy,
    _sheet_product_column_map,
    row_crawl_outputs_complete,
)


class PipelineServiceTests(unittest.TestCase):
    def test_stage_mapping(self):
        service = LauncherPipelineService()

        self.assertEqual(service.stage_for_action("watch"), "scout")
        self.assertEqual(service.stage_for_action("save-images"), "assets")
        self.assertEqual(service.stage_for_action("thumbnail-create"), "design")
        self.assertEqual(service.stage_for_action("upload-auto"), "sales")

    def test_stage_from_log(self):
        service = LauncherPipelineService()

        self.assertEqual(service.stage_from_log("python main.py --download-images"), "assets")
        self.assertEqual(service.stage_from_log("python main.py --make-thumbnails"), "design")
        self.assertEqual(service.stage_from_log("python buyma_upload.py --mode auto"), "sales")

    def test_watch_policy_failure_threshold(self):
        policy = WatchPolicy(max_failures_before_pause=3)

        self.assertTrue(policy.should_count_failure(1, enabled=True))
        self.assertFalse(policy.should_count_failure(1, enabled=False))
        self.assertFalse(policy.should_pause_after_failure(2))
        self.assertTrue(policy.should_pause_after_failure(3))

    def test_sheet_product_column_map_includes_english_name(self):
        mapping = _sheet_product_column_map(
            {
                "BRAND_COLUMN": "C",
                "BRAND_EN_COLUMN": "D",
                "PRODUCT_NAME_KR_COLUMN": "E",
                "PRODUCT_NAME_JP_COLUMN": "F",
                "PRODUCT_NAME_EN_COLUMN": "G",
                "MUSINSA_SKU_COLUMN": "H",
            }
        )

        self.assertEqual(mapping["product_name_jp"], "F")
        self.assertEqual(mapping["product_name_en"], "G")

    def test_crawl_outputs_complete_accepts_buyma_meta_without_price(self):
        row = {
            "C": "카인다미",
            "D": "KINDAME",
            "E": "데님 버튼 튜브탑",
            "H": "TS25S3105",
            "I": "흰, 검정",
            "K": "S, M",
            "L": "S: 총장 35.8",
            "M": "59,000",
            "N": "",
            "O": '{"selected_reason":"no_reliable_candidate"}',
            "Q": "₩11,350",
        }

        self.assertTrue(
            row_crawl_outputs_complete(
                row,
                "C",
                "D",
                "E",
                "H",
                "I",
                "K",
                "L",
                "M",
                "N",
                "O",
                "Q",
            )
        )


if __name__ == "__main__":
    unittest.main()
