import os
import shutil
import unittest
import uuid
from contextlib import contextmanager

from ui.pages.image_thumbnail_page import get_latest_preview_images


class LatestPreviewImagesTests(unittest.TestCase):
    @contextmanager
    def _tmpdir(self):
        root = os.path.join(os.getcwd(), "tests", ".tmp_preview")
        case_dir = os.path.join(root, f"case_{uuid.uuid4().hex}")
        os.makedirs(case_dir, exist_ok=True)
        try:
            yield case_dir
        finally:
            shutil.rmtree(case_dir, ignore_errors=True)

    def _touch(self, path: str, mtime: float) -> None:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as f:
            f.write(b"x")
        os.utime(path, (mtime, mtime))

    def test_missing_images_dir_returns_empty(self):
        self.assertEqual(get_latest_preview_images("Z:/definitely-not-exists/auto-shop", limit=6), [])

    def test_no_images_returns_empty(self):
        with self._tmpdir() as root:
            os.makedirs(os.path.join(root, "2026-05-02"), exist_ok=True)
            with open(os.path.join(root, "2026-05-02", "readme.txt"), "w", encoding="utf-8") as f:
                f.write("not image")
            self.assertEqual(get_latest_preview_images(root, limit=6), [])

    def test_mtime_desc_sort_across_date_folders(self):
        with self._tmpdir() as root:
            self._touch(os.path.join(root, "2026-05-01", "old1.jpg"), 1000)
            self._touch(os.path.join(root, "2026-05-02", "new1.jpg"), 3000)
            self._touch(os.path.join(root, "2026-05-02", "new2.jpg"), 2500)
            self._touch(os.path.join(root, "2026-04-30", "old2.jpg"), 1500)

            items = get_latest_preview_images(root, limit=6)
            paths = [os.path.basename(str(it["path"])) for it in items]
            self.assertEqual(paths, ["new1.jpg", "new2.jpg", "old2.jpg", "old1.jpg"])

    def test_limit_applied(self):
        with self._tmpdir() as root:
            self._touch(os.path.join(root, "d1", "a.jpg"), 1000)
            self._touch(os.path.join(root, "d2", "b.jpg"), 2000)
            self._touch(os.path.join(root, "d3", "c.jpg"), 3000)
            items = get_latest_preview_images(root, limit=2)
            self.assertEqual(len(items), 2)
            self.assertEqual(os.path.basename(str(items[0]["path"])), "c.jpg")
            self.assertEqual(os.path.basename(str(items[1]["path"])), "b.jpg")

    def test_non_image_files_excluded(self):
        with self._tmpdir() as root:
            self._touch(os.path.join(root, "d", "a.jpg"), 1000)
            self._touch(os.path.join(root, "d", "b.png"), 900)
            with open(os.path.join(root, "d", "c.txt"), "w", encoding="utf-8") as f:
                f.write("x")
            items = get_latest_preview_images(root, limit=10)
            names = {os.path.basename(str(it["path"])) for it in items}
            self.assertEqual(names, {"a.jpg", "b.png"})


if __name__ == "__main__":
    unittest.main()
