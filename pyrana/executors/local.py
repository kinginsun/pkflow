from __future__ import annotations
from pathlib import Path
import subprocess


class LocalExecutor:
    """Runs commands as local subprocesses. Synchronous wait."""

    def __init__(self, config: dict | None = None):
        self.config = config or {}

    def submit(self, cmd: list[str], cwd: Path) -> subprocess.Popen:
        log = open(cwd / "stdout.log", "w")
        err = open(cwd / "stderr.log", "w")
        return subprocess.Popen(cmd, cwd=cwd, stdout=log, stderr=err)

    def wait(self, proc: subprocess.Popen) -> int:
        return proc.wait()
