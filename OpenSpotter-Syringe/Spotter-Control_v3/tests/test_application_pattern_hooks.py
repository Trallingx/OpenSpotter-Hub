import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from app.core.application_patterns import (
    ApplicationPatternPlugin,
    WorkspaceSpec,
)
from app.plugins.grid.editor import Grid
from app.plugins.grid.fields import (
    CLEANING_FIELDS,
    GRID_FIELDS,
    WASHING_FIELDS,
)
from app.plugins.grid.plugin import GridPlugin
from app.plugins.spiral.editor import SpiralGrid
from app.plugins.spiral.fields import SPIRAL_FIELDS
from app.plugins.spiral.plugin import SpiralPlugin


class FakeEntry:
    def __init__(self, value):
        self.value = str(value)

    def get(self):
        return self.value

    def delete(self, _start, _end):
        self.value = ""

    def insert(self, _index, value):
        self.value = str(value)


class FakeVariable:
    def __init__(self, value):
        self.value = value
        self.callbacks = []

    def get(self):
        return self.value

    def set(self, value):
        self.value = value
        for callback in tuple(self.callbacks):
            callback()

    def trace_add(self, _mode, callback):
        self.callbacks.append(callback)
        return "trace-{}".format(len(self.callbacks))


def entries_for(fields, values=None):
    values = values or {}
    return [
        FakeEntry(values.get(field.key, field.default))
        for field in fields
    ]


