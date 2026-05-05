import unittest
from unittest.mock import Mock, patch

from services import image_service


class ImageServiceThumbnailBlurTests(unittest.TestCase):
    def test_thumbnail_command_omits_blur_flag_when_disabled(self):
        with patch.object(image_service.os.path, "isdir", return_value=True), \
            patch.object(image_service.os.path, "exists", return_value=True), \
            patch.object(image_service, "compose_thumbnail_footer", return_value="BRAND / footer"), \
            patch.object(image_service, "get_thumbnail_blur_faces_enabled", return_value=False), \
            patch("builtins.print"), \
            patch.object(image_service.subprocess, "run") as run_mock:
            run_mock.return_value = Mock(returncode=0, stdout="Created 1 split thumbnail\n", stderr="")

            self.assertTrue(image_service.create_thumbnail_for_folder("/tmp/images", "BRAND"))

        command = run_mock.call_args.args[0]
        self.assertNotIn("--blur-face", command)

    def test_thumbnail_command_adds_blur_flag_when_enabled(self):
        with patch.object(image_service.os.path, "isdir", return_value=True), \
            patch.object(image_service.os.path, "exists", return_value=True), \
            patch.object(image_service, "compose_thumbnail_footer", return_value="BRAND / footer"), \
            patch.object(image_service, "get_thumbnail_blur_faces_enabled", return_value=True), \
            patch("builtins.print"), \
            patch.object(image_service.subprocess, "run") as run_mock:
            run_mock.return_value = Mock(returncode=0, stdout="Created 1 split thumbnail\n", stderr="")

            self.assertTrue(image_service.create_thumbnail_for_folder("/tmp/images", "BRAND"))

        command = run_mock.call_args.args[0]
        self.assertIn("--blur-face", command)


if __name__ == "__main__":
    unittest.main()
