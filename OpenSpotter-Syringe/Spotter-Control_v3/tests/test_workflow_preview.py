import inspect
import unittest
from types import SimpleNamespace
from unittest import mock

from app import gcode_workflow
from app.core.plugins import PluginManifest
from app.core.workflow_preview import (
    WorkflowPreviewPlugin,
    dispatch_workflow_preview,
)
from app.gcode_editor import GCodeWorkflowEditor
from app.plugins.grid.plugin import GridPlugin
from app.plugins.spiral.plugin import SpiralPlugin


class SyntheticPreviewPlugin:
    manifest = PluginManifest(
        id="synthetic",
        display_name="Synthetic",
        version="1.0.0",
    )
    workflow_preview_triggers = frozenset(("synthetic_event",))

    def __init__(self):
        self.calls = []

    def enrich_workflow_preview(self, sample):
        self.calls.append(sample.trigger)
        sample.put("runtime.synthetic.value", 42)


class WorkflowPreviewDispatchTests(unittest.TestCase):
    def test_structural_capability_dispatches_a_synthetic_plugin(self):
        plugin = SyntheticPreviewPlugin()
        original = {"global": {"movement_speed": 100}}

        result = dispatch_workflow_preview(
            original,
            "synthetic_event",
            {"custom_variables": []},
            (plugin,),
        )

        self.assertIsInstance(plugin, WorkflowPreviewPlugin)
        self.assertEqual(plugin.calls, ["synthetic_event"])
        self.assertEqual(result["runtime"]["job"]["kind"], "synthetic")
        self.assertEqual(result["runtime"]["synthetic"]["value"], 42)
        self.assertEqual(original, {"global": {"movement_speed": 100}})

    def test_editor_uses_discovered_plugins_without_pattern_branches(self):
        plugin = SyntheticPreviewPlugin()
        editor = object.__new__(GCodeWorkflowEditor)
        editor.workflow = {"custom_variables": []}
        editor.backend = SimpleNamespace(
            core=SimpleNamespace(WorkflowEngine=None)
        )

        with mock.patch(
            "app.gcode_editor._load_application_plugins",
            return_value=(plugin,),
        ):
            result = editor._event_preview_context(
                {},
                "synthetic_event",
            )

        self.assertEqual(result["runtime"]["synthetic"]["value"], 42)
        source = inspect.getsource(
            GCodeWorkflowEditor._event_preview_context
        ).casefold()
        self.assertNotIn("grid", source)
        self.assertNotIn("spiral", source)


