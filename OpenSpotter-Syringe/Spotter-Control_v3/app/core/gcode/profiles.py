"""Generation-profile sidecars shared by all pattern plugins."""

from __future__ import annotations

import os
from datetime import datetime
from typing import Any, Mapping

from ..storage import write_json_atomic
from ...runtime_logging import get_logger, log_options


logger = get_logger("generation.profile")


def write_generation_settings_file(
    gcode_path: str,
    settings_snapshot: Mapping[str, Any],
) -> str:
    """Write a versioned, reproducible profile beside generated G-code."""

    base, _extension = os.path.splitext(gcode_path)
    settings_path = "{}_settings.json".format(base)
    payload = dict(settings_snapshot)
    payload.setdefault("schema_version", 3)
    payload["generated_at"] = datetime.now().astimezone().isoformat(
        timespec="seconds"
    )
    # Retain the schema-v2 path while adding a portable identifier for new
    # consumers that should not depend on the originating machine.
    payload["gcode_path"] = gcode_path
    payload["gcode_filename"] = os.path.basename(gcode_path)
    try:
        write_json_atomic(settings_path, payload, replace=os.replace)
    except Exception:
        logger.exception(
            "generation.settings_write_failed | gcode_path=%s | settings_path=%s",
            gcode_path,
            settings_path,
        )
        raise
    log_options(
        logger,
        "generation.settings_written",
        gcode_path=gcode_path,
        settings_path=settings_path,
        settings=payload,
    )
    return settings_path


__all__ = ["write_generation_settings_file"]
