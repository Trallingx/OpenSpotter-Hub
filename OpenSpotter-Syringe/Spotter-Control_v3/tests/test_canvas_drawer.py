import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image

from app.canvas_drawer import (
    CanvasDrawer,
    canvas_to_world_point,
    load_scaled_visual_image,
    resolve_canvas_visual_objects,
    visual_image_cache_key,
    visual_object_shape_options,
    world_to_canvas_point,
)


class CanvasDrawerTests(unittest.TestCase):
    def test_visual_binding_provider_is_snapshotted_once_for_all_objects(self):
        class FakeGui:
            entry = []
            grid_tab_dict = {}
            spiral_tab_dict = {}
            visual_objects = [
                {"id": "first", "x": 1.0},
                {"id": "second", "x": 2.0},
            ]

            def __init__(self):
                self.provider_calls = 0

            def _visual_binding_variable_provider(self):
                self.provider_calls += 1
                return {"global.shared_x": {"value": 42.0}}

        gui = FakeGui()
        drawer = CanvasDrawer.__new__(CanvasDrawer)
        drawer.gui = gui

        def resolve(item, catalog):
            resolved = dict(item)
            resolved["x"] = catalog["global.shared_x"]["value"]
            return resolved, []

        with patch(
            "app.canvas_drawer.resolve_visual_object_bindings",
            side_effect=resolve,
        ):
            snapshot = drawer._collect_data()

        self.assertEqual(gui.provider_calls, 1)
        self.assertEqual(
            [item["x"] for item in snapshot["visual_objects"]],
            [42.0, 42.0],
        )
        self.assertEqual(snapshot["visual_binding_warnings"], ())

    def test_visual_binding_resolution_failure_keeps_literal_object(self):
        literal = {"id": "container", "x": 16.0, "y": 208.0}

        with patch(
            "app.canvas_drawer.resolve_visual_object_bindings",
            side_effect=ValueError("broken binding"),
        ):
            resolved, warnings = resolve_canvas_visual_objects(
                [literal],
                {"global.container1_x": {"value": 30.0}},
            )

        self.assertEqual(resolved, [literal])
        self.assertIsNot(resolved[0], literal)
        self.assertEqual(warnings, ["container: broken binding"])

    def test_canvas_coordinates_increase_downward_and_round_trip(self):
        transform = {
            "origin_x": -5.0,
            "origin_y": -10.0,
            "scale": 4.0,
            "pan_x": 30.0,
            "pan_y": 40.0,
        }

        upper = world_to_canvas_point(2.0, 3.0, **transform)
        lower = world_to_canvas_point(2.0, 8.0, **transform)

        self.assertEqual(upper, (58.0, 92.0))
        self.assertEqual(lower, (58.0, 112.0))
        self.assertGreater(lower[1], upper[1])
        self.assertEqual(
            canvas_to_world_point(*lower, **transform),
            (2.0, 8.0),
        )

    def test_editable_rectangles_and_circles_use_solid_fills(self):
        for object_type in ("rectangle", "circle"):
            with self.subTest(object_type=object_type):
                options = visual_object_shape_options(object_type, "#123456")

                self.assertEqual(options["fill"], "#123456")
                self.assertNotIn("stipple", options)
                self.assertNotIn("outlinestipple", options)

    def test_visual_images_scale_to_exact_requested_canvas_size(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            project = Path(temporary_directory)
            asset_directory = project / "assets"
            asset_directory.mkdir()
            source_path = asset_directory / "sample.png"
            Image.new("RGB", (80, 40), "#123456").save(source_path)

            rendered = load_scaled_visual_image(
                "assets/sample.png",
                31.6,
                18.2,
                project_directory=project,
            )

            self.assertEqual(rendered.size, (32, 18))
            self.assertEqual(rendered.mode, "RGBA")

            first_key = visual_image_cache_key(
                "assets/sample.png",
                31.6,
                18.2,
                project_directory=project,
            )
            same_key = visual_image_cache_key(
                "assets/sample.png",
                31.6,
                18.2,
                project_directory=project,
            )
            resized_key = visual_image_cache_key(
                "assets/sample.png",
                40,
                18.2,
                project_directory=project,
            )
            source_stat = source_path.stat()
            os.utime(
                source_path,
                ns=(
                    source_stat.st_atime_ns,
                    source_stat.st_mtime_ns + 1_000_000_000,
                ),
            )
            changed_file_key = visual_image_cache_key(
                "assets/sample.png",
                31.6,
                18.2,
                project_directory=project,
            )

            self.assertEqual(first_key, same_key)
            self.assertNotEqual(first_key, resized_key)
            self.assertNotEqual(first_key, changed_file_key)


if __name__ == "__main__":
    unittest.main()
