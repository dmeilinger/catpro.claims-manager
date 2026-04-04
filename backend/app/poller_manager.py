"""Manages the catpro poller as a subprocess spawned by the FastAPI process."""

import logging
import logging.handlers
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent.parent
LOGS_DIR = REPO_ROOT / "logs"
LOG_PATH = LOGS_DIR / "poller.log"

_venv_python = REPO_ROOT / ".venv" / "bin" / "python3.13"
PYTHON = str(_venv_python) if _venv_python.exists() else "python3.13"

_proc: subprocess.Popen | None = None


def _open_log_file():
    """Return a rotating file handle for the poller log (10 MB × 5 backups)."""
    LOGS_DIR.mkdir(exist_ok=True)
    handler = logging.handlers.RotatingFileHandler(
        LOG_PATH, maxBytes=10 * 1024 * 1024, backupCount=5
    )
    return open(handler.baseFilename, "a")


def is_running() -> bool:
    return _proc is not None and _proc.poll() is None


def get_pid() -> int | None:
    return _proc.pid if is_running() else None


def start() -> dict:
    global _proc
    if is_running():
        return {"started": False, "reason": "already_running", "pid": _proc.pid}
    log_file = _open_log_file()
    _proc = subprocess.Popen(
        [PYTHON, "-m", "catpro.poller"],
        cwd=str(REPO_ROOT),
        stdout=log_file,
        stderr=subprocess.STDOUT,
    )
    log_file.close()
    return {"started": True, "pid": _proc.pid}


def stop() -> dict:
    global _proc
    if not is_running():
        return {"stopped": False, "reason": "not_running"}
    _proc.terminate()
    try:
        _proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        _proc.kill()
    pid = _proc.pid
    _proc = None
    return {"stopped": True, "pid": pid}


def read_logs(lines: int = 200) -> list[str]:
    """Return the last N lines from the poller log file."""
    if not LOG_PATH.exists():
        return []
    with open(LOG_PATH) as f:
        all_lines = f.readlines()
    return [line.rstrip() for line in all_lines[-lines:]]
