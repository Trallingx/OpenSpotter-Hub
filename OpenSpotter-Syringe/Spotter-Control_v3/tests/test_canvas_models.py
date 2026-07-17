import unittest
from pathlib import Path

from app.core.canvas import (
    CanvasPreview,
    CanvasPreviewContext,
    CanvasPreviewProvider,
    CanvasPreviewStyle,
    LinePrimitive,
    MarkerPrimitive,
    PolylinePrimitive,
    PreviewBounds,
)


class CanvasPreviewModelTests(unittest.TestCase):
    def test_preview_metadata_is_detached_and_read_only(self):
        source = {"plugin": "example"}
        preview = CanvasPreview(metadata=source)

        source["plugin"] = "changed"
        self.assertEqual(preview.metadata["plugin"], "example")
        with self.assertRaises(TypeError):
            preview.metadata["plugin"] = "changed"

    def test_preview_provider_is_an_optional_structural_capability(self):
        class Provider:
            def build_canvas_preview(self, gui, context):
                return CanvasPreview.empty()

        context = CanvasPreviewContext(
            global_values={"base_square_x": 100.0},
            config_dir=Path("config"),
            workflow_source=Path("config/workflow.json"),
            style=CanvasPreviewStyle(
                maintenance_primary="gold",
                maintenance_secondary="gray",
                maintenance_primary_outline="black",
                maintenance_secondary_outline="darkgray",
                washing_line="blue",
            ),
        )

        self.assertIsInstance(Provider(), CanvasPreviewProvider)
        self.assertEqual(
            Provider().build_canvas_preview(object(), context),
            CanvasPreview.empty(),
        )
        with self.assertRaises(TypeError):
            context.global_values["base_square_x"] = 200.0

    def test_combined_preview_exposes_all_fit_and_safety_points(self):
        first = CanvasPreview(
            markers=(MarkerPrimitive(1.0, 2.0, "green"),),
            polylines=(
                PolylinePrimitive(((3.0, 4.0), (5.0, 6.0)), "orange"),
            ),
        )
        second = CanvasPreview(
            lines=(LinePrimitive((7.0, 8.0), (9.0, 10.0), "blue"),),
            safety_points=((11.0, 12.0),),
            warnings=("preview warning",),
        )

        combined = CanvasPreview.combine((first, second))

        self.assertEqual(
            combined.all_points(),
            (
                (11.0, 12.0),
                (1.0, 2.0),
                (3.0, 4.0),
                (5.0, 6.0),
                (7.0, 8.0),
                (9.0, 10.0),
            ),
        )
        self.assertEqual(combined.warnings, ("preview warning",))

    def test_acceptance_boundary_check_includes_hidden_safety_points(self):
        preview = CanvasPreview(safety_points=((5.0, 5.0), (12.0, 5.0)))
        bounds = PreviewBounds(0.0, 0.0, 10.0, 10.0)

        self.assertTrue(preview.extends_outside(bounds))

    def test_non_pattern_maintenance_can_fit_without_failing_acceptance(self):
        preview = CanvasPreview(
            lines=(
                LinePrimitive(
                    (20.0, 20.0),
                    (30.0, 20.0),
                    "blue",
                    safety_relevant=False,
                ),
            ),
        )
        bounds = PreviewBounds(0.0, 0.0, 10.0, 10.0)

        self.assertEqual(
            preview.all_points(),
            ((20.0, 20.0), (30.0, 20.0)),
        )
        self.assertFalse(preview.extends_outside(bounds))


if __name__ == "__main__":
    unittest.main()
