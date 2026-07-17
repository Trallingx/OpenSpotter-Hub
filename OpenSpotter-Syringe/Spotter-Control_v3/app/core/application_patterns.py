"""Application-level contracts for pattern workspaces.

The low-level registry only requires a manifest and numeric ``plan`` method.
Desktop shells need a richer, still UI-toolkit-neutral contract for locating
instances, creating editors, saving profiles, generating output, and exposing
field groups to workflow and visual-binding tools.
"""

from __future__ import annotations

import os
from collections.abc import Mapping as MappingABC
from dataclasses import dataclass
from pathlib import Path
from typing import (
    Any,
    Dict,
    Generic,
    Iterator,
    Mapping,
    MutableMapping,
    Optional,
    Protocol,
    Sequence,
    Tuple,
    TypeVar,
    Union,
    runtime_checkable,
)

from .plugins import PatternPlugin
from .schema import parse_widget_entries


PathLike = Union[str, os.PathLike]
RecipePayload = TypeVar("RecipePayload")
DEFAULT_MAX_RECIPE_TEXT_LENGTH = 120


class FrozenDict(MappingABC):
    """Small immutable mapping used by detached runtime snapshots."""

    def __init__(self, values: Mapping[str, Any]):
        self._data = dict(values)

    def __getitem__(self, key: str) -> Any:
        return self._data[key]

    def __iter__(self) -> Iterator[str]:
        return iter(self._data)

    def __len__(self) -> int:
        return len(self._data)

    def __deepcopy__(self, _memo):
        """Detached adapters may safely reuse this immutable value object."""

        return self


class RuntimeValueSource:
    """Widget-compatible scalar source backed by a detached value."""

    def __init__(self, value: Any):
        self._value = value

    def get(self) -> str:
        return str(self._value)


class RuntimeBooleanSource:
    """Widget-compatible boolean source backed by a detached value."""

    def __init__(self, value: Any):
        self._value = bool(value)

    def get(self) -> bool:
        return self._value


def runtime_entries(
    fields: Sequence[Any],
    values: Mapping[str, Any],
) -> list:
    """Build detached entry-like sources in schema order."""

    return [
        RuntimeValueSource(values.get(field.key, field.default))
        for field in fields
    ]


def capture_runtime_fields(
    entries: Sequence[Any],
    fields: Sequence[Any],
    context: str,
) -> Dict[str, Any]:
    """Strictly detach one schema-ordered field group from live widgets."""

    return parse_widget_entries(
        entries,
        fields,
        strict=True,
        context=context,
    )


def require_runtime_range(
    values: Mapping[str, Any],
    key: str,
    *,
    minimum: Optional[float] = None,
    maximum: Optional[float] = None,
    nonzero: bool = False,
    label: Optional[str] = None,
) -> None:
    """Validate one numeric direct-run value with a readable error."""

    value = float(values[key])
    display = label or key
    if minimum is not None and value < minimum:
        raise ValueError("{} must be at least {}".format(display, minimum))
    if maximum is not None and value > maximum:
        raise ValueError("{} must be at most {}".format(display, maximum))
    if nonzero and abs(value) < 1e-12:
        raise ValueError("{} must be non-zero".format(display))


def validated_runtime_text(
    value: Any,
    label: str,
    max_length: int = DEFAULT_MAX_RECIPE_TEXT_LENGTH,
) -> str:
    """Return safe single-line recipe metadata for generated output."""

    text = str(value).strip()
    if not text:
        raise ValueError("{} must not be empty".format(label))
    if len(text) > int(max_length):
        raise ValueError(
            "{} must be at most {} characters".format(label, max_length)
        )
    if any(ord(character) < 32 or ord(character) == 127 for character in text):
        raise ValueError(
            "{} must not contain newlines or control characters".format(label)
        )
    return text


def validate_runtime_container_ids(
    values: Mapping[str, Any],
    context: str,
    keys: Sequence[str] = ("loading_from", "leftovers_into"),
    minimum: int = 1,
    maximum: int = 6,
) -> None:
    """Validate recipe references to the configured container slots."""

    for key in keys:
        value = int(values[key])
        if value < minimum or value > maximum:
            raise ValueError(
                "{} {} must be between {} and {}".format(
                    context,
                    key.replace("_", " "),
                    minimum,
                    maximum,
                )
            )


@dataclass(frozen=True)
class PatternRecipeSnapshot(Generic[RecipePayload]):
    """Immutable, plugin-tagged recipe captured from a live workspace."""

    plugin_id: str
    number: int
    payload: RecipePayload
    estimated_work: int = 0

    def __post_init__(self) -> None:
        plugin_id = str(self.plugin_id).strip()
        if not plugin_id:
            raise ValueError("Runtime recipe plugin_id must not be empty")
        if int(self.number) < 1:
            raise ValueError("Runtime recipe number must be at least 1")
        if int(self.estimated_work) < 0:
            raise ValueError("Runtime recipe estimated_work must not be negative")
        object.__setattr__(self, "plugin_id", plugin_id)
        object.__setattr__(self, "number", int(self.number))
        object.__setattr__(self, "estimated_work", int(self.estimated_work))


