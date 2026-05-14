import unittest

from ui.dashboard import DEFAULT_1080P_WINDOWS_SCALING, _recommended_ui_scaling


class LauncherUiScalingTest(unittest.TestCase):
    def test_windows_1080p_uses_larger_minimum_scale(self) -> None:
        scale = _recommended_ui_scaling(
            1.333,
            1920,
            1080,
            platform_name="win32",
        )
        self.assertEqual(scale, DEFAULT_1080P_WINDOWS_SCALING)

    def test_windows_high_dpi_scale_is_preserved(self) -> None:
        scale = _recommended_ui_scaling(
            1.8,
            1920,
            1080,
            platform_name="win32",
        )
        self.assertEqual(scale, 1.8)

    def test_non_windows_scale_is_unchanged(self) -> None:
        scale = _recommended_ui_scaling(
            1.333,
            1920,
            1080,
            platform_name="darwin",
        )
        self.assertEqual(scale, 1.333)

    def test_environment_override_wins(self) -> None:
        scale = _recommended_ui_scaling(
            1.333,
            1920,
            1080,
            platform_name="win32",
            override="1.7",
        )
        self.assertEqual(scale, 1.7)


if __name__ == "__main__":
    unittest.main()
