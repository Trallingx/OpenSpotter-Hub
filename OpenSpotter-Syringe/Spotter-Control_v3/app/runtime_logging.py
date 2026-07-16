"""Central runtime logging for OpenSpotter Control."""

from __future__ import annotations

import json
import logging
import math
import os
import platform
import re
import sys
from dataclasses import asdict, is_dataclass
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any, Mapping

from .paths import LOG_DIR


LOGGER_NAME = "openspotter"
LOG_FILENAME = "openspotter-control.log"
DEFAULT_LOG_LEVEL = logging.INFO
MAX_LOG_BYTES = 5 * 1024 * 1024
BACKUP_COUNT = 5
_SENSITIVE_KEY = re.compile(
    r"(?:password|passwd|secret|token|api[_-]?key|credential|authorization)",
    re.IGNORECASE,
)


_root_logger = logging.getLogger(LOGGER_NAME)
_root_logger.addHandler(logging.NullHandler())
_root_logger.propagate = False


def get_logger(component: str | None = None) -> logging.Logger:
    """Return an application logger without configuring global Python logging."""
    if not component:
        return _root_logger
    cleaned = str(component).strip().strip(".")
    return logging.getLogger(f"{LOGGER_NAME}.{cleaned}")


def _resolve_level(level: int | str | None) -> int:
    requested = level if level is not None else os.getenv("OPENSPOTTER_LOG_LEVEL", "INFO")
    if isinstance(requested, int):
        return requested
    numeric_level = logging.getLevelName(str(requested).strip().upper())
    return numeric_level if isinstance(numeric_level, int) else DEFAULT_LOG_LEVEL


def configure_logging(
    log_dir: str | os.PathLike[str] = LOG_DIR,
    *,
    level: int | str | None = None,
) -> Path:
    """Configure rotating file and console logging, returning the active log path."""
    destination_dir = Path(log_dir)
    destination_dir.mkdir(parents=True, exist_ok=True)
    log_path = destination_dir / LOG_FILENAME

    for handler in list(_root_logger.handlers):
        _root_logger.removeHandler(handler)
        try:
            handler.close()
        except Exception:
            pass

    resolved_level = _resolve_level(level)
    formatter = logging.Formatter(
        "%(asctime)s.%(msecs)03d | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    file_handler = RotatingFileHandler(
        log_path,
        maxBytes=MAX_LOG_BYTES,
        backupCount=BACKUP_COUNT,
        encoding="utf-8",
    )
    file_handler.setLevel(resolved_level)
    file_handler.setFormatter(formatter)

    console_handler = logging.StreamHandler()
    console_handler.setLevel(max(resolved_level, logging.INFO))
    console_handler.setFormatter(formatter)

    _root_logger.setLevel(resolved_level)
    _root_logger.addHandler(file_handler)
    _root_logger.addHandler(console_handler)
    _root_logger.propagate = False

    sys.excepthook = _log_uncaught_exception
    log_options(
        _root_logger,
        "logging.configured",
        log_path=log_path,
        level=logging.getLevelName(resolved_level),
        max_log_bytes=MAX_LOG_BYTES,
        backup_count=BACKUP_COUNT,
        python=sys.version.split()[0],
        platform=platform.platform(),
    )
    return log_path


def shutdown_logging() -> None:
    """Flush and close application-owned handlers."""
    for handler in list(_root_logger.handlers):
        _root_logger.removeHandler(handler)
        try:
            handler.flush()
            handler.close()
        except Exception:
            pass
    _root_logger.setLevel(logging.WARNING)
    _root_logger.addHandler(logging.NullHandler())
    sys.excepthook = sys.__excepthook__


def log_options(logger: logging.Logger, event: str, **options: Any) -> None:
    """Write a stable, redacted JSON option snapshot at INFO level."""
    if not logger.isEnabledFor(logging.INFO):
        return
    logger.info("%s | options=%s", event, serialize_options(options))


def serialize_options(options: Mapping[str, Any]) -> str:
    """Serialize runtime options for logs while redacting credential-like keys."""
    safe = _json_safe(options)
    return json.dumps(
        safe,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def _json_safe(value: Any, key: str | None = None) -> Any:
    if key is not None and _SENSITIVE_KEY.search(key):
        return "<redacted>"
    if is_dataclass(value):
        value = asdict(value)
    if isinstance(value, Mapping):
        return {
            str(item_key): _json_safe(item_value, str(item_key))
            for item_key, item_value in value.items()
        }
    if isinstance(value, (list, tuple, set, frozenset)):
        return [_json_safe(item) for item in value]
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, float) and not math.isfinite(value):
        return str(value)
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return repr(value)


def _log_uncaught_exception(exc_type, exc_value, exc_traceback) -> None:
    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc_value, exc_traceback)
        return
    _root_logger.critical(
        "runtime.uncaught_exception",
        exc_info=(exc_type, exc_value, exc_traceback),
    )
