import os
import tempfile
import unittest
from unittest.mock import patch

import main


class RuntimePathTests(unittest.TestCase):
    def test_images_env_overrides_data_dir_env(self):
        original_data_dir = main.DATA_DIR
        original_images_root = main.IMAGES_ROOT
        original_credentials_path = main.CREDENTIALS_PATH
        with tempfile.TemporaryDirectory() as data_dir, tempfile.TemporaryDirectory() as images_dir:
            try:
                with patch.dict(
                    os.environ,
                    {
                        "AUTO_SHOP_DATA_DIR": data_dir,
                        "AUTO_SHOP_IMAGES_DIR": images_dir,
                    },
                    clear=False,
                ):
                    main.initialize_runtime_paths()
                    self.assertEqual(main.IMAGES_ROOT, os.path.abspath(images_dir))
            finally:
                main.DATA_DIR = original_data_dir
                main.IMAGES_ROOT = original_images_root
                main.CREDENTIALS_PATH = original_credentials_path


if __name__ == "__main__":
    unittest.main()