class ApplicationPatternContractTests(unittest.TestCase):
    def test_workspace_spec_resolves_indexed_defaults_and_palette(self):
        spec = WorkspaceSpec(
            plugin_id="sample",
            parameter_title="SAMPLE PARAMETERS",
            add_button_text="ADD SAMPLE",
            remove_button_text="REMOVE SAMPLE",
            notebook_attribute="sample_tabs",
            instance_map_attribute="sample_tab_dict",
            count_attribute="sample_count",
            state_count_key="sample_count",
            profile_key="sample_settings",
            config_filename_template="config_sample_{index}.json",
            fallback_config_filename="config_sample_1.json",
            default_colors=("red", "blue"),
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            directory = Path(temp_dir)
            fallback = directory / "config_sample_1.json"
            fallback.write_text("{}\n", encoding="utf-8")

            self.assertEqual(spec.resolve_config_path(directory, 2), fallback)
            indexed = directory / "config_sample_2.json"
            indexed.write_text("{}\n", encoding="utf-8")
            self.assertEqual(spec.resolve_config_path(directory, 2), indexed)

        self.assertEqual(spec.default_color(1), "red")
        self.assertEqual(spec.default_color(2), "blue")
        self.assertEqual(spec.default_color(3), "red")

    def test_builtins_satisfy_the_application_contract(self):
        self.assertIsInstance(GridPlugin(), ApplicationPatternPlugin)
        self.assertIsInstance(SpiralPlugin(), ApplicationPatternPlugin)


class PluginHookTests(unittest.TestCase):
    def test_instance_maps_and_generation_delegate_to_plugin_modules(self):
        grid = GridPlugin()
        spiral = SpiralPlugin()
        gui = SimpleNamespace(
            grid_tab_dict={1: object()},
            spiral_tab_dict={2: object()},
        )

        self.assertIs(grid.instance_map(gui), gui.grid_tab_dict)
        self.assertIs(spiral.instance_map(gui), gui.spiral_tab_dict)

        with mock.patch(
            "app.plugins.grid.generation.save_grid_gcode",
            return_value="grid.gcode",
        ) as generate_grid:
            self.assertEqual(grid.generate(gui, "grid.gcode"), "grid.gcode")
            generate_grid.assert_called_once_with(gui, "grid.gcode")

        with mock.patch(
            "app.plugins.spiral.generation.save_spiral_gcode",
            return_value="spiral.gcode",
        ) as generate_spiral:
            self.assertEqual(
                spiral.generate(gui, "spiral.gcode"),
                "spiral.gcode",
            )
            generate_spiral.assert_called_once_with(gui, "spiral.gcode")

    def test_editor_factories_apply_fallback_configs_and_default_colors(self):
        parent = object()
        with tempfile.TemporaryDirectory() as temp_dir:
            directory = Path(temp_dir)
            (directory / "config_grid_1.json").write_text(
                "{}\n",
                encoding="utf-8",
            )
            (directory / "config_spiral_1.json").write_text(
                "{}\n",
                encoding="utf-8",
            )

            with mock.patch("app.plugins.grid.editor.Grid") as editor_type:
                GridPlugin().create_editor(
                    parent,
                    directory,
                    2,
                    on_name_changed="grid-callback",
                )
                editor_type.assert_called_once_with(
                    parent,
                    config=str(directory / "config_grid_1.json"),
                    background="orange",
                    config_dir=str(directory),
                    grid_number=2,
                    on_name_changed="grid-callback",
                )

            with mock.patch(
                "app.plugins.spiral.editor.SpiralGrid"
            ) as editor_type:
                SpiralPlugin().create_editor(
                    parent,
                    directory,
                    2,
                    on_name_changed="spiral-callback",
                )
                editor_type.assert_called_once_with(
                    parent,
                    config=str(directory / "config_spiral_1.json"),
                    background="orange",
                    config_dir=str(directory),
                    spiral_number=2,
                    on_name_changed="spiral-callback",
                )

    def test_profile_hooks_persist_validate_restore_and_expose_groups(self):
        class HookEditor:
            grid_number = 3
            spiral_number = 4
            grid_entry = ["grid-entry"]
            cleaning_entry = ["cleaning-entry"]
            washing_entry = ["washing-entry"]
            spiral_entry = ["spiral-entry"]

            def __init__(self, payload):
                self.payload = payload
                self.restored = None

            def serialize(self):
                return self.payload

            def defaults_dict(self):
                return {"saved": True}

            def restore(self, payload):
                self.restored = payload

        grid = GridPlugin()
        grid_payload = {
            "grid": {},
            "cleaning": {},
            "washing": {},
            "cleaning_enabled": True,
        }
        grid_editor = HookEditor(grid_payload)
        self.assertEqual(grid.serialize_editor(grid_editor), grid_payload)
        grid.restore_profile_entry(grid_editor, grid_payload)
        self.assertEqual(grid_editor.restored, grid_payload)
        self.assertEqual(
            [group.namespace for group in grid.workflow_preview_groups(
                grid_editor,
                3,
            )],
            ["grid", "cleaning", "washing"],
        )
        self.assertEqual(
            [group.namespace for group in grid.visual_binding_groups(
                grid_editor,
                3,
            )],
            ["grid.3", "cleaning.3", "washing.3"],
        )

        spiral = SpiralPlugin()
        spiral_payload = {"spiral": {}}
        spiral_editor = HookEditor(spiral_payload)
        spiral.restore_profile_entry(spiral_editor, spiral_payload)
        self.assertEqual(spiral_editor.restored, spiral_payload)
        self.assertEqual(
            spiral.workflow_preview_groups(spiral_editor, 4)[0].namespace,
            "spiral",
        )
        self.assertEqual(
            spiral.visual_binding_groups(spiral_editor, 4)[0].namespace,
            "spiral.4",
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            grid_path = grid.persist_editor_defaults(
                grid_editor,
                temp_dir,
                3,
            )
            spiral_path = spiral.persist_editor_defaults(
                spiral_editor,
                temp_dir,
                4,
            )
            self.assertEqual(
                json.loads(grid_path.read_text(encoding="utf-8")),
                {"saved": True},
            )
            self.assertEqual(
                json.loads(spiral_path.read_text(encoding="utf-8")),
                {"saved": True},
            )

        with self.assertRaisesRegex(ValueError, "true or false"):
            grid.validate_profile_entry(
                {
                    "grid": {},
                    "cleaning": {},
                    "washing": {},
                    "cleaning_enabled": "yes",
                },
                1,
            )
        with self.assertRaisesRegex(ValueError, "'spiral' settings"):
            spiral.validate_profile_entry({"spiral": []}, 1)


class EditorSerializationTests(unittest.TestCase):
    def test_grid_editor_neutral_aliases_and_round_trip(self):
        editor = Grid.__new__(Grid)
        editor.gui = SimpleNamespace()
        editor.grid_number = 1
        editor.default_color = "green"
        editor.on_name_changed = None
        editor.grid_name_var = FakeVariable("Grid A")
        editor.grid_color_var = FakeVariable("orange")
        editor.grid_entry = entries_for(GRID_FIELDS)
        editor.cleaning_entry = entries_for(CLEANING_FIELDS)
        editor.washing_entry = entries_for(WASHING_FIELDS)
        editor.cleaning_enabled = FakeVariable(False)
        editor.washing_enabled = FakeVariable(False)
        editor.wash_after_loading_enabled = FakeVariable(False)
        editor.final_rinse_enabled = FakeVariable(False)
        editor.final_rinse_add_cleaning_grid = FakeVariable(False)
        editor.cleaning_widgets = []
        editor.washing_widgets = []
        editor.wash_after_loading_widgets = []
        editor.final_rinse_widgets = []

        self.assertEqual(editor.get_name(), editor.get_grid_name())
        self.assertEqual(editor.get_color(), editor.get_grid_color())
        payload = editor.serialize()
        payload["grid_name"] = "Restored Grid"
        payload["grid"]["rows"] = 4
        payload["cleaning_enabled"] = True
        editor.restore(payload)

        self.assertEqual(editor.get_name(), "Restored Grid")
        self.assertEqual(editor.grid_entry[0].get(), "4")
        self.assertTrue(editor.cleaning_enabled.get())
        self.assertEqual(editor.defaults_dict()["grid_name"], "Restored Grid")

    def test_spiral_editor_round_trip_and_name_change_callback(self):
        renamed = []
        editor = SpiralGrid.__new__(SpiralGrid)
        editor.spiral_number = 2
        editor.default_color = "orange"
        editor.on_name_changed = renamed.append
        editor.spiral_name_var = FakeVariable("Spiral A")
        editor.spiral_color_var = FakeVariable("blue")
        editor.spiral_entry = entries_for(SPIRAL_FIELDS)
        editor._install_name_change_trace()

        editor.set_name("Renamed Spiral")
        self.assertEqual(renamed, ["Renamed Spiral"])
        self.assertEqual(editor.get_name(), editor.get_grid_name())
        self.assertEqual(editor.get_color(), editor.get_grid_color())

        payload = editor.serialize()
        payload["spiral"]["turns"] = 7
        payload["spiral_color"] = "purple"
        editor.restore(payload)

        self.assertEqual(editor.spiral_entry[3].get(), "7")
        self.assertEqual(editor.get_color(), "purple")
        self.assertEqual(
            editor.defaults_dict()["spiral_name"],
            "Renamed Spiral",
        )


if __name__ == "__main__":
    unittest.main()