@dataclass(frozen=True)
class RuntimeGenerationContext:
    """Core generation state shared with one selected pattern plugin."""

    config_dir: str
    global_values: Mapping[str, Any]
    workflow_json: str


@dataclass(frozen=True)
class WorkspaceSpec:
    """Stable metadata used by a generic pattern-workspace shell."""

    plugin_id: str
    parameter_title: str
    add_button_text: str
    remove_button_text: str
    notebook_attribute: str
    instance_map_attribute: str
    count_attribute: str
    state_count_key: str
    profile_key: str
    config_filename_template: str
    fallback_config_filename: str
    default_colors: Tuple[str, ...]

    def config_filename(self, index: int) -> str:
        """Return the indexed default filename for one editor instance."""

        return self.config_filename_template.format(index=int(index))

    def default_color(self, index: int) -> str:
        """Return the deterministic palette color for a one-based instance."""

        if not self.default_colors:
            raise ValueError(
                "Workspace {!r} must define at least one default color".format(
                    self.plugin_id
                )
            )
        return self.default_colors[
            (max(1, int(index)) - 1) % len(self.default_colors)
        ]

    def resolve_config_path(
        self,
        config_dir: PathLike,
        index: int,
    ) -> Path:
        """Resolve an indexed config, falling back to the plugin default."""

        directory = Path(config_dir)
        candidate = directory / self.config_filename(index)
        if candidate.is_file():
            return candidate
        return directory / self.fallback_config_filename


@dataclass(frozen=True)
class WorkspaceValueGroup:
    """One live editor field group exposed under a variable namespace."""

    namespace: str
    fields: Tuple[Any, ...]
    entries: Tuple[Any, ...]
    source: str


@runtime_checkable
class ApplicationPatternPlugin(PatternPlugin, Protocol):
    """Full contract consumed by a generic desktop application shell."""

    workspace: WorkspaceSpec

    def instance_map(self, gui: Any) -> MutableMapping[int, Any]:
        """Return the live one-based editor map owned by ``gui``."""

    def resolve_config_path(
        self,
        config_dir: PathLike,
        index: int,
    ) -> Path:
        """Resolve indexed defaults with the plugin's fallback policy."""

    def create_editor(
        self,
        parent: Any,
        config_dir: PathLike,
        index: int,
        on_name_changed: Any = None,
    ) -> Any:
        """Create one editor using indexed defaults and palette metadata."""

    def generate(
        self,
        gui: Any,
        filepath: Optional[PathLike] = None,
    ) -> Any:
        """Generate this plugin's output from the current application state."""

    def capture_runtime_recipes(
        self,
        gui: Any,
        global_values: Mapping[str, Any],
        workflow: Mapping[str, Any],
    ) -> Sequence[PatternRecipeSnapshot[Any]]:
        """Capture and validate detached direct-run recipes from ``gui``."""

    def generate_runtime(
        self,
        context: RuntimeGenerationContext,
        recipes: Sequence[PatternRecipeSnapshot[Any]],
        filepath: PathLike,
    ) -> Any:
        """Generate direct-run output from detached plugin recipe snapshots."""

    def serialize_editor(self, editor: Any) -> Mapping[str, Any]:
        """Return the canonical profile entry for one editor."""

    def persist_editor_defaults(
        self,
        editor: Any,
        config_dir: PathLike,
        index: int,
    ) -> Path:
        """Persist one editor's flattened defaults and return their path."""

    def validate_profile_entry(
        self,
        payload: Mapping[str, Any],
        index: int,
    ) -> Mapping[str, Any]:
        """Validate and normalize one serialized profile entry."""

    def restore_profile_entry(
        self,
        editor: Any,
        payload: Mapping[str, Any],
    ) -> None:
        """Restore one validated profile entry into a live editor."""

    def workflow_preview_groups(
        self,
        editor: Any,
        index: int,
    ) -> Sequence[WorkspaceValueGroup]:
        """Expose unindexed workflow namespaces for the active editor."""

    def visual_binding_groups(
        self,
        editor: Any,
        index: int,
    ) -> Sequence[WorkspaceValueGroup]:
        """Expose stable indexed namespaces for visual-object bindings."""


__all__ = [
    "ApplicationPatternPlugin",
    "DEFAULT_MAX_RECIPE_TEXT_LENGTH",
    "FrozenDict",
    "PatternRecipeSnapshot",
    "PathLike",
    "RuntimeBooleanSource",
    "RuntimeGenerationContext",
    "RuntimeValueSource",
    "WorkspaceSpec",
    "WorkspaceValueGroup",
    "capture_runtime_fields",
    "require_runtime_range",
    "runtime_entries",
    "validate_runtime_container_ids",
    "validated_runtime_text",
]
