"""Registry-facing implementation of the built-in grid plugin."""

from collections.abc import Mapping as MappingABC
from collections.abc import MutableMapping
from pathlib import Path
from typing import Any, Mapping, Sequence

from ...core.application_patterns import WorkspaceSpec, WorkspaceValueGroup
from ...core.storage import write_json_atomic
from .fields import CLEANING_FIELDS, GRID_FIELDS, WASHING_FIELDS
from .geometry import create_coordinates
from .manifest import PLUGIN_MANIFEST
from .workflow import WORKFLOW_CONTRIBUTION
from .workflow_preview import GRID_WORKFLOW_PREVIEW_TRIGGERS


GRID_WORKSPACE = WorkspaceSpec(
    plugin_id=PLUGIN_MANIFEST.id,
    parameter_title="GRID PARAMETERS",
    add_button_text="ADD GRID",
    remove_button_text="REMOVE GRID",
    notebook_attribute="grid_tabs",
    instance_map_attribute="grid_tab_dict",
    count_attribute="grid_count",
    state_count_key="grid_count",
    profile_key="grid_settings",
    config_filename_template="config_grid_{index}.json",
    fallback_config_filename="config_grid_1.json",
    default_colors=(
        "lightgreen",
        "orange",
        "lightblue",
        "gold",
        "violet",
        "salmon",
    ),
)


