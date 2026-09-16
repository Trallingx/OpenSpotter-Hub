"""Typed, atomic persistence for editable application configuration."""

from __future__ import annotations

import os
from typing import Any, Dict, Optional, Sequence

from .schema import Field, parse_widget_entries
from .storage import read_json_object, write_json_atomic
from ..runtime_logging import get_logger, log_options


logger = get_logger("configuration")


def read_defaults(path: os.PathLike) -> Dict[str, Any]:
    """Load one JSON configuration object."""

    data = read_json_object(path)
    log_options(logger, "configuration.loaded", path=path, options=data)
    return data


def save_defaults(path: os.PathLike, *sections: Dict[str, Any]) -> None:
    """Merge configuration sections and replace the destination atomically."""

    data = {}
    for section in sections:
        if not isinstance(section, dict):
            raise TypeError(
                "save_defaults expected dicts, got {}: {}".format(
                    type(section).__name__,
                    section,
                )
            )
        data.update(section)
    write_json_atomic(path, data, replace=os.replace)
    log_options(logger, "configuration.saved", path=path, options=data)


def write_state(
    state: Any,
    config_dir: Optional[os.PathLike] = None,
) -> None:
    """Persist active pattern counts without risking a partial JSON file."""

    filepath = (
        "config_states.json"
        if config_dir is None
        else os.path.join(str(config_dir), "config_states.json")
    )
    payload = state if isinstance(state, dict) else {"grid_count": state}
    write_json_atomic(filepath, payload, replace=os.replace)
    log_options(logger, "pattern_state.saved", path=filepath, options=payload)


def entries_to_dict(
    entries: Sequence[Any],
    fields: Sequence[Field],
) -> Dict[str, Any]:
    """Read GUI value sources with the historical permissive fallback rules."""

    def log_default(field, raw_value, default, error):
        log_options(
            logger,
            "configuration.invalid_value_defaulted",
            field=field.key,
            raw_value=raw_value,
            default=default,
            error=str(error),
        )

    return parse_widget_entries(
        entries,
        fields,
        strict=False,
        on_error=log_default,
    )


__all__ = [
    "entries_to_dict",
    "read_defaults",
    "save_defaults",
    "write_state",
]
