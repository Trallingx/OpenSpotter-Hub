"""Spiral geometry plugin for OpenSpotter-Syringe.

The plugin produces numeric point events.  The runtime workflow owns all machine
command text, keeping pattern geometry independent from the output language.
"""
from collections.abc import Mapping as MappingABC
from collections.abc import MutableMapping
from math import cos, pi, sin, sqrt
from pathlib import Path
from typing import Any, Mapping, Sequence

from ...core.application_patterns import WorkspaceSpec, WorkspaceValueGroup
from ...core.storage import write_json_atomic
from .fields import SPIRAL_FIELDS
from .manifest import PLUGIN_MANIFEST
from .workflow import WORKFLOW_CONTRIBUTION
from .workflow_preview import SPIRAL_WORKFLOW_PREVIEW_TRIGGERS


SPIRAL_WORKSPACE = WorkspaceSpec(
    plugin_id=PLUGIN_MANIFEST.id,
    parameter_title="SPIRAL PARAMETERS",
    add_button_text="ADD SPIRAL",
    remove_button_text="REMOVE SPIRAL",
    notebook_attribute="spiral_tabs",
    instance_map_attribute="spiral_tab_dict",
    count_attribute="spiral_count",
    state_count_key="spiral_count",
    profile_key="spiral_settings",
    config_filename_template="config_spiral_{index}.json",
    fallback_config_filename="config_spiral_1.json",
    default_colors=(
        "lightgreen",
        "orange",
        "lightblue",
        "gold",
        "violet",
        "salmon",
    ),
)


def _as_bool(value):
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        return value.strip().lower() in ("1", "true", "yes", "on")
    return False


def _spiral_points(
    center_x,
    center_y,
    start_radius,
    turns,
    spacing_mm,
    resolution_radians,
    theta_offset=0.0,
):
    # Archimedean spiral: r = a + b*theta
    # b controls radial spacing per revolution.
    b = max(1e-9, spacing_mm / (2.0 * pi))
    max_theta = 2.0 * pi * max(0.0, turns)
    step = float(resolution_radians)
    if step <= 0:
        raise ValueError("Spiral resolution must be positive")

    points = []
    theta = 0.0
    while theta <= max_theta + 1e-9:
        adjusted_theta = theta + theta_offset
        radius = start_radius + b * theta
        x = center_x + radius * cos(adjusted_theta)
        y = center_y + radius * sin(adjusted_theta)
        points.append((x, y, adjusted_theta, radius))
        theta += step

    return points


def _interleave_point_sets(point_sets):
    max_len = max((len(points) for points in point_sets), default=0)
    for index in range(max_len):
        for points in point_sets:
            if index < len(points):
                yield points[index]