class GridPlugin:
    """Built-in grid planner plus application-workspace integration hooks."""

    manifest = PLUGIN_MANIFEST
    name = PLUGIN_MANIFEST.id
    workspace = GRID_WORKSPACE
    workflow_contribution = WORKFLOW_CONTRIBUTION
    workflow_preview_triggers = GRID_WORKFLOW_PREVIEW_TRIGGERS

    def plan(
        self,
        context: Mapping[str, Any],
    ) -> Sequence[Mapping[str, Any]]:
        params = context.get("params", {}) or {}
        rows = int(params.get("rows", 0))
        cols = int(params.get("cols", 0))
        if rows < 0 or cols < 0:
            raise ValueError("Grid dimensions cannot be negative")
        coordinates = create_coordinates(
            rows,
            cols,
            float(context.get("x_offset", 0.0)),
            float(params.get("grid_offset_x", 0.0)),
            float(params.get("pitch_x", 0.0)),
            float(context.get("y_offset", 0.0)),
            float(params.get("grid_offset_y", 0.0)),
            float(params.get("pitch_y", 0.0)),
        )
        return [
            {
                "index": index,
                "row": index // cols if cols else 0,
                "column": index % cols if cols else 0,
                "x": x,
                "y": y,
            }
            for index, (x, y) in enumerate(coordinates)
        ]

    def instance_map(self, gui):
        """Return the live grid editor mapping from an application shell."""

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
        """Resolve indexed defaults, falling back to config_grid_1.json."""

        return self.workspace.resolve_config_path(config_dir, index)

    def create_editor(
        self,
        parent,
        config_dir,
        index,
        on_name_changed=None,
    ):
        """Create one grid editor without exposing legacy layout arguments."""

        from .editor import Grid

        config_path = self.resolve_config_path(config_dir, index)
        return Grid(
            parent,
            config=str(config_path),
            background=self.workspace.default_color(index),
            config_dir=str(Path(config_dir)),
            grid_number=int(index),
            on_name_changed=on_name_changed,
        )

    def generate(self, gui, filepath=None):
        """Generate grid G-code through the plugin-owned implementation."""

        from .generation import save_grid_gcode

        return save_grid_gcode(gui, filepath)

    def capture_runtime_recipes(self, gui, global_values, workflow):
        """Capture immutable direct-run recipes through the grid runtime."""

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
        """Describe all live grids with renderer-neutral preview primitives."""

        from .preview import build_grid_canvas_preview

        recipes = []
        for number, editor in sorted(self.instance_map(gui).items()):
            recipe = dict(self.serialize_editor(editor))
            recipe["pattern_number"] = int(number)
            recipes.append(recipe)
        if not recipes:
            from ...core.canvas import CanvasPreview

            return CanvasPreview.empty()
        return build_grid_canvas_preview(self, recipes, context)

    def serialize_editor(self, editor):
        """Return one canonical grid profile entry."""

        payload = editor.serialize()
        if not isinstance(payload, MappingABC):
            raise TypeError("Grid editor serialize() must return a mapping")
        return dict(payload)

    def persist_editor_defaults(self, editor, config_dir, index):
        """Atomically persist one flattened indexed grid configuration."""

        payload = editor.defaults_dict()
        if not isinstance(payload, MappingABC):
            raise TypeError("Grid editor defaults_dict() must return a mapping")
        path = Path(config_dir) / self.workspace.config_filename(index)
        return write_json_atomic(path, payload)

    def validate_profile_entry(self, payload, index):
        """Validate the structural grid profile contract used by the shell."""

        if not isinstance(payload, MappingABC):
            raise ValueError(
                "Grid {} settings must be a JSON object".format(index)
            )
        normalized = dict(payload)
        for subsection in ("grid", "cleaning", "washing"):
            values = normalized.get(subsection, {})
            if not isinstance(values, MappingABC):
                raise ValueError(
                    "Grid {} {!r} settings must be a JSON object".format(
                        index,
                        subsection,
                    )
                )
            normalized[subsection] = dict(values)
        for flag in (
            "cleaning_enabled",
            "washing_enabled",
            "wash_after_loading",
            "final_rinse_enabled",
            "final_rinse_add_cleaning_grid",
        ):
            if flag in normalized and not isinstance(
                normalized[flag],
                bool,
            ):
                raise ValueError(
                    "Grid {} {!r} setting must be true or false".format(
                        index,
                        flag,
                    )
                )
        return normalized

    def restore_profile_entry(self, editor, payload):
        """Validate and restore one grid profile into its live editor."""

        index = int(getattr(editor, "grid_number", 0) or 0)
        editor.restore(self.validate_profile_entry(payload, index))

    @staticmethod
    def _value_group(namespace, fields, entries, source):
        return WorkspaceValueGroup(
            namespace=namespace,
            fields=tuple(fields),
            entries=tuple(entries or ()),
            source=source,
        )

    def workflow_preview_groups(self, editor, index):
        """Expose the active unindexed grid workflow namespaces."""

        source = "Grid {} runtime inputs".format(index)
        return (
            self._value_group(
                "grid",
                GRID_FIELDS,
                getattr(editor, "grid_entry", ()),
                source,
            ),
            self._value_group(
                "cleaning",
                CLEANING_FIELDS,
                getattr(editor, "cleaning_entry", ()),
                source,
            ),
            self._value_group(
                "washing",
                WASHING_FIELDS,
                getattr(editor, "washing_entry", ()),
                source,
            ),
        )

    def enrich_workflow_preview(self, sample):
        """Add representative grid-owned event values to a preview."""

        from .workflow_preview import enrich_grid_workflow_preview

        enrich_grid_workflow_preview(sample)

    def visual_binding_groups(self, editor, index):
        """Expose stable indexed grid namespaces for visual bindings."""

        return (
            self._value_group(
                "grid.{}".format(index),
                GRID_FIELDS,
                getattr(editor, "grid_entry", ()),
                "Grid {}".format(index),
            ),
            self._value_group(
                "cleaning.{}".format(index),
                CLEANING_FIELDS,
                getattr(editor, "cleaning_entry", ()),
                "Grid {} cleaning".format(index),
            ),
            self._value_group(
                "washing.{}".format(index),
                WASHING_FIELDS,
                getattr(editor, "washing_entry", ()),
                "Grid {} washing".format(index),
            ),
        )


def register() -> GridPlugin:
    """Construct the built-in grid plugin for registry discovery."""

    return GridPlugin()


from .runtime import GridJobSnapshot


__all__ = [
    "GRID_WORKSPACE",
    "GridJobSnapshot",
    "GridPlugin",
    "PLUGIN_MANIFEST",
    "register",
]
