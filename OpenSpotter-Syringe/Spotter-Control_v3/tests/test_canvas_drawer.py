import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image

from app.canvas_drawer import (
    CanvasDrawer,
    LIVE_TOOLHEAD_TAG,
    canvas_to_world_point,
    load_scaled_visual_image,
    normalize_live_toolhead_position,
    resolve_canvas_visual_objects,
    visual_image_cache_key,
    visual_object_shape_options,
    world_to_canvas_point,
)


class FakeCanvas:
    def __init__(self):
        self.items = {}
        self.next_id = 1
        self.create_count = 0
        self.raised = []

    def _create(self, kind, coordinates, options):
        item_id = self.next_id
        self.next_id += 1
        self.create_count += 1
        self.items[item_id] = {
            "kind": kind,
            "coords": tuple(coordinates),
            "options": dict(options),
        }
        return item_id

    def create_oval(self, *coordinates, **options):
        return self._create("oval", coordinates, options)

    def create_line(self, *coordinates, **options):
        return self._create("line", coordinates, options)

    def create_text(self, *coordinates, **options):
        return self._create("text", coordinates, options)

    def coords(self, item_id, *coordinates):
        self.items[item_id]["coords"] = tuple(coordinates)

    def itemconfigure(self, item_id, **options):
        self.items[item_id]["options"].update(options)

    def delete(self, item_or_tag):
        if isinstance(item_or_tag, str):
            self.items = {
                item_id: item
                for item_id, item in self.items.items()
                if item_or_tag
                not in tuple(item["options"].get("tags", ()))
            }
        else:
            self.items.pop(item_or_tag, None)

    def tag_raise(self, tag):
        self.raised.append(tag)


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

    def test_live_toolhead_requires_homed_finite_xy(self):
        self.assertEqual(
            normalize_live_toolhead_position((1, 2, 3), "xyz"),
            (1.0, 2.0, 3.0),
        )
        self.assertIsNone(
            normalize_live_toolhead_position((1, 2, 3), "z")
        )
        self.assertIsNone(
            normalize_live_toolhead_position((float("nan"), 2, 3), "xy")
        )

    def test_live_toolhead_overlay_updates_without_full_redraw(self):
        canvas = FakeCanvas()
        drawer = CanvasDrawer.__new__(CanvasDrawer)
        drawer.canvas = canvas
        drawer._fit_scale = 2.0
        drawer._zoom_factor = 1.0
        drawer._origin_x = 0.0
        drawer._origin_y = 0.0
        drawer._pan_x = 10.0
        drawer._pan_y = 20.0
        drawer._canvas_width = 400
        drawer._canvas_height = 300
        drawer._transform_ready = True
        drawer._toolhead_position = None
        drawer._toolhead_homed_axes = ""
        drawer._toolhead_item_ids = ()

        self.assertTrue(
            drawer.set_toolhead_position((5.0, 7.0, 9.0), "xyz")
        )
        self.assertEqual(len(canvas.items), 5)
        first_ids = drawer._toolhead_item_ids
        ring = canvas.items[first_ids[0]]
        self.assertEqual(ring["coords"], (10.0, 24.0, 30.0, 44.0))
        self.assertEqual(canvas.raised[-1], LIVE_TOOLHEAD_TAG)

        self.assertTrue(
            drawer.set_toolhead_position((6.0, 8.0, 10.0), "xyz")
        )
        self.assertEqual(drawer._toolhead_item_ids, first_ids)
        self.assertEqual(canvas.create_count, 5)
        moved_ring = canvas.items[first_ids[0]]
        self.assertEqual(moved_ring["coords"], (12.0, 26.0, 32.0, 46.0))

        self.assertTrue(drawer.set_toolhead_position(None, ""))
        self.assertEqual(canvas.items, {})

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