class BuiltinWorkflowPreviewCompatibilityTests(unittest.TestCase):
    def setUp(self):
        self.editor = object.__new__(GCodeWorkflowEditor)
        self.editor.workflow = gcode_workflow.default_workflow()
        self.editor.backend = SimpleNamespace(core=gcode_workflow)
        self.context = {
            "global": {
                "x_cord_of_y_line": 10,
                "tuning_offset_x": 1,
                "y_cord_of_x_line": 20,
                "tuning_offset_y": 2,
                "drop_extra_aspirate": 0.2,
                "max_syringe_vol": 100,
                "priming_vol": 5,
                "max_syringe_mm": 90,
                "min_syringe_mm": 2,
                "container2_x": 12,
                "container2_y": 22,
                "container2_z": 32,
                "container4_x": 14,
                "container4_y": 24,
                "container4_z": 34,
            },
            "grid": {
                "dispense_vol": 2,
                "grid_offset_x": 3,
                "grid_offset_y": 4,
                "row_add_volume": 0.5,
                "rows": 2,
                "cols": 3,
                "leftovers_into": 2,
            },
            "cleaning": {
                "dispense_vol_cleaning": 1,
                "grid_offset_x_cleaning": 5,
                "grid_offset_y_cleaning": 6,
                "rows_cleaning": 2,
                "cols_cleaning": 2,
            },
            "washing": {
                "washing_x_pos": 7,
                "washing_line_lenght": 8,
            },
            "spiral": {
                "center_x": 30,
                "center_y": 40,
                "start_radius": 2,
                "spacing_mm": 1.5,
                "dispense_vol": 0.25,
                "leftovers_into": 4,
            },
            "container": {"id": 3},
        }

    def preview(self, kind, trigger):
        context = dict(self.context)
        context["runtime"] = {"job": {"kind": kind}}
        return self.editor._event_preview_context(context, trigger)

    def test_builtins_expose_the_optional_preview_capability(self):
        self.assertIsInstance(GridPlugin(), WorkflowPreviewPlugin)
        self.assertIsInstance(SpiralPlugin(), WorkflowPreviewPlugin)

    def test_grid_spot_refill_washing_and_rinse_values_are_preserved(self):
        spot = self.preview("grid", "grid_spot_dispense")
        self.assertEqual(
            spot["runtime"]["spot"],
            {
                "index": 0,
                "row": 0,
                "column": 0,
                "x": 14.0,
                "y": 26.0,
                "dispense_mm": 10.0,
                "is_row_start": True,
            },
        )

        washing = self.preview("grid", "washing_cycle")
        self.assertEqual(
            washing["runtime"]["washing"],
            {"cycle": 0, "x_start": 7.0, "x_end": 15.0},
        )

        refill = self.preview("grid", "syringe_reload")
        self.assertEqual(
            refill["runtime"]["refill"],
            {
                "reason": "representative_preview",
                "dynamic": False,
                "container_id": 3,
                "fill_mm": 122.5,
                "priming_mm": 25.0,
                "target_fill_mm": 97.5,
                "target_fill_ul": 19.5,
                "remaining_spots_mm": 62.5,
                "cleaning_mm": 20.0,
                "reserve_mm": 15.0,
                "total_needed_mm": 97.5,
                "cap_mm": 500.0,
            },
        )

        rinse = self.preview("grid", "rinse_midpoint")
        self.assertEqual(
            rinse["runtime"]["rinse"],
            {"cycle": 1, "phase": 2, "max_mm": 90.0, "min_mm": 2.0},
        )
        self.assertEqual(
            rinse["container"],
            {"id": 2, "x": 12.0, "y": 22.0, "z": 32.0},
        )

    def test_spiral_spot_refill_and_rinse_values_are_preserved(self):
        spot = self.preview("grid", "spiral_continuous")
        self.assertEqual(spot["runtime"]["job"]["kind"], "spiral")
        self.assertEqual(spot["runtime"]["spot"]["index"], 1)
        self.assertEqual(spot["runtime"]["spot"]["start_index"], 0)
        self.assertAlmostEqual(
            spot["runtime"]["spot"]["x"],
            32.0126409228661,
        )
        self.assertAlmostEqual(
            spot["runtime"]["spot"]["y"],
            40.16135564616685,
        )
        self.assertAlmostEqual(
            spot["runtime"]["spot"]["segment_length"],
            0.1618500462799663,
        )
        self.assertEqual(spot["runtime"]["spot"]["theta"], 0.08)
        self.assertTrue(spot["runtime"]["spot"]["continuous"])

        refill = self.preview("spiral", "syringe_reload")
        self.assertEqual(
            refill["runtime"]["refill"],
            {
                "reason": "representative_preview",
                "dynamic": False,
                "container_id": 3,
                "fill_mm": 32.25,
                "priming_mm": 25.0,
                "target_fill_mm": 7.25,
                "target_fill_ul": 1.45,
                "remaining_spots_mm": 1.25,
                "cleaning_mm": 0.0,
                "reserve_mm": 6.0,
                "total_needed_mm": 7.25,
                "cap_mm": 500.0,
            },
        )

        rinse = self.preview("spiral", "rinse_midpoint")
        self.assertEqual(
            rinse["container"],
            {"id": 4, "x": 14.0, "y": 24.0, "z": 34.0},
        )


if __name__ == "__main__":
    unittest.main()
