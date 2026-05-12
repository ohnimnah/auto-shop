import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch

from PIL import Image, ImageDraw

import make_thumbnails


class MakeThumbnailsFaceBlurTests(unittest.TestCase):
    def setUp(self):
        make_thumbnails._HAAR_FACE_CASCADE_FAILED = False

    def tearDown(self):
        make_thumbnails._HAAR_FACE_CASCADE_FAILED = False

    def test_missing_haar_cascade_skips_face_detection(self):
        fake_cv2 = SimpleNamespace(data=SimpleNamespace(haarcascades="/missing/cv2/data/"))
        image = Image.new("RGB", (120, 120), "white")

        with patch.object(make_thumbnails, "cv2", fake_cv2):
            self.assertEqual(make_thumbnails._detect_faces_haar(image), [])
            self.assertTrue(make_thumbnails._HAAR_FACE_CASCADE_FAILED)

    def test_corner_overlay_is_pasted_on_top_right(self):
        canvas = Image.new("RGB", (100, 100), "white")
        with TemporaryDirectory() as tmp_dir:
            overlay_path = Path(tmp_dir) / "overlay.png"
            overlay = Image.new("RGBA", (100, 100), (255, 255, 255, 0))
            draw = ImageDraw.Draw(overlay)
            draw.polygon([(70, 0), (100, 0), (100, 30)], fill=(50, 120, 250, 255))
            overlay.save(overlay_path)

            self.assertTrue(make_thumbnails._paste_corner_overlay(canvas, overlay_path, 100))

        self.assertEqual(canvas.getpixel((95, 5)), (50, 120, 250))
        self.assertEqual(canvas.getpixel((5, 95)), (255, 255, 255))

    def test_simple_style_keeps_brand_logo_and_corner_overlay(self):
        with TemporaryDirectory() as tmp_dir:
            base = Path(tmp_dir)
            src = base / "01.jpg"
            logo = base / "__brand_logo.png"
            overlay = base / "overlay.png"
            output = base / "out.png"

            Image.new("RGB", (120, 120), "white").save(src)
            Image.new("RGBA", (40, 20), (255, 0, 0, 255)).save(logo)
            overlay_image = Image.new("RGBA", (100, 100), (255, 255, 255, 0))
            ImageDraw.Draw(overlay_image).polygon([(70, 0), (100, 0), (100, 30)], fill=(50, 120, 250, 255))
            overlay_image.save(overlay)

            make_thumbnails.compose_simple_logo_style(
                [src],
                output,
                100,
                brand_logo=logo,
                corner_overlay=overlay,
            )

            result = Image.open(output).convert("RGB")

        self.assertEqual(result.getpixel((50, 20)), (255, 0, 0))
        self.assertEqual(result.getpixel((95, 5)), (50, 120, 250))


if __name__ == "__main__":
    unittest.main()
