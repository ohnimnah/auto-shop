import unittest

from services.pipeline_service import LauncherPipelineService, WatchPolicy


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


if __name__ == "__main__":
    unittest.main()