class SpiralPlugin:
    manifest = PLUGIN_MANIFEST
    name = PLUGIN_MANIFEST.id
    workspace = SPIRAL_WORKSPACE
    workflow_contribution = WORKFLOW_CONTRIBUTION
    workflow_preview_triggers = SPIRAL_WORKFLOW_PREVIEW_TRIGGERS

    def plan(
        self,
        context: Mapping[str, Any],
    ) -> Sequence[Mapping[str, Any]]:
        params = context.get('params', {}) or {}

        center_x = float(params.get('center_x', 0.0))
        center_y = float(params.get('center_y', 0.0))
        start_radius = float(params.get('start_radius', 0.0))
        turns = float(params.get('turns', 5.0))
        num_starts = max(1, int(params.get('num_starts', 1)))
        spacing_mm = float(params.get('spacing_mm', 1.5))
        dispense_vol_ul = float(params.get('dispense_vol', 0.003))
        if start_radius < 0:
            raise ValueError("Spiral start radius cannot be negative")
        if turns < 0:
            raise ValueError("Spiral turns cannot be negative")
        if spacing_mm <= 0:
            raise ValueError("Spiral spacing must be positive")
        if dispense_vol_ul < 0:
            raise ValueError("Spiral dispense volume cannot be negative")
        spiral_mode = str(params.get('spiral_mode', 'drop')).strip().lower()
        interleave = _as_bool(params.get('interleave', False))
        if spiral_mode == 'continuous' and interleave and num_starts > 1:
            raise ValueError(
                "Interleaving multiple starts is not supported in continuous spiral mode"
            )
        resolution_radians = float(context['resolution_radians'])
        millimeters_per_microliter = float(context['millimeters_per_microliter'])

        # Build one point set per start with equal angular offsets.
        point_sets = []
        for start_index in range(num_starts):
            theta_offset = (2.0 * pi * start_index) / float(num_starts)
            point_sets.append([
                (start_index, *point)
                for point in _spiral_points(
                    center_x=center_x,
                    center_y=center_y,
                    start_radius=start_radius,
                    turns=turns,
                    spacing_mm=spacing_mm,
                    resolution_radians=resolution_radians,
                    theta_offset=theta_offset,
                )
            ])

        if interleave:
            path = list(_interleave_point_sets(point_sets))
        else:
            path = [point for points in point_sets for point in points]

        if not path:
            return []

        planned_points = []
        previous_by_start = {}
        for index, (start_index, x, y, theta, radius) in enumerate(path):
            previous_point = previous_by_start.get(start_index)
            if spiral_mode == 'continuous' and previous_point is not None:
                dx = x - previous_point[0]
                dy = y - previous_point[1]
                segment_length = sqrt(dx * dx + dy * dy)
                segment_ul = max(dispense_vol_ul, segment_length * dispense_vol_ul)
                continuous = True
            else:
                segment_length = 0.0
                segment_ul = dispense_vol_ul
                continuous = False
            planned_points.append({
                'index': index,
                'start_index': start_index,
                'x': x,
                'y': y,
                'theta': theta,
                'radius': radius,
                'segment_length': segment_length,
                'dispense_ul': segment_ul,
                'dispense_mm': segment_ul * millimeters_per_microliter,
                'continuous': continuous,
            })
            previous_by_start[start_index] = (x, y)
        return planned_points

    def instance_map(self, gui):
        """Return the live spiral editor mapping from an application shell."""

        instances = getattr(
            gui,
            self.workspace.instance_map_attribute,
            None,
        )
        if not isinstance(instances, MutableMapping):
            raise TypeError(
                "{} must expose a mutable {!r} mapping".format(
                    type(gui).__name__,
                    self.workspace.instance_map_attribute,
                )
            )
        return instances

    def resolve_config_path(self, config_dir, index):
        """Resolve indexed defaults, falling back to config_spiral_1.json."""

        return self.workspace.resolve_config_path(config_dir, index)

    def create_editor(
        self,
        parent,
        config_dir,
        index,
        on_name_changed=None,
    ):
        """Create one spiral editor with plugin-owned defaults."""

        from .editor import SpiralGrid

        config_path = self.resolve_config_path(config_dir, index)
        return SpiralGrid(
            parent,
            config=str(config_path),
            background=self.workspace.default_color(index),
            config_dir=str(Path(config_dir)),
            spiral_number=int(index),
            on_name_changed=on_name_changed,
        )

    def generate(self, gui, filepath=None):
        """Generate spiral G-code through the plugin-owned implementation."""

        from .generation import save_spiral_gcode

        return save_spiral_gcode(gui, filepath)

    def capture_runtime_recipes(self, gui, global_values, workflow):
        """Capture immutable direct-run recipes through the spiral runtime."""

        from .runtime import capture_runtime_recipes

        return capture_runtime_recipes(
            self.instance_map(gui),
            global_values,
            workflow,
        )

    def generate_runtime(self, context, recipes, filepath):
        """Generate a direct-run artifact without retaining live widgets."""

        from .runtime import build_generation_adapter

        return self.generate(
            build_generation_adapter(context, recipes),
            filepath,
        )

    def build_canvas_preview(self, gui, context):
        """Describe all live spirals with renderer-neutral preview primitives."""

        from .preview import build_spiral_canvas_preview

        recipes = []
        for number, editor in sorted(self.instance_map(gui).items()):
            recipe = dict(self.serialize_editor(editor))
            recipe["pattern_number"] = int(number)
            recipes.append(recipe)
        if not recipes:
            from ...core.canvas import CanvasPreview

            return CanvasPreview.empty()
        return build_spiral_canvas_preview(self, recipes, context)

    def serialize_editor(self, editor):
        """Return one canonical spiral profile entry."""

        payload = editor.serialize()
        if not isinstance(payload, MappingABC):
            raise TypeError("Spiral editor serialize() must return a mapping")
        return dict(payload)

    def persist_editor_defaults(self, editor, config_dir, index):
        """Atomically persist one flattened indexed spiral configuration."""

        payload = editor.defaults_dict()
        if not isinstance(payload, MappingABC):
            raise TypeError(
                "Spiral editor defaults_dict() must return a mapping"
            )
        path = Path(config_dir) / self.workspace.config_filename(index)
        return write_json_atomic(path, payload)

    def validate_profile_entry(self, payload, index):
        """Validate the structural spiral profile contract used by the shell."""

        if not isinstance(payload, MappingABC):
            raise ValueError(
                "Spiral {} settings must be a JSON object".format(index)
            )
        normalized = dict(payload)
        values = normalized.get("spiral", {})
        if not isinstance(values, MappingABC):
            raise ValueError(
                "Spiral {} 'spiral' settings must be a JSON object".format(
                    index
                )
            )
        normalized["spiral"] = dict(values)
        return normalized

    def restore_profile_entry(self, editor, payload):
        """Validate and restore one spiral profile into its live editor."""

        index = int(getattr(editor, "spiral_number", 0) or 0)
        editor.restore(self.validate_profile_entry(payload, index))

    @staticmethod
    def _value_group(namespace, editor, source):
        return WorkspaceValueGroup(
            namespace=namespace,
            fields=tuple(SPIRAL_FIELDS),
            entries=tuple(getattr(editor, "spiral_entry", ()) or ()),
            source=source,
        )

    def workflow_preview_groups(self, editor, index):
        """Expose the active unindexed spiral workflow namespace."""

        return (
            self._value_group(
                "spiral",
                editor,
                "Spiral {} runtime inputs".format(index),
            ),
        )

    def enrich_workflow_preview(self, sample):
        """Add representative spiral-owned event values to a preview."""

        from .workflow_preview import enrich_spiral_workflow_preview

        enrich_spiral_workflow_preview(sample)

    def visual_binding_groups(self, editor, index):
        """Expose the stable indexed spiral visual-binding namespace."""

        return (
            self._value_group(
                "spiral.{}".format(index),
                editor,
                "Spiral {}".format(index),
            ),
        )


def register():
    return SpiralPlugin()


from .runtime import SpiralJobSnapshot


__all__ = [
    "PLUGIN_MANIFEST",
    "SPIRAL_WORKSPACE",
    "SpiralJobSnapshot",
    "SpiralPlugin",
    "_as_bool",
    "_interleave_point_sets",
    "_spiral_points",
    "register",
]
