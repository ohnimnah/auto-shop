"""Build command lines for launcher actions."""

from __future__ import annotations

import os
from typing import Callable


class CommandBuilder:
    def __init__(
        self,
        *,
        script_dir: str,
        resolve_python_executable: Callable[[], str],
        load_sheet_config: Callable[[], dict],
    ) -> None:
        self.script_dir = script_dir
        self.resolve_python_executable = resolve_python_executable
        self.load_sheet_config = load_sheet_config

    def build_unbuffered_python_command(self, script_name: str, *args: str) -> list[str]:
        return [self.resolve_python_executable(), "-u", os.path.join(self.script_dir, script_name), *args]

    def build(self, action: str) -> list[str]:
        if action == "install":
            if os.name == "nt":
                return [
                    "powershell",
                    "-NoProfile",
                    "-ExecutionPolicy",
                    "Bypass",
                    "-File",
                    os.path.join(self.script_dir, "bootstrap_windows.ps1"),
                ]
            return ["bash", os.path.join(self.script_dir, "bootstrap_mac.sh")]

        if action == "run":
            return self.build_unbuffered_python_command("main.py")
        if action == "collect-listings":
            config = self.load_sheet_config()
            queue_sheet_url = (config.get("queue_sheet_url") or "").strip()
            command = self.build_unbuffered_python_command("main.py", "--collect-listings")
            if queue_sheet_url:
                command.extend(["--queue-sheet-url", queue_sheet_url])
            return command
        if action == "watch":
            return self.build_unbuffered_python_command("main.py", "--watch")
        if action == "watch-images":
            return self.build_unbuffered_python_command("main.py", "--watch", "--download-images")
        if action == "watch-thumbnails":
            return self.build_unbuffered_python_command("main.py", "--watch", "--make-thumbnails")
        if action == "watch-upload":
            return self.build_unbuffered_python_command("buyma_upload.py", "--watch", "--mode", "auto")
        if action == "save-images":
            return self.build_unbuffered_python_command("main.py", "--download-images")
        if action == "upload-review":
            return self.build_unbuffered_python_command("buyma_upload.py", "--mode", "review")
        if action == "upload-auto":
            return self.build_unbuffered_python_command("buyma_upload.py", "--mode", "auto")

        raise ValueError(f"Unknown action: {action}")

