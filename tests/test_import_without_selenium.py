import subprocess
import sys
import textwrap
import unittest


class ImportWithoutSeleniumTests(unittest.TestCase):
    def test_core_modules_import_without_selenium(self):
        code = textwrap.dedent(
            """
            import builtins
            real_import = builtins.__import__
            def blocked(name, *args, **kwargs):
                if name == "selenium" or name.startswith("selenium."):
                    raise ModuleNotFoundError("No module named 'selenium'")
                return real_import(name, *args, **kwargs)
            builtins.__import__ = blocked

            import services.browser_service
            import services.buyma_service
            import services.crawler_service
            import marketplace.buyma.options
            import marketplace.buyma.uploader
            print("ok")
            """
        )
        proc = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, msg=proc.stderr)
        self.assertIn("ok", proc.stdout)


if __name__ == "__main__":
    unittest.main()

