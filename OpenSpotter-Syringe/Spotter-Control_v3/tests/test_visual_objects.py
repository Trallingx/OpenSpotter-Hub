import json
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path

from app.visual_objects import (
    CAPTRON_VISUAL_OBJECT_ID,
    DEFAULT_VISUAL_OBJECT_IDS,
    VISUAL_BINDABLE_PROPERTIES,
    VISUAL_OBJECT_TYPES,
    VisualObjectStore,
    VisualObjectValidationError,
    default_visual_objects,
    move_visual_object_layer,
    normalize_visual_object,
    normalize_visual_object_config,
    resolve_visual_image_path,
    resolve_visual_object_bindings,
    serialize_visual_image_path,
    visual_object_bounds,
    visual_object_center,
    visual_objects_top_first,
)


class VisualObjectTests(unittest.TestCase):
    def test_rectangle_coordinates_use_top_left_corner(self):
        item = normalize_visual_object(
            {
                "id": "plate",
                "type": "rectangle",
                "x": "-4.5",
                "y": "8",
                "width": "20",
                "height": "10",
                "color": "#abcdef",
                "text": "Plate",
                "text_size": "12",
            },
            fallback_id="fallback",
        )

        self.assertEqual(visual_object_bounds(item), (-4.5, 8.0, 15.5, 18.0))
        self.assertEqual(visual_object_center(item), (5.5, 13.0))

    def test_circle_coordinates_use_center_point(self):
        item = normalize_visual_object(
            {
                "type": "circle",
                "x": 10,
                "y": -5,
                "width": 8,
                "height": 4,
                "text_size": 9,
            },
            fallback_id="vial",
        )

        self.assertEqual(visual_object_bounds(item), (6.0, -7.0, 14.0, -3.0))
        self.assertEqual(visual_object_center(item), (10.0, -5.0))

    def test_image_coordinates_use_top_left_and_preserve_path(self):
        item = normalize_visual_object(
            {
                "type": "image",
                "x": -30,
                "y": -20,
                "width": 60,
                "height": 40,
                "image_path": "assets/example.png",
            },
            fallback_id="image",
        )

        self.assertIn("image", VISUAL_OBJECT_TYPES)
        self.assertEqual(item["image_path"], "assets/example.png")
        self.assertEqual(visual_object_bounds(item), (-30.0, -20.0, 30.0, 20.0))
        self.assertEqual(visual_object_center(item), (0.0, 0.0))

    def test_invalid_geometry_and_duplicate_ids_are_rejected(self):
        with self.assertRaises(VisualObjectValidationError):
            normalize_visual_object(
                {"type": "triangle", "width": 1, "height": 1},
                fallback_id="bad",
            )
        with self.assertRaises(VisualObjectValidationError):
            normalize_visual_object(
                {"type": "rectangle", "width": 0, "height": 1},
                fallback_id="bad",
            )
        with self.assertRaises(VisualObjectValidationError):
            normalize_visual_object(
                {"type": "image", "width": 1, "height": 1},
                fallback_id="bad",
            )
        with self.assertRaises(VisualObjectValidationError):
            normalize_visual_object_config(
                {
                    "objects": [
                        {"id": "same", "width": 1, "height": 1},
                        {"id": "same", "width": 2, "height": 2},
                    ]
                }
            )

    def test_bindings_are_validated_and_normalized(self):
        item = normalize_visual_object(
            {
                "type": "circle",
                "width": 12,
                "height": 12,
                "bindings": {
                    "x": " global.container1_x ",
                    "y": "global.container1_y",
                    "width": "custom.container_diameter",
                    "height": "grid.1.pitch_y",
                },
            },
            fallback_id="container",
        )

        self.assertEqual(
            item["bindings"],
            {
                "x": "global.container1_x",
                "y": "global.container1_y",
                "width": "custom.container_diameter",
                "height": "grid.1.pitch_y",
            },
        )
        self.assertEqual(
            VISUAL_BINDABLE_PROPERTIES,
            ("x", "y", "width", "height"),
        )

        invalid_bindings = (
            [],
            None,
            {"text": "global.container1_x"},
            {"x": ""},
            {"x": "container1_x"},
            {"x": "global.container 1.x"},
            {"x": 123},
        )
        for bindings in invalid_bindings:
            with self.subTest(bindings=bindings):
                with self.assertRaises(VisualObjectValidationError):
                    normalize_visual_object(
                        {
                            "type": "circle",
                            "width": 12,
                            "height": 12,
                            "bindings": bindings,
                        },
                        fallback_id="container",
                    )

    def test_v1_container_objects_migrate_but_v2_unlinked_objects_do_not(self):
        migrated = normalize_visual_object_config(
            {
                "version": 1,
                "objects": [
                    {
                        "id": "legacy-container-1",
                        "type": "circle",
                        "width": 12,
                        "height": 12,
                    },
                    {
                        "id": "legacy-container-2",
                        "type": "circle",
                        "width": 12,
                        "height": 12,
                        "bindings": {},
                    },
                    {
                        "id": "other-object",
                        "type": "rectangle",
                        "width": 12,
                        "height": 12,
                    },
                ],
            }
        )

        self.assertEqual(migrated["version"], 2)
        self.assertEqual(
            migrated["objects"][0]["bindings"],
            {
                "x": "global.container1_x",
                "y": "global.container1_y",
            },
        )
        self.assertEqual(migrated["objects"][1]["bindings"], {})
        self.assertEqual(migrated["objects"][2]["bindings"], {})

        current = normalize_visual_object_config(
            {
                "version": 2,
                "objects": [
                    {
                        "id": "legacy-container-1",
                        "type": "circle",
                        "width": 12,
                        "height": 12,
                    },
                    {
                        "id": "legacy-container-2",
                        "type": "circle",
                        "width": 12,
                        "height": 12,
                        "bindings": {},
                    },
                ],
            }
        )
        self.assertEqual(current["objects"][0]["bindings"], {})
        self.assertEqual(current["objects"][1]["bindings"], {})

    def test_store_load_migrates_v1_document_to_canonical_v2(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            path = Path(temporary_directory) / "visual.json"
            path.write_text(
                json.dumps(
                    {
                        "version": 1,
                        "objects": [
                            {
                                "id": "legacy-container-6",
                                "type": "circle",
                                "x": 218,
                                "y": 15,
                                "width": 12,
                                "height": 12,
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )

            loaded = VisualObjectStore(path).load()

        self.assertEqual(loaded["version"], 2)
        self.assertEqual(
            loaded["objects"][0]["bindings"],
            {
                "x": "global.container6_x",
                "y": "global.container6_y",
            },
        )

        bare_list = normalize_visual_object_config(
            [
                {
                    "id": "legacy-container-5",
                    "type": "circle",
                    "width": 12,
                    "height": 12,
                }
            ]
        )
        self.assertEqual(
            bare_list["objects"][0]["bindings"],
            {
                "x": "global.container5_x",
                "y": "global.container5_y",
            },
        )

    def test_binding_resolver_overlays_catalog_values_without_mutation(self):
        item = normalize_visual_object(
            {
                "id": "container",
                "type": "circle",
                "x": 1,
                "y": 2,
                "width": 3,
                "height": 4,
                "bindings": {
                    "x": "global.container1_x",
                    "y": "global.container1_y",
                    "width": "custom.container_width",
                    "height": "custom.container_height",
                },
            },
            fallback_id="container",
        )
        catalog = {
            "global.container1_x": "16.5",
            "global.container1_y": {"value": -8},
            "custom.container_width": 12,
            "custom.container_height": {"value": "13.25", "unit": "mm"},
        }
        original_item = deepcopy(item)
        original_catalog = deepcopy(catalog)

        resolved, warnings = resolve_visual_object_bindings(item, catalog)

        self.assertEqual(warnings, [])
        self.assertEqual(
            (resolved["x"], resolved["y"], resolved["width"], resolved["height"]),
            (16.5, -8.0, 12.0, 13.25),
        )
        self.assertEqual(item, original_item)
        self.assertEqual(catalog, original_catalog)
        self.assertIsNot(resolved, item)
        self.assertIsNot(resolved["bindings"], item["bindings"])

    def test_binding_resolver_retains_fallbacks_and_reports_bad_sources(self):
        item = normalize_visual_object(
            {
                "id": "container",
                "type": "circle",
                "x": 1,
                "y": 2,
                "width": 3,
                "height": 4,
                "bindings": {
                    "x": "global.missing",
                    "y": "global.invalid",
                    "width": "global.zero_width",
                    "height": "global.infinite_height",
                },
            },
            fallback_id="container",
        )

        resolved, warnings = resolve_visual_object_bindings(
            item,
            {
                "global.invalid": {"value": True},
                "global.zero_width": 0,
                "global.infinite_height": float("inf"),
            },
        )

        self.assertEqual(
            (resolved["x"], resolved["y"], resolved["width"], resolved["height"]),
            (1.0, 2.0, 3.0, 4.0),
        )
        self.assertEqual(len(warnings), 4)
        self.assertTrue(any("missing variable 'global.missing'" in item for item in warnings))
        self.assertTrue(any("invalid numeric value True" in item for item in warnings))
        self.assertTrue(any("non-positive value 0.0" in item for item in warnings))
        self.assertTrue(any("invalid numeric value inf" in item for item in warnings))

    def test_binding_resolver_honors_provider_validity_metadata(self):
        item = normalize_visual_object(
            {
                "id": "indexed-value",
                "type": "circle",
                "x": 7,
                "y": 2,
                "width": 3,
                "height": 4,
                "bindings": {"x": "grid.1.rows"},
            },
            fallback_id="indexed-value",
        )

        resolved, warnings = resolve_visual_object_bindings(
            item,
            {
                "grid.1.rows": {
                    "value": "3.5",
                    "type": "int",
                    "valid": False,
                }
            },
        )

        self.assertEqual(resolved["x"], 7.0)
        self.assertEqual(len(warnings), 1)
        self.assertIn("invalid numeric value '3.5'", warnings[0])

    def test_store_round_trip_uses_canonical_schema(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            path = Path(temporary_directory) / "visual.json"
            store = VisualObjectStore(path)
            saved = store.save(
                [
                    {
                        "id": "sample",
                        "type": "rectangle",
                        "x": 1,
                        "y": 2,
                        "width": 3,
                        "height": 4,
                        "color": "navy",
                        "text": "Sample",
                        "text_size": 11,
                    },
                    {
                        "id": "sample-image",
                        "type": "image",
                        "x": -1,
                        "y": -2,
                        "width": 5,
                        "height": 6,
                        "color": "#ffffff",
                        "text": "Image",
                        "text_size": 9,
                        "image_path": "assets/sample.png",
                    },
                ]
            )

            self.assertEqual(store.load(), saved)
            self.assertEqual(json.loads(path.read_text(encoding="utf-8")), saved)

    def test_layer_helpers_present_top_first_and_move_adjacent_objects(self):
        objects = [
            {
                "id": "back",
                "bindings": {"x": "global.container1_x"},
            },
            {
                "id": "middle",
                "image_path": "assets/example.png",
            },
            {
                "id": "front",
                "x": 99,
            },
        ]

        self.assertEqual(
            [item["id"] for item in visual_objects_top_first(objects)],
            ["front", "middle", "back"],
        )

        moved, selected_index, changed = move_visual_object_layer(
            objects,
            1,
            "up",
        )
        self.assertTrue(changed)
        self.assertEqual(selected_index, 2)
        self.assertEqual(
            [item["id"] for item in moved],
            ["back", "front", "middle"],
        )
        self.assertEqual(moved[2]["image_path"], "assets/example.png")
        self.assertEqual(
            moved[0]["bindings"],
            {"x": "global.container1_x"},
        )
        self.assertEqual(
            [item["id"] for item in objects],
            ["back", "middle", "front"],
        )

        restored, selected_index, changed = move_visual_object_layer(
            moved,
            selected_index,
            "down",
        )
        self.assertTrue(changed)
        self.assertEqual(selected_index, 1)
        self.assertEqual(
            [item["id"] for item in restored],
            ["back", "middle", "front"],
        )

        unchanged, selected_index, changed = move_visual_object_layer(
            objects,
            2,
            "up",
        )
        self.assertFalse(changed)
        self.assertEqual(selected_index, 2)
        self.assertEqual(unchanged, objects)

        with self.assertRaises(VisualObjectValidationError):
            move_visual_object_layer(objects, 1, "sideways")

    def test_image_paths_are_relative_inside_project_and_absolute_outside(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            project = Path(temporary_directory) / "project"
            asset = project / "assets" / "sample.png"
            external = Path(temporary_directory) / "external.png"

            self.assertEqual(
                serialize_visual_image_path(
                    asset,
                    project_directory=project,
                ),
                "assets/sample.png",
            )
            self.assertEqual(
                resolve_visual_image_path(
                    "assets/sample.png",
                    project_directory=project,
                ),
                asset.resolve(),
            )
            self.assertEqual(
                serialize_visual_image_path(
                    external,
                    project_directory=project,
                ),
                str(external.resolve()),
            )

    def test_missing_store_starts_with_editable_legacy_layout(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            path = Path(temporary_directory) / "visual.json"
            store = VisualObjectStore(path)
            loaded = store.load()

            self.assertEqual(
                tuple(item["id"] for item in loaded["objects"]),
                DEFAULT_VISUAL_OBJECT_IDS,
            )

            store.save([])
            self.assertEqual(store.load()["objects"], [])

    def test_default_layout_contains_all_former_hardcoded_objects(self):
        defaults = {item["id"]: item for item in default_visual_objects()}

        self.assertEqual(tuple(defaults), DEFAULT_VISUAL_OBJECT_IDS)
        self.assertEqual(
            visual_object_bounds(defaults["legacy-build-plate"]),
            (22.0, 19.0, 198.0, 195.0),
        )
        self.assertEqual(
            visual_object_bounds(defaults["legacy-acceptance-limit"]),
            (27.5, 24.5, 192.5, 189.5),
        )
        self.assertEqual(
            visual_object_bounds(defaults["legacy-container-6"]),
            (212.0, 9.0, 224.0, 21.0),
        )
        for index in range(1, 7):
            self.assertEqual(
                defaults[f"legacy-container-{index}"]["bindings"],
                {
                    "x": f"global.container{index}_x",
                    "y": f"global.container{index}_y",
                },
            )
        self.assertEqual(
            visual_object_bounds(defaults[CAPTRON_VISUAL_OBJECT_ID]),
            (-30.0, -30.0, 30.0, 30.0),
        )
        self.assertEqual(defaults[CAPTRON_VISUAL_OBJECT_ID]["type"], "image")
        self.assertEqual(
            defaults[CAPTRON_VISUAL_OBJECT_ID]["image_path"],
            "assets/Captron-TCP.png",
        )
        project_directory = Path(__file__).resolve().parents[1]
        self.assertTrue(
            resolve_visual_image_path(
                defaults[CAPTRON_VISUAL_OBJECT_ID]["image_path"],
                project_directory=project_directory,
            ).is_file()
        )


if __name__ == "__main__":
    unittest.main()
