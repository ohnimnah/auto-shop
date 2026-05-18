import unittest
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock, patch

from bs4 import BeautifulSoup
from PIL import Image

from config.app_config import BRAND_COLUMN, BRAND_EN_COLUMN
from services import image_service


class ImageServiceThumbnailBlurTests(unittest.TestCase):
    def _image_bytes(self, size):
        payload = BytesIO()
        Image.new("RGB", size, "white").save(payload, format="JPEG")
        return payload.getvalue()

    def _gradient_image_bytes(self, size):
        image = Image.new("RGB", size)
        width, height = size
        for y in range(height):
            for x in range(width):
                image.putpixel((x, y), ((x * 255) // max(width - 1, 1), (y * 255) // max(height - 1, 1), 120))
        payload = BytesIO()
        image.save(payload, format="JPEG")
        return payload.getvalue()

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

    def test_download_brand_logo_creates_text_png_when_logo_url_missing(self):
        with TemporaryDirectory() as tmp_dir:
            folder = Path(tmp_dir) / "product"
            folder.mkdir()
            image_path = folder / "01.jpg"
            Image.new("RGB", (20, 20), "white").save(image_path)

            saved = image_service.download_brand_logo(
                logo_url="",
                folder_name="product",
                images_root=tmp_dir,
                image_paths=str(image_path),
                brand_text="BAUF",
            )

            logo_path = folder / "__brand_logo.png"
            self.assertEqual(saved, str(logo_path).replace("\\", "/"))
            self.assertTrue(logo_path.exists())
            with Image.open(logo_path) as logo_image:
                self.assertEqual(logo_image.mode, "RGBA")

    def test_download_brand_logo_skips_korean_text_logo(self):
        with TemporaryDirectory() as tmp_dir:
            folder = Path(tmp_dir) / "product"
            folder.mkdir()
            image_path = folder / "01.jpg"
            Image.new("RGB", (20, 20), "white").save(image_path)

            saved = image_service.download_brand_logo(
                logo_url="",
                folder_name="product",
                images_root=tmp_dir,
                image_paths=str(image_path),
                brand_text="카인다미",
            )

            self.assertEqual(saved, "")
            self.assertFalse((folder / "__brand_logo.png").exists())

    def test_thumbnail_brand_uses_english_column_only(self):
        values = {
            BRAND_EN_COLUMN: "BAUF",
            BRAND_COLUMN: "바우프",
        }

        self.assertEqual(image_service.build_thumbnail_brand(values), "BAUF")
        self.assertEqual(image_service.build_thumbnail_brand({BRAND_COLUMN: "바우프"}), "BRAND")

    def test_brand_text_logo_strips_non_english_parts(self):
        with TemporaryDirectory() as tmp_dir:
            folder = Path(tmp_dir) / "product"
            folder.mkdir()
            image_path = folder / "01.jpg"
            Image.new("RGB", (20, 20), "white").save(image_path)

            saved = image_service.download_brand_logo(
                logo_url="",
                folder_name="product",
                images_root=tmp_dir,
                image_paths=str(image_path),
                brand_text="BAUF 바우프",
            )

            self.assertTrue(saved.endswith("__brand_logo.png"))
            self.assertTrue((folder / "__brand_logo.png").exists())

    def test_extract_brand_logo_url_uses_musinsa_brand_info_state(self):
        soup = BeautifulSoup("<html><body></body></html>", "html.parser")
        payload = {
            "mss_state": {
                "brandInfo": {
                    "brandEnglishName": "BAUF",
                    "brandLogoImageUrl": "//image.msscdn.net/brand/bauf/logo.png?width=120",
                }
            }
        }

        self.assertEqual(
            image_service.extract_brand_logo_url(soup, payload),
            "https://image.msscdn.net/brand/bauf/logo.png",
        )

    def test_extract_brand_logo_url_uses_brand_img_srcset(self):
        soup = BeautifulSoup(
            '<a href="/brand/bauf"><img srcset="//image.msscdn.net/brand/bauf/small.png 1x, //image.msscdn.net/brand/bauf/big.png 2x"></a>',
            "html.parser",
        )

        self.assertEqual(
            image_service.extract_brand_logo_url(soup, {}),
            "https://image.msscdn.net/brand/bauf/small.png",
        )

    def test_product_image_filter_keeps_product_and_model_photos(self):
        self.assertTrue(image_service.is_likely_product_or_model_image(self._image_bytes((960, 1440))))
        self.assertTrue(image_service.is_likely_product_or_model_image(self._image_bytes((500, 600))))

    def test_product_image_filter_skips_banners_and_extreme_detail_images(self):
        self.assertFalse(image_service.is_likely_product_or_model_image(self._image_bytes((1400, 180))))
        self.assertFalse(image_service.is_likely_product_or_model_image(self._image_bytes((800, 3600))))
        self.assertFalse(
            image_service.is_likely_product_or_model_image(
                self._image_bytes((960, 1440)),
                "https://image.msscdn.net/images/goodsdetail/banner/event.jpg",
            )
        )
        self.assertFalse(
            image_service.is_likely_product_or_model_image(
                self._image_bytes((960, 1440)),
                "https://image.msscdn.net/images/prd_img/model_info.jpg",
            )
        )

    def test_visual_fingerprint_detects_resized_duplicate_images(self):
        large = self._gradient_image_bytes((960, 1440))
        small = self._gradient_image_bytes((480, 720))
        large_fingerprint = image_service.build_visual_fingerprint(large)
        small_fingerprint = image_service.build_visual_fingerprint(small)

        self.assertTrue(image_service.is_duplicate_visual_fingerprint(small_fingerprint, [large_fingerprint]))


if __name__ == "__main__":
    unittest.main()
