import unittest
from pathlib import Path

from app.core.canvas import CanvasPreviewContext, CanvasPreviewStyle
from app.gcode_workflow import DEFAULT_WORKFLOW_PATH
from app.input_configs import GLOBAL_FIELDS
from app.plugins.grid.plugin import GridPlugin
from app.plugins.grid.preview import build_grid_canvas_preview
from app.plugins.spiral.plugin import SpiralPlugin
from app.plugins.spiral.preview import build_spiral_canvas_preview


def _preview_context():
    return CanvasPreviewContext(
        global_values={
            field.key: field.default
            for field in GLOBAL_FIELDS
        },
        config_dir=Path(DEFAULT_WORKFLOW_PATH).parent,
        workflow_source=DEFAULT_WORKFLOW_PATH,
        style=CanvasPreviewStyle(
            maintenance_primary="gold",
            maintenance_secondary="gray",
            maintenance_primary_outline="black",
            maintenance_secondary_outline="darkgray",
            washing_line="blue",
        ),
    )


class PluginCanvasPreviewTests(unittest.TestCase):
    def test_grid_preview_uses_numeric_plugin_plan(self):
        preview = build_grid_canvas_preview(
            GridPlugin(),
            (
                {
                    "pattern_number": 3,
                    "grid_color": "green",
                    "grid": {
                        "rows": 1,
                        "cols": 2,
                        "pitch_x": 4.0,
                        "pitch_y": 1.0,
                        "grid_offset_x": 2.0,
                        "grid_offset_y": 3.0,
                        "dispense_vol": 0.01,
                        "row_add_volume": 0.0,
                        "loading_from": 1,
                    },
                    "cleaning": {},
                    "washing": {},
                },
            ),
            _preview_context(),
        )

        self.assertEqual(
            [marker.point for marker in preview.markers],
            [(2.0, 3.0), (6.0, 3.0)],
        )
        self.assertEqual(preview.lines, ())
        self.assertEqual(preview.warnings, ())

    def test_spiral_preview_keeps_each_start_as_a_separate_path(self):
        preview = build_spiral_canvas_preview(
            SpiralPlugin(),
            (
                {
                    "pattern_number": 2,
                    "spiral_color": "orange",
                    "spiral": {
                        "center_x": 10.0,
                        "center_y": 20.0,
                        "start_radius": 2.0,
                        "turns": 0.0,
                        "num_starts": 2,
                        "spacing_mm": 1.5,
                        "dispense_vol": 0.01,
                        "spiral_mode": "drop",
                        "interleave": False,
                    },
                },
            ),
            _preview_context(),
        )

        self.assertEqual(len(preview.polylines), 2)
        self.assertTrue(
            all(polyline.show_markers for polyline in preview.polylines)
        )
        self.assertEqual(
            [polyline.points for polyline in preview.polylines],
            [((12.0, 20.0),), ((8.0, 20.0),)],
        )
        self.assertEqual(preview.warnings, ())


if __name__ == "__main__":
    unittest.main()
