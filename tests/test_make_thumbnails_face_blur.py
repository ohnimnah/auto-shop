import unittest
from types import SimpleNamespace
from unittest.mock import patch

from PIL import Image

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


if __name__ == "__main__":
    unittest.main()
