import json
import tempfile
import unittest
from pathlib import Path

from app.grid_gcode import save_grid_gcode
from app.input_configs import (
    CLEANING_FIELDS,
    GLOBAL_FIELDS,
    GRID_FIELDS,
    SPIRAL_FIELDS,
    WASHING_FIELDS,
)
from app.spiral_gcode import save_spiral_gcode


PROJECT_DIR = Path(__file__).resolve().parents[1]


class FakeEntry:
    def __init__(self, value):
        self.value = value

    def get(self):
        return str(self.value)


class FakeVariable:
    def __init__(self, value):
        self.value = value

    def get(self):
        return self.value


def entries_for(fields, values):
    return [FakeEntry(values.get(field.key, field.default)) for field in fields]


class FakeGrid:
    def __init__(self):
        grid = {
            "rows": 1,
            "cols": 2,
            "pitch_x": 1.5,
            "pitch_y": 1.5,
            "dispense_vol": 0.003,
            "row_add_volume": 0.0,
            "loading_from": 1,
            "leftovers_into": 6,
            "z_contact": 0.01,
            "droplet_forming_time": 0.001,
            "grid_offset_x": 20.0,
            "grid_offset_y": 20.0,
        }
        cleaning = {
            "rows_cleaning": 1,
            "cols_cleaning": 1,
            "pitch_x_cleaning": 1.0,
            "pitch_y_cleaning": 1.0,
            "dispense_vol_cleaning": 0.003,
            "droplet_forming_time_cleaning": 0.1,
            "grid_offset_x_cleaning": 100.0,
            "grid_offset_y_cleaning": 20.0,
            "x_relative_increase": 0.0,
            "y_relative_increase": 0.0,
            "spots_before_cleaning": 0,
            "final_rinse_cycles": 1,
        }
        washing = {
            "washing_depth": -5.0,
            "washing_speed": 2000.0,
            "washing_x_pos": 218.0,
            "washing_y_pos": 16.0,
            "washing_line_lenght": 1.0,
            "washing_after_x_spots": 0,
            "washing_cycles": 1,
        }
        self.grid_entry = entries_for(GRID_FIELDS, grid)
        self.cleaning_entry = entries_for(CLEANING_FIELDS, cleaning)
        self.washing_entry = entries_for(WASHING_FIELDS, washing)
        self.cleaning_enabled = FakeVariable(False)
        self.washing_enabled = FakeVariable(False)
        self.wash_after_loading_enabled = FakeVariable(False)
        self.final_rinse_enabled = FakeVariable(False)
        self.final_rinse_add_cleaning_grid = FakeVariable(False)

    @staticmethod
    def get_grid_name():
        return "Integration Grid"

    @staticmethod
    def get_grid_color():
        return "green"


class FakeSpiral:
    def __init__(self):
        values = {
            "center_x": 100.0,
            "center_y": 100.0,
            "start_radius": 0.0,
            "turns": 0.0,
            "num_starts": 1,
            "spacing_mm": 1.5,
            "dispense_vol": 0.003,
            "spiral_mode": "drop",
            "interleave": False,
            "loading_from": 1,
            "leftovers_into": 1,
            "z_contact": 0.01,
            "droplet_forming_time": 0.1,
        }
        self.spiral_entry = entries_for(SPIRAL_FIELDS, values)

    @staticmethod
    def get_grid_name():
        return "Integration Spiral"

    @staticmethod
    def get_grid_color():
        return "orange"


class FakeGui:
    def __init__(self):
        global_values = json.loads(
            (PROJECT_DIR / "config" / "config_global.json").read_text(encoding="utf-8")
        )
        self.entry = entries_for(GLOBAL_FIELDS, global_values)
        self.grid_tab_dict = {}
        self.spiral_tab_dict = {}


class GenerationIntegrationTests(unittest.TestCase):
    def test_grid_and_spiral_generation_render_the_active_workflow(self):
        gui = FakeGui()
        gui.grid_tab_dict = {1: FakeGrid()}
        gui.spiral_tab_dict = {1: FakeSpiral()}

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            grid_path = temp_path / "grid_job.gcode"
            spiral_path = temp_path / "spiral_job.gcode"

            self.assertEqual(save_grid_gcode(gui, str(grid_path)), str(grid_path))
            self.assertEqual(save_spiral_gcode(gui, str(spiral_path)), str(spiral_path))

            grid_output = grid_path.read_text(encoding="utf-8")
            spiral_output = spiral_path.read_text(encoding="utf-8")
            self.assertNotIn("{{", grid_output + spiral_output)
            self.assertIn("NEEDLE_TIP_OFFSETS_ENABLE", grid_output)
            self.assertIn("NEEDLE_TIP_OFFSETS_DISABLE", grid_output)
            for output in (grid_output, spiral_output):
                command_names = [
                    line.split(";", 1)[0].strip().upper().split(" ", 1)[0]
                    for line in output.splitlines()
                    if line.split(";", 1)[0].strip()
                ]
                self.assertEqual(command_names.count("HOMING"), 1)
                self.assertNotIn("G28", command_names)
                self.assertNotIn("SET_TMC_FIELD", command_names)
                self.assertNotIn("OPENSPOTTER_HOME", command_names)
                self.assertNotIn("OPENSPOTTER_JOB_HOME", command_names)
                self.assertNotIn("OPENSPOTTER_JOB_REHOME_Z", command_names)

            grid_profile = json.loads(
                (temp_path / "grid_job_settings.json").read_text(encoding="utf-8")
            )
            spiral_profile = json.loads(
                (temp_path / "spiral_job_settings.json").read_text(encoding="utf-8")
            )
            self.assertEqual(grid_profile["schema_version"], 3)
            self.assertEqual(
                grid_profile["patterns"][0]["plugin_id"],
                "grid",
            )
            self.assertEqual(grid_profile["grid_settings"][0]["grid_name"], "Integration Grid")
            self.assertEqual(
                spiral_profile["spiral_settings"][0]["spiral_name"],
                "Integration Spiral",
            )
            self.assertEqual(
                [block["role"] for block in grid_profile["workflow"]["blocks"]],
                ["start", "loading", "printing", "cleaning", "end"],
            )

    def test_generation_uses_the_gui_config_directory_workflow(self):
        gui = FakeGui()
        gui.grid_tab_dict = {1: FakeGrid()}

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            config_dir = temp_path / "config"
            config_dir.mkdir()
            workflow = json.loads(
                (PROJECT_DIR / "config" / "config_gcode_workflow.json").read_text(
                    encoding="utf-8"
                )
            )
            workflow["blocks"][0]["sections"][0]["template"] += (
                "; ACTIVE CONFIG DIRECTORY MARKER\n"
            )
            (config_dir / "config_gcode_workflow.json").write_text(
                json.dumps(workflow, indent=2) + "\n",
                encoding="utf-8",
            )
            gui.config_dir = str(config_dir)
            output_path = temp_path / "configured.gcode"

            save_grid_gcode(gui, str(output_path))

            self.assertIn(
                "ACTIVE CONFIG DIRECTORY MARKER",
                output_path.read_text(encoding="utf-8"),
            )


if __name__ == "__main__":
    unittest.main()
