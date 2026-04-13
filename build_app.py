"""Build standalone desktop app for auto_shop launcher."""

from __future__ import annotations

import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent
DIST_DIR = PROJECT_DIR / "dist"
BUILD_DIR = PROJECT_DIR / "build"
ENTRY = PROJECT_DIR / "launcher_gui.py"
APP_NAME = "AutoShopLauncher"


def resolve_python() -> str:
    windows_python = PROJECT_DIR / ".venv" / "Scripts" / "python.exe"
    mac_python = PROJECT_DIR / ".venv" / "bin" / "python"
    if windows_python.exists():
        return str(windows_python)
    if mac_python.exists():
        return str(mac_python)
    return sys.executable


def ensure_pyinstaller(python_cmd: str) -> None:
    subprocess.check_call([python_cmd, "-m", "pip", "install", "--upgrade", "pip"])
    subprocess.check_call([python_cmd, "-m", "pip", "install", "pyinstaller"])


def pick_icon() -> str | None:
    system_name = platform.system().lower()
    custom_ico = PROJECT_DIR / "images" / "app_icon.ico"
    custom_icns = PROJECT_DIR / "images" / "app_icon.icns"

    if system_name == "windows":
        if custom_ico.exists():
            return str(custom_ico)
        return None

    if system_name == "darwin":
        if custom_icns.exists():
            return str(custom_icns)
        fallback_icons = [
            "/System/Library/CoreServices/CoreTypes.bundle/Contents/Resources/SidebarApplicationsFolder.icns",
            "/System/Library/CoreServices/CoreTypes.bundle/Contents/Resources/ToolbarCustomizeIcon.icns",
        ]
        for icon_path in fallback_icons:
            if Path(icon_path).exists():
                return icon_path
        return None

    return None


def clean_old_artifacts() -> None:
    if BUILD_DIR.exists():
        shutil.rmtree(BUILD_DIR, ignore_errors=True)


def build() -> Path:
    python_cmd = resolve_python()
    ensure_pyinstaller(python_cmd)
    clean_old_artifacts()

    command = [
        python_cmd,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--windowed",
        "--name",
        APP_NAME,
        str(ENTRY),
    ]

    icon = pick_icon()
    if icon:
        command.extend(["--icon", icon])

    subprocess.check_call(command, cwd=str(PROJECT_DIR))

    if platform.system().lower() == "windows":
        return DIST_DIR / f"{APP_NAME}.exe"
    if platform.system().lower() == "darwin":
        return DIST_DIR / f"{APP_NAME}.app"
    return DIST_DIR / APP_NAME


def main() -> None:
    print("[build] Starting app packaging")
    output_path = build()
    print(f"[build] Done: {output_path}")
    print("[build] You can launch the packaged app by double-clicking it.")


if __name__ == "__main__":
    main()
