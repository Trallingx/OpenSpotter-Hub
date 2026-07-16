"""Validated persistence for canvas objects and optional program bindings.

Visual objects deliberately live outside generation settings. Unlinked geometry
only describes the layout shown behind the preview; linked properties resolve
from real program inputs without becoming planner geometry themselves.
"""

from __future__ import annotations

import json
import math
import os
import re
import tempfile
from copy import deepcopy
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping


VISUAL_OBJECT_CONFIG_VERSION = 2
VISUAL_OBJECT_TYPES = ("rectangle", "circle", "image")
VISUAL_BINDABLE_PROPERTIES = ("x", "y", "width", "height")
CAPTRON_VISUAL_OBJECT_ID = "captron-tcp"
_VARIABLE_PATH_RE = re.compile(
    r"^[A-Za-z_][A-Za-z0-9_]*(?:\.(?:[A-Za-z_][A-Za-z0-9_]*|[1-9][0-9]*))+$"
)
_LEGACY_CONTAINER_ID_RE = re.compile(r"^legacy-container-([1-6])$")

DEFAULT_VISUAL_OBJECT_DATA = (
    {
        "id": "legacy-build-plate",
        "type": "rectangle",
        "x": 22.0,
        "y": 19.0,
        "width": 176.0,
        "height": 176.0,
        "color": "#273036",
        "text": "Build plate",
        "text_size": 10,
    },
    {
        "id": "legacy-acceptance-limit",
        "type": "rectangle",
        "x": 27.5,
        "y": 24.5,
        "width": 165.0,
        "height": 165.0,
        "color": "#263c44",
        "text": "Acceptance limit",
        "text_size": 9,
    },
    *(
        {
            "id": f"legacy-container-{index}",
            "type": "circle",
            "x": x,
            "y": y,
            "width": 12.0,
            "height": 12.0,
            "color": "#1c252a",
            "text": str(index),
            "text_size": 9,
            "bindings": {
                "x": f"global.container{index}_x",
                "y": f"global.container{index}_y",
            },
        }
        for index, (x, y) in enumerate(
            (
                (16.0, 208.0),
                (66.0, 208.0),
                (116.0, 208.0),
                (218.0, 115.0),
                (218.0, 65.0),
                (218.0, 15.0),
            ),
            start=1,
        )
    ),
    {
        "id": CAPTRON_VISUAL_OBJECT_ID,
        "type": "image",
        "x": -30.0,
        "y": -30.0,
        "width": 60.0,
        "height": 60.0,
        "color": "#1c252a",
        "text": "CAPTRON TCP",
        "text_size": 8,
        "image_path": "assets/Captron-TCP.png",
    },
)

DEFAULT_VISUAL_OBJECT_IDS = tuple(
    item["id"] for item in DEFAULT_VISUAL_OBJECT_DATA
)


class VisualObjectValidationError(ValueError):
    """Raised when a display object cannot be drawn safely."""


