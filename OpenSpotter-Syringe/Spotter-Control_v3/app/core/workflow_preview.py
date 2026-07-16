"""Plugin-neutral helpers for representative workflow event previews.

Workflow previews need realistic event values even though no pattern has been
planned yet.  Core owns the mutable preview context and machine-wide refill and
rinse mechanics.  Pattern plugins contribute their own representative spot,
maintenance, demand, and container calculations through a structural hook.
"""

from __future__ import annotations

import copy
from collections.abc import Mapping as MappingABC
from typing import (
    Any,
    Callable,
    Iterable,
    Mapping,
    Optional,
    Protocol,
    Tuple,
    runtime_checkable,
)

from .plugins import PluginManifest


CustomValueResolver = Callable[[str, Mapping[str, Any]], Any]
_MISSING = object()

RINSE_TRIGGERS = frozenset(
    (
        "syringe_empty_start",
        "rinse_cycle",
        "rinse_midpoint",
        "syringe_empty_end",
    )
)


class WorkflowPreviewError(ValueError):
    """Base error raised while composing representative preview values."""


class WorkflowPreviewConflictError(WorkflowPreviewError):
    """Raised when more than one plugin claims the same preview trigger."""


@runtime_checkable
class WorkflowPreviewPlugin(Protocol):
    """Optional structural capability implemented by pattern plugins.

    This protocol is deliberately separate from the required pattern-plugin
    API.  A numeric planner can therefore remain headless and minimal, while a
    desktop-capable plugin may opt into representative workflow previews.
    """

    manifest: PluginManifest
    workflow_preview_triggers: frozenset

    def enrich_workflow_preview(
        self,
        sample: "WorkflowPreviewSample",
    ) -> None:
        """Add plugin-owned representative values to ``sample``."""


def _get_nested(
    mapping: Mapping[str, Any],
    dotted_name: str,
    default: Any = None,
) -> Any:
    value: Any = mapping
    for part in dotted_name.split("."):
        if not isinstance(value, MappingABC) or part not in value:
            return default
        value = value[part]
    return value


def _set_nested(
    mapping: dict,
    dotted_name: str,
    value: Any,
) -> None:
    parts = [part for part in dotted_name.split(".") if part]
    if not parts:
        raise ValueError("Workflow preview path must not be empty")
    cursor = mapping
    for part in parts[:-1]:
        existing = cursor.get(part)
        if not isinstance(existing, dict):
            existing = {}
            cursor[part] = existing
        cursor = existing
    cursor[parts[-1]] = value


class WorkflowPreviewSample:
    """Mutable, detached context passed to one active preview plugin."""

    def __init__(
        self,
        context: Mapping[str, Any],
        trigger: str,
        workflow: Mapping[str, Any],
        custom_value_resolver: Optional[CustomValueResolver] = None,
    ):
        self._context = copy.deepcopy(dict(context))
        self.trigger = str(trigger)
        self.workflow = copy.deepcopy(dict(workflow))
        self._custom_value_resolver = custom_value_resolver

    @property
    def context(self) -> Mapping[str, Any]:
        """Read-only-by-convention view of the current nested context."""

        return self._context

    def result(self) -> dict:
        """Return a detached copy suitable for the workflow engine."""

        return copy.deepcopy(self._context)

    def get(self, path: str, default: Any = None) -> Any:
        """Read one dotted context path."""

        return _get_nested(self._context, path, default)

    def put(self, path: str, value: Any) -> None:
        """Set one dotted context path, creating nested mappings as needed."""

        _set_nested(self._context, path, value)

    def number(self, path: str, default: float = 0.0) -> float:
        """Read a finite-or-nonfinite numeric value with a safe fallback."""

        try:
            return float(self.get(path, default))
        except (TypeError, ValueError):
            return float(default)

    def integer(self, path: str, default: int = 0) -> int:
        """Read an integer-compatible value with a safe fallback."""

        try:
            return int(float(self.get(path, default)))
        except (TypeError, ValueError):
            return int(default)

    def custom_number(self, name: str, default: float) -> float:
        """Resolve one staged workflow custom variable as a number.

        Literal values provide a useful fallback when the workflow engine
        cannot resolve an expression.  A host-supplied resolver remains the
        authority when it succeeds.
        """

        fallback = float(default)
        for definition in self.workflow.get("custom_variables", ()):
            if not isinstance(definition, MappingABC):
                continue
            if str(definition.get("name", "")) != name:
                continue
            literal = definition.get("value")
            if isinstance(literal, (int, float)) and not isinstance(
                literal,
                bool,
            ):
                fallback = float(literal)
            break

        if self._custom_value_resolver is None:
            return fallback
        try:
            return float(
                self._custom_value_resolver(
                    name,
                    self._context,
                )
            )
        except Exception:
            return fallback

    def select_container(self, container_id: int) -> None:
        """Populate the active container from global machine coordinates."""

        selected = int(container_id)
        self.put("container.id", selected)
        self.put(
            "container.x",
            self.number("global.container{}_x".format(selected)),
        )
        self.put(
            "container.y",
            self.number("global.container{}_y".format(selected)),
        )
        self.put(
            "container.z",
            self.number("global.container{}_z".format(selected)),
        )


