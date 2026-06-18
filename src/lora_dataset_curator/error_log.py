from __future__ import annotations

import faulthandler
import sys
import traceback
from datetime import UTC, datetime
from pathlib import Path
from types import TracebackType

from .storage import ensure_app_data_dirs

ERROR_LOG_NAME = "error.log"
NATIVE_CRASH_LOG_NAME = "native-crash.log"
_CRASH_LOG_FILE = None


def error_log_path() -> Path:
    return ensure_app_data_dirs().logs_dir / ERROR_LOG_NAME


def native_crash_log_path() -> Path:
    return ensure_app_data_dirs().logs_dir / NATIVE_CRASH_LOG_NAME


def install_runtime_error_logging() -> None:
    global _CRASH_LOG_FILE

    path = native_crash_log_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    if _CRASH_LOG_FILE is None:
        _CRASH_LOG_FILE = path.open("a", encoding="utf-8")
    faulthandler.enable(file=_CRASH_LOG_FILE, all_threads=True)

    previous_excepthook = sys.excepthook

    def log_uncaught_exception(
        exc_type: type[BaseException],
        exc_value: BaseException,
        exc_traceback: TracebackType | None,
    ) -> None:
        append_exception_log(exc_type, exc_value, exc_traceback)
        previous_excepthook(exc_type, exc_value, exc_traceback)

    sys.excepthook = log_uncaught_exception


def append_error_log(message: str) -> Path:
    path = error_log_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(UTC).isoformat()
    with path.open("a", encoding="utf-8") as file:
        file.write(f"[{timestamp}] {message.rstrip()}\n\n")
    return path


def append_exception_log(
    exc_type: type[BaseException],
    exc_value: BaseException,
    exc_traceback: TracebackType | None,
) -> Path:
    return append_error_log(
        "".join(traceback.format_exception(exc_type, exc_value, exc_traceback))
    )


def read_error_log() -> str:
    path = error_log_path()
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return ""


def clear_error_log() -> None:
    try:
        error_log_path().unlink()
    except FileNotFoundError:
        pass
