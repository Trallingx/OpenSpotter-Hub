import hashlib
import tempfile
import unittest
from pathlib import Path

from app import gcode_planner as legacy_planner
from app.core.gcode import lifecycle
from app.core.plugins import PluginRegistry
from app.grid import Grid as LegacyGrid
from app.grid_gcode import save_grid_gcode as legacy_save_grid_gcode
from app.input_configs import (
    CLEANING_FIELDS as LEGACY_CLEANING_FIELDS,
    GRID_FIELDS as LEGACY_GRID_FIELDS,
    SPIRAL_FIELDS as LEGACY_SPIRAL_FIELDS,
    WASHING_FIELDS as LEGACY_WASHING_FIELDS,
)
from app.plugins.grid.editor import Grid
from app.plugins.grid.fields import (
    CLEANING_FIELDS,
    GRID_FIELDS,
    WASHING_FIELDS,
)
from app.plugins.grid.generation import save_grid_gcode
from app.plugins.grid.planner import (
    calculate_grid_refill_ul,
    clean_grid,
    generate_grid_events,
    wash_needle,
)
from app.plugins.spiral import SpiralPlugin
from app.plugins.spiral.editor import SpiralGrid
from app.plugins.spiral.fields import SPIRAL_FIELDS
from app.plugins.spiral.generation import save_spiral_gcode
from app.plugins.spiral.planner import generate_spiral_events
from app.spiral_gcode import save_spiral_gcode as legacy_save_spiral_gcode
from app.spiral_grid import SpiralGrid as LegacySpiralGrid

try:
    from tests.test_generation_integration import FakeGrid, FakeGui, FakeSpiral
except ImportError:
    from test_generation_integration import FakeGrid, FakeGui, FakeSpiral


GRID_GCODE_SHA256 = (
    "36f45aee4b017262622857b5f302512d7258461a85722984e90645950235f4b0"
)
SPIRAL_GCODE_SHA256 = (
    "9ee7abb70207827216ed2d95329366a282539ebfa11f6962b9df957bcdbaf84a"
)


class BuiltinPluginPackageTests(unittest.TestCase):
    def test_legacy_imports_are_exact_reexports(self):
        self.assertIs(LegacyGrid, Grid)
        self.assertIs(LegacySpiralGrid, SpiralGrid)
        self.assertIs(legacy_save_grid_gcode, save_grid_gcode)
        self.assertIs(legacy_save_spiral_gcode, save_spiral_gcode)

        self.assertIs(legacy_planner.clean_grid, clean_grid)
        self.assertIs(legacy_planner.wash_needle, wash_needle)
        self.assertIs(
            legacy_planner.calculate_grid_refill_ul,
            calculate_grid_refill_ul,
        )
        self.assertIs(
            legacy_planner.generate_grid_events,
            generate_grid_events,
        )
        self.assertIs(
            legacy_planner.generate_spiral_events,
            generate_spiral_events,
        )
        self.assertIs(legacy_planner.emit_event, lifecycle.emit_event)
        self.assertIs(legacy_planner.load_syringe, lifecycle.load_syringe)
        self.assertIs(legacy_planner.empty_syringe, lifecycle.empty_syringe)

        self.assertIs(LEGACY_GRID_FIELDS, GRID_FIELDS)
        self.assertIs(LEGACY_CLEANING_FIELDS, CLEANING_FIELDS)
        self.assertIs(LEGACY_WASHING_FIELDS, WASHING_FIELDS)
        self.assertIs(LEGACY_SPIRAL_FIELDS, SPIRAL_FIELDS)

    def test_registry_discovers_both_builtin_packages(self):
        registry = PluginRegistry()

        loaded = registry.discover_builtins("app.plugins")

        self.assertEqual(loaded, ("grid", "spiral"))
        self.assertEqual(registry.ids(), ("grid", "spiral"))
        self.assertEqual(registry.require("grid").manifest.id, "grid")
        self.assertIsInstance(registry.require("spiral"), SpiralPlugin)

    def test_representative_gcode_hashes_are_unchanged(self):
        gui = FakeGui()
        gui.grid_tab_dict = {1: FakeGrid()}
        gui.spiral_tab_dict = {1: FakeSpiral()}

        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)
            grid_path = output_dir / "grid.gcode"
            spiral_path = output_dir / "spiral.gcode"

            save_grid_gcode(gui, str(grid_path))
            save_spiral_gcode(gui, str(spiral_path))

            self.assertEqual(
                hashlib.sha256(grid_path.read_bytes()).hexdigest(),
                GRID_GCODE_SHA256,
            )
            self.assertEqual(
                hashlib.sha256(spiral_path.read_bytes()).hexdigest(),
                SPIRAL_GCODE_SHA256,
            )


if __name__ == "__main__":
    unittest.main()