def _finite_number(value: Any, field_name: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise VisualObjectValidationError(
            f"'{field_name}' must be a number"
        ) from exc
    if not math.isfinite(number):
        raise VisualObjectValidationError(
            f"'{field_name}' must be a finite number"
        )
    return number


def _normalize_visual_bindings(value: Any) -> Dict[str, str]:
    if value is None:
        raise VisualObjectValidationError("'bindings' must be a JSON object")
    if not isinstance(value, dict):
        raise VisualObjectValidationError("'bindings' must be a JSON object")

    normalized: Dict[str, str] = {}
    for raw_property, raw_path in value.items():
        property_name = str(raw_property).strip()
        if property_name not in VISUAL_BINDABLE_PROPERTIES:
            allowed = ", ".join(VISUAL_BINDABLE_PROPERTIES)
            raise VisualObjectValidationError(
                f"Unsupported binding property '{property_name}'; expected {allowed}"
            )
        if not isinstance(raw_path, str):
            raise VisualObjectValidationError(
                f"Binding path for '{property_name}' must be a string"
            )
        variable_path = raw_path.strip()
        if not _VARIABLE_PATH_RE.fullmatch(variable_path):
            raise VisualObjectValidationError(
                f"Binding path for '{property_name}' is invalid: '{variable_path}'"
            )
        normalized[property_name] = variable_path
    return normalized


def _migrate_v1_visual_object(value: Any) -> Any:
    """Add default container-coordinate links without restoring removed objects."""
    if not isinstance(value, dict) or "bindings" in value:
        return value

    match = _LEGACY_CONTAINER_ID_RE.fullmatch(str(value.get("id", "")).strip())
    if match is None:
        return value

    container_number = match.group(1)
    migrated = dict(value)
    migrated["bindings"] = {
        "x": f"global.container{container_number}_x",
        "y": f"global.container{container_number}_y",
    }
    return migrated


def normalize_visual_object(value: Any, *, fallback_id: str) -> Dict[str, Any]:
    """Return one object in the canonical, JSON-safe canvas schema."""
    if not isinstance(value, dict):
        raise VisualObjectValidationError("Each visual object must be a JSON object")

    object_id = str(value.get("id", fallback_id)).strip()
    if not object_id:
        raise VisualObjectValidationError("Visual object IDs cannot be empty")

    object_type = str(value.get("type", "rectangle")).strip().lower()
    if object_type not in VISUAL_OBJECT_TYPES:
        allowed = ", ".join(VISUAL_OBJECT_TYPES)
        raise VisualObjectValidationError(
            f"Unsupported visual object type '{object_type}'; expected {allowed}"
        )

    width = _finite_number(value.get("width", 0), "width")
    height = _finite_number(value.get("height", 0), "height")
    if width <= 0 or height <= 0:
        raise VisualObjectValidationError("'width' and 'height' must be greater than zero")

    color = str(value.get("color", "#9aa7b2")).strip()
    if not color:
        raise VisualObjectValidationError("'color' cannot be empty")

    raw_text_size = _finite_number(value.get("text_size", 10), "text_size")
    text_size = int(raw_text_size)
    if raw_text_size != text_size or not 1 <= text_size <= 200:
        raise VisualObjectValidationError(
            "'text_size' must be a whole number from 1 to 200"
        )

    normalized = {
        "id": object_id,
        "type": object_type,
        "x": _finite_number(value.get("x", 0), "x"),
        "y": _finite_number(value.get("y", 0), "y"),
        "width": width,
        "height": height,
        "color": color,
        "text": str(value.get("text", "")),
        "text_size": text_size,
        "bindings": _normalize_visual_bindings(value.get("bindings", {})),
    }
    if object_type == "image":
        image_path = str(value.get("image_path", "")).strip()
        if not image_path:
            raise VisualObjectValidationError(
                "'image_path' is required for image objects"
            )
        normalized["image_path"] = image_path
    return normalized


def normalize_visual_object_config(payload: Any) -> Dict[str, Any]:
    """Validate a complete visual-object document and preserve display order."""
    if isinstance(payload, list):
        payload = {"version": 1, "objects": payload}
    if not isinstance(payload, dict):
        raise VisualObjectValidationError(
            "Visual object configuration must be a JSON object"
        )

    version = payload.get("version", 1)
    if version not in (1, VISUAL_OBJECT_CONFIG_VERSION):
        raise VisualObjectValidationError(
            f"Unsupported visual object configuration version '{version}'"
        )

    objects = payload.get("objects", [])
    if not isinstance(objects, list):
        raise VisualObjectValidationError("'objects' must be a JSON array")

    normalized: List[Dict[str, Any]] = []
    object_ids = set()
    for index, item in enumerate(objects, start=1):
        if version == 1:
            item = _migrate_v1_visual_object(item)
        visual_object = normalize_visual_object(
            item,
            fallback_id=f"visual-object-{index}",
        )
        if visual_object["id"] in object_ids:
            raise VisualObjectValidationError(
                f"Duplicate visual object ID '{visual_object['id']}'"
            )
        object_ids.add(visual_object["id"])
        normalized.append(visual_object)

    return {
        "version": VISUAL_OBJECT_CONFIG_VERSION,
        "objects": normalized,
    }


def default_visual_objects() -> List[Dict[str, Any]]:
    """Return fresh editable copies of the layout that replaced old overlays."""
    return normalize_visual_object_config(
        {"objects": [dict(item) for item in DEFAULT_VISUAL_OBJECT_DATA]}
    )["objects"]


def resolve_visual_image_path(
    image_path: os.PathLike[str] | str,
    *,
    project_directory: os.PathLike[str] | str,
) -> Path:
    """Resolve project-relative or external image paths for canvas loading."""
    expanded = os.path.expandvars(str(image_path).strip())
    candidate = Path(expanded).expanduser()
    if not candidate.is_absolute():
        candidate = Path(project_directory) / candidate
    return candidate.resolve(strict=False)


def serialize_visual_image_path(
    image_path: os.PathLike[str] | str,
    *,
    project_directory: os.PathLike[str] | str,
) -> str:
    """Prefer portable project-relative paths while preserving external paths."""
    project_path = Path(project_directory).resolve(strict=False)
    resolved = resolve_visual_image_path(
        image_path,
        project_directory=project_path,
    )
    try:
        return resolved.relative_to(project_path).as_posix()
    except ValueError:
        return str(resolved)


def visual_object_bounds(value: Dict[str, Any]):
    """Return bounds; rectangles/images use top-left and circles use centre."""
    object_x = float(value["x"])
    object_y = float(value["y"])
    object_width = float(value["width"])
    object_height = float(value["height"])
    if value["type"] == "circle":
        return (
            object_x - object_width / 2,
            object_y - object_height / 2,
            object_x + object_width / 2,
            object_y + object_height / 2,
        )
    return (
        object_x,
        object_y,
        object_x + object_width,
        object_y + object_height,
    )


def visual_object_center(value: Dict[str, Any]):
    """Return the world position used for centred descriptive text."""
    left, bottom, right, top = visual_object_bounds(value)
    return ((left + right) / 2, (bottom + top) / 2)


def resolve_visual_object_bindings(
    value: Dict[str, Any],
    variable_catalog: Mapping[str, Any],
) -> tuple[Dict[str, Any], List[str]]:
    """Overlay valid live variable values while retaining stored fallbacks."""
    if not isinstance(value, dict):
        raise VisualObjectValidationError("Visual object must be a JSON object")
    if not isinstance(variable_catalog, Mapping):
        raise TypeError("variable_catalog must be a mapping")

    resolved = deepcopy(value)
    warnings: List[str] = []
    bindings = value.get("bindings", {})
    if not isinstance(bindings, Mapping):
        raise VisualObjectValidationError("'bindings' must be a JSON object")

    object_id = str(value.get("id", "visual object"))
    for property_name, variable_path in bindings.items():
        if property_name not in VISUAL_BINDABLE_PROPERTIES:
            raise VisualObjectValidationError(
                f"Unsupported binding property '{property_name}'"
            )
        if not isinstance(variable_path, str) or not _VARIABLE_PATH_RE.fullmatch(
            variable_path.strip()
        ):
            raise VisualObjectValidationError(
                f"Binding path for '{property_name}' is invalid: '{variable_path}'"
            )
        variable_path = variable_path.strip()
        fallback = value.get(property_name)

        if variable_path not in variable_catalog:
            warnings.append(
                f"Visual object '{object_id}' binding for '{property_name}' "
                f"references missing variable '{variable_path}'; using stored "
                f"value {fallback!r}."
            )
            continue

        supplied = variable_catalog[variable_path]
        if isinstance(supplied, Mapping):
            if supplied.get("valid") is False:
                invalid_value = supplied.get("value")
                warnings.append(
                    f"Visual object '{object_id}' binding for '{property_name}' "
                    f"resolved variable '{variable_path}' to an invalid numeric value "
                    f"{invalid_value!r}; using stored value {fallback!r}."
                )
                continue
            if "value" in supplied:
                supplied = supplied["value"]
        try:
            if isinstance(supplied, bool):
                raise TypeError
            number = float(supplied)
            if not math.isfinite(number):
                raise ValueError
        except (TypeError, ValueError):
            warnings.append(
                f"Visual object '{object_id}' binding for '{property_name}' "
                f"resolved variable '{variable_path}' to an invalid numeric value "
                f"{supplied!r}; using stored value {fallback!r}."
            )
            continue

        if property_name in ("width", "height") and number <= 0:
            warnings.append(
                f"Visual object '{object_id}' binding for '{property_name}' "
                f"resolved variable '{variable_path}' to non-positive value "
                f"{number!r}; using stored value {fallback!r}."
            )
            continue
        resolved[property_name] = number

    return resolved, warnings


class VisualObjectStore:
    """Load and atomically save canvas objects and their variable links."""

    def __init__(self, path: os.PathLike[str] | str):
        self.path = Path(path)

    def load(self) -> Dict[str, Any]:
        if not self.path.exists():
            return {
                "version": VISUAL_OBJECT_CONFIG_VERSION,
                "objects": default_visual_objects(),
            }
        with self.path.open("r", encoding="utf-8") as config_file:
            return normalize_visual_object_config(json.load(config_file))

    def save(self, objects: Iterable[Dict[str, Any]] | Dict[str, Any]) -> Dict[str, Any]:
        if isinstance(objects, dict):
            payload = objects
        else:
            payload = {"objects": list(objects)}
        normalized = normalize_visual_object_config(payload)

        self.path.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary_path = tempfile.mkstemp(
            prefix=f".{self.path.name}.",
            suffix=".tmp",
            dir=str(self.path.parent),
            text=True,
        )
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
                json.dump(normalized, handle, indent=2)
                handle.write("\n")
            os.replace(temporary_path, self.path)
        except Exception:
            try:
                os.unlink(temporary_path)
            except OSError:
                pass
            raise
        return normalized