def populate_refill_preview(
    sample: WorkflowPreviewSample,
    *,
    remaining_spots_ul: float,
    cleaning_ul: float,
    reserve_basis_ul: float,
    container_id: int,
) -> None:
    """Populate core refill values from plugin-calculated liquid demand."""

    millimeters_per_microliter = sample.custom_number(
        "syringe_mm_per_ul",
        1.0,
    )
    remaining_spots_ul = max(0.0, float(remaining_spots_ul))
    cleaning_ul = max(0.0, float(cleaning_ul))
    reserve_basis_ul = max(0.0, float(reserve_basis_ul))
    reserve_ul = reserve_basis_ul * (
        1.0 + max(0.0, sample.number("global.drop_extra_aspirate"))
    )
    cap_mm = (
        max(0.0, sample.number("global.max_syringe_vol"))
        * millimeters_per_microliter
    )
    total_needed_mm = (
        remaining_spots_ul + cleaning_ul + reserve_ul
    ) * millimeters_per_microliter
    target_mm = min(total_needed_mm, cap_mm)
    priming_mm = (
        max(0.0, sample.number("global.priming_vol"))
        * millimeters_per_microliter
    )
    values = {
        "reason": "representative_preview",
        "dynamic": total_needed_mm > cap_mm,
        "container_id": int(container_id),
        "fill_mm": target_mm + priming_mm,
        "priming_mm": priming_mm,
        "target_fill_mm": target_mm,
        "target_fill_ul": (
            target_mm / millimeters_per_microliter
            if millimeters_per_microliter > 0
            else 0.0
        ),
        "remaining_spots_mm": (
            remaining_spots_ul * millimeters_per_microliter
        ),
        "cleaning_mm": cleaning_ul * millimeters_per_microliter,
        "reserve_mm": reserve_ul * millimeters_per_microliter,
        "total_needed_mm": total_needed_mm,
        "cap_mm": cap_mm,
    }
    for key, value in values.items():
        sample.put("runtime.refill.{}".format(key), value)


def enrich_core_workflow_preview(sample: WorkflowPreviewSample) -> None:
    """Add representative values for core-owned rinse mechanics."""

    if sample.trigger not in RINSE_TRIGGERS:
        return
    sample.put("runtime.rinse.cycle", 1)
    sample.put(
        "runtime.rinse.phase",
        2
        if sample.trigger in ("rinse_midpoint", "syringe_empty_end")
        else 1,
    )
    sample.put(
        "runtime.rinse.max_mm",
        sample.number("global.max_syringe_mm"),
    )
    sample.put(
        "runtime.rinse.min_mm",
        sample.number("global.min_syringe_mm"),
    )


def _preview_capabilities(
    plugins: Iterable[object],
) -> Tuple[WorkflowPreviewPlugin, ...]:
    return tuple(
        plugin
        for plugin in plugins
        if isinstance(plugin, WorkflowPreviewPlugin)
    )


def _plugin_id(plugin: WorkflowPreviewPlugin) -> str:
    return str(plugin.manifest.id)


def _active_preview_plugin(
    sample: WorkflowPreviewSample,
    plugins: Tuple[WorkflowPreviewPlugin, ...],
) -> Tuple[Optional[WorkflowPreviewPlugin], bool]:
    owners = tuple(
        plugin
        for plugin in plugins
        if sample.trigger in plugin.workflow_preview_triggers
    )
    if len(owners) > 1:
        raise WorkflowPreviewConflictError(
            "Workflow preview trigger {!r} is claimed by: {}".format(
                sample.trigger,
                ", ".join(_plugin_id(plugin) for plugin in owners),
            )
        )
    if owners:
        return owners[0], True

    current_kind = sample.get("runtime.job.kind", _MISSING)
    if current_kind is not _MISSING:
        current_kind = str(current_kind)
        for plugin in plugins:
            if _plugin_id(plugin) == current_kind:
                return plugin, False

    # Preserve the historical deterministic fallback for previews without an
    # active workspace while avoiding knowledge of any built-in plugin ID.
    return (plugins[0], current_kind is _MISSING) if plugins else (None, False)


def dispatch_workflow_preview(
    context: Mapping[str, Any],
    trigger: str,
    workflow: Mapping[str, Any],
    plugins: Iterable[object],
    custom_value_resolver: Optional[CustomValueResolver] = None,
) -> dict:
    """Compose core and active-plugin values for one representative event."""

    sample = WorkflowPreviewSample(
        context,
        trigger,
        workflow,
        custom_value_resolver,
    )
    preview_plugins = _preview_capabilities(plugins)
    active_plugin, should_set_job_kind = _active_preview_plugin(
        sample,
        preview_plugins,
    )
    if active_plugin is not None and (
        should_set_job_kind
        or sample.trigger in active_plugin.workflow_preview_triggers
    ):
        sample.put("runtime.job.kind", _plugin_id(active_plugin))

    enrich_core_workflow_preview(sample)
    if active_plugin is not None:
        active_plugin.enrich_workflow_preview(sample)
    return sample.result()


__all__ = [
    "CustomValueResolver",
    "RINSE_TRIGGERS",
    "WorkflowPreviewConflictError",
    "WorkflowPreviewError",
    "WorkflowPreviewPlugin",
    "WorkflowPreviewSample",
    "dispatch_workflow_preview",
    "enrich_core_workflow_preview",
    "populate_refill_preview",
]
