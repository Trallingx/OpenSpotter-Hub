"""Crash-safe filesystem persistence used by configuration and artifacts.

All replacements are written beside the destination so ``os.replace`` remains
atomic on the target filesystem.  Callers own schema validation; this module
only guarantees consistent encoding, cleanup, and replacement behavior.
"""

from __future__ import annotations

import json
import os
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Callable, Iterator, Mapping, Optional, Union


PathLike = Union[str, os.PathLike]


@contextmanager
def atomic_text_writer(
    destination: PathLike,
    *,
    encoding: str = "utf-8",
    replace: Optional[Callable[[str, str], Any]] = None,
) -> Iterator[Any]:
    """Yield a temporary text stream and atomically replace ``destination``."""

    target = Path(destination).expanduser().resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=".{}.".format(target.name),
        suffix=".tmp",
        dir=str(target.parent),
        text=True,
    )
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(
            descriptor,
            "w",
            encoding=encoding,
            newline="\n",
        ) as handle:
            yield handle
            handle.flush()
            os.fsync(handle.fileno())
        replace_file = os.replace if replace is None else replace
        replace_file(str(temporary_path), str(target))
    except Exception:
        try:
            temporary_path.unlink()
        except OSError:
            pass
        raise


def write_text_atomic(
    destination: PathLike,
    text: str,
    *,
    replace: Optional[Callable[[str, str], Any]] = None,
) -> Path:
    """Write text with normalized newlines and return the resolved path."""

    target = Path(destination).expanduser().resolve()
    with atomic_text_writer(target, replace=replace) as handle:
        handle.write(str(text))
    return target


def write_json_atomic(
    destination: PathLike,
    payload: Mapping[str, Any],
    *,
    indent: int = 2,
    replace: Optional[Callable[[str, str], Any]] = None,
) -> Path:
    """Serialize one JSON object with stable formatting and atomic replacement."""

    if not isinstance(payload, Mapping):
        raise TypeError("JSON configuration payload must be a mapping")
    target = Path(destination).expanduser().resolve()
    with atomic_text_writer(target, replace=replace) as handle:
        json.dump(dict(payload), handle, indent=indent, ensure_ascii=False)
        handle.write("\n")
    return target


def read_json_object(source: PathLike) -> dict:
    """Load a JSON document and require an object at its root."""

    path = Path(source).expanduser().resolve()
    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        raise ValueError("JSON configuration must contain an object")
    return payload


__all__ = [
    "PathLike",
    "atomic_text_writer",
    "read_json_object",
    "write_json_atomic",
    "write_text_atomic",
]
