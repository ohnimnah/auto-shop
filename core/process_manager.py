"""Subprocess lifecycle management decoupled from Tk widgets."""

from __future__ import annotations

import os
import subprocess
import threading
from typing import Callable, Dict, Optional

from core.errors import ProcessStartError, ProcessStopError


LineCallback = Callable[[str], None]
DoneCallback = Callable[[int], None]


class ProcessManager:
    def __init__(self, cwd: str, env_factory: Callable[[], dict[str, str]]) -> None:
        self.cwd = cwd
        self.env_factory = env_factory
        self.process: Optional[subprocess.Popen] = None
        self.team_processes: Dict[str, subprocess.Popen] = {}
        self.thread: Optional[threading.Thread] = None
        self.team_threads: Dict[str, threading.Thread] = {}
        self._lock = threading.RLock()

    def is_running(self) -> bool:
        with self._lock:
            return bool(self.process and self.process.poll() is None)

    def is_team_running(self, team_key: str) -> bool:
        with self._lock:
            proc = self.team_processes.get(team_key)
            return bool(proc and proc.poll() is None)

    def start(self, command: list[str], on_line: LineCallback, on_done: DoneCallback) -> bool:
        with self._lock:
            if self.process and self.process.poll() is None:
                return False
            self.process = self._popen(command)
            self.thread = threading.Thread(
                target=self._read_process,
                args=(self.process, on_line, on_done, None),
                daemon=False,
            )
            self.thread.start()
        return True

    def start_team(self, team_key: str, command: list[str], on_line: LineCallback, on_done: DoneCallback) -> bool:
        with self._lock:
            proc = self.team_processes.get(team_key)
            if proc and proc.poll() is None:
                return False
            proc = self._popen(command)
            thread = threading.Thread(
                target=self._read_process,
                args=(proc, on_line, on_done, team_key),
                daemon=False,
            )
            self.team_processes[team_key] = proc
            self.team_threads[team_key] = thread
            thread.start()
        return True

    def stop(self) -> None:
        with self._lock:
            proc = self.process
            thread = self.thread
        self._stop_process(proc)
        self._join_thread(thread)
        with self._lock:
            if self.process is proc:
                self.process = None
            if self.thread is thread:
                self.thread = None

    def stop_team(self, team_key: str) -> None:
        with self._lock:
            proc = self.team_processes.get(team_key)
            thread = self.team_threads.get(team_key)
        self._stop_process(proc)
        self._join_thread(thread)
        with self._lock:
            if self.team_processes.get(team_key) is proc:
                self.team_processes.pop(team_key, None)
            if self.team_threads.get(team_key) is thread:
                self.team_threads.pop(team_key, None)

    def stop_all_teams(self) -> None:
        with self._lock:
            team_keys = list(self.team_processes.keys())
        for team_key in team_keys:
            self.stop_team(team_key)

    def _popen(self, command: list[str]) -> subprocess.Popen:
        env = self.env_factory()
        try:
            return subprocess.Popen(
                command,
                cwd=self.cwd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                env=env,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
            )
        except OSError as exc:
            raise ProcessStartError(str(exc)) from exc

    def _read_process(
        self,
        proc: subprocess.Popen,
        on_line: LineCallback,
        on_done: DoneCallback,
        team_key: Optional[str],
    ) -> None:
        return_code = 1
        try:
            if proc.stdout:
                while True:
                    line = proc.stdout.readline()
                    if line:
                        on_line(line)
                        continue
                    if proc.poll() is not None:
                        break
        except Exception as exc:
            on_line(f"[process-manager] stdout read error: {exc}\n")
        finally:
            try:
                return_code = proc.wait(timeout=1)
            except subprocess.TimeoutExpired:
                try:
                    self._stop_process(proc)
                except ProcessStopError as exc:
                    on_line(f"[process-manager] stop error: {exc}\n")
                return_code = proc.poll()
                if return_code is None:
                    return_code = 1
            try:
                if proc.stdout:
                    proc.stdout.close()
            except Exception:
                pass
            with self._lock:
                if team_key is None:
                    if self.process is proc:
                        self.process = None
                    if self.thread is threading.current_thread():
                        self.thread = None
                else:
                    if self.team_processes.get(team_key) is proc:
                        self.team_processes.pop(team_key, None)
                    if self.team_threads.get(team_key) is threading.current_thread():
                        self.team_threads.pop(team_key, None)
            on_done(return_code)

    def _stop_process(self, proc: Optional[subprocess.Popen]) -> None:
        if not proc or proc.poll() is not None:
            return
        try:
            proc.terminate()
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            try:
                proc.kill()
                proc.wait(timeout=5)
            except Exception:
                raise ProcessStopError("프로세스를 강제 종료하지 못했습니다.")
        except Exception:
            try:
                proc.kill()
            except Exception:
                raise ProcessStopError("프로세스를 종료하지 못했습니다.")

    def _join_thread(self, thread: Optional[threading.Thread]) -> None:
        if not thread or thread is threading.current_thread():
            return
        if thread.is_alive():
            thread.join(timeout=5)


def build_default_env(data_dir: str, images_dir: str) -> dict[str, str]:
    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"
    env["AUTO_SHOP_IMAGES_DIR"] = images_dir
    env["AUTO_SHOP_DATA_DIR"] = data_dir
    for proxy_key in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy"):
        env[proxy_key] = ""
    env["NO_PROXY"] = "*"
    env["no_proxy"] = "*"
    return env
