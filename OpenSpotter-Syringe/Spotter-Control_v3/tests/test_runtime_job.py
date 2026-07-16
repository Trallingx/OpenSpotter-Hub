import json
import tempfile
import unittest
from pathlib import Path

from app.runtime_job import (
    JobArtifact,
    capture_generation_snapshot,
    generate_job_artifact,
)
try:
    from tests.test_generation_integration import FakeGrid, FakeGui, FakeSpiral
except ImportError:
    from test_generation_integration import FakeGrid, FakeGui, FakeSpiral


PROJECT_DIR = Path(__file__).resolve().parents[1]


class RuntimeJobTests(unittest.TestCase):
    def test_grid_snapshot_is_detached_from_live_widgets(self):
        gui = FakeGui()
        gui.config_dir = str(PROJECT_DIR / "config")
        gui.grid_tab_dict = {1: FakeGrid()}
        gui._current_workspace_mode = lambda: "grid"

        snapshot = capture_generation_snapshot(gui)
        gui.grid_tab_dict[1].grid_entry[0].value = 99

        self.assertEqual(snapshot.kind, "grid")
        self.assertEqual(snapshot.grids[0].grid["rows"], 1)

    def test_runtime_artifact_contains_hash_profile_and_line_index(self):
        gui = FakeGui()
        gui.config_dir = str(PROJECT_DIR / "config")
        gui.spiral_tab_dict = {1: FakeSpiral()}
        gui._current_workspace_mode = lambda: "spiral"
        snapshot = capture_generation_snapshot(gui)

        with tempfile.TemporaryDirectory() as temp_dir:
            artifact = generate_job_artifact(snapshot, temp_dir)

            self.assertIsInstance(artifact, JobArtifact)
            self.assertTrue(artifact.path.is_file())
            self.assertTrue(artifact.settings_path.is_file())
            self.assertEqual(len(artifact.sha256), 64)
            self.assertEqual(artifact.size, len(artifact.path.read_bytes()))
            self.assertTrue(artifact.remote_path.startswith("openspotter/spiral/"))
            self.assertIn(
                "OPENSPOTTER_SET_PROMPT PROMPT=20",
                artifact.path.read_text(encoding="utf-8"),
            )

            file_position = artifact.line_offsets[-1]
            current, context = artifact.context_for_file_position(file_position)
            self.assertEqual(current, artifact.line_count - 1)
            self.assertEqual(context[-1][0], current)

            profile = json.loads(artifact.settings_path.read_text(encoding="utf-8"))
            self.assertEqual(profile["spiral_settings"][0]["spiral_name"], "Integration Spiral")

    def test_captured_workflow_is_used_even_if_source_file_changes(self):
        gui = FakeGui()
        gui.grid_tab_dict = {1: FakeGrid()}
        gui._current_workspace_mode = lambda: "grid"

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            config_dir = temp_path / "config"
            config_dir.mkdir()
            workflow = json.loads(
                (PROJECT_DIR / "config" / "config_gcode_workflow.json").read_text(
                    encoding="utf-8"
                )
            )
            workflow["blocks"][0]["sections"][0]["template"] += "; SNAPSHOT MARKER\n"
            workflow_path = config_dir / "config_gcode_workflow.json"
            workflow_path.write_text(
                json.dumps(workflow, indent=2) + "\n",
                encoding="utf-8",
            )
            gui.config_dir = str(config_dir)
            snapshot = capture_generation_snapshot(gui)

            workflow["blocks"][0]["sections"][0]["template"] = "; CHANGED AFTER CAPTURE\n"
            workflow_path.write_text(
                json.dumps(workflow, indent=2) + "\n",
                encoding="utf-8",
            )
            artifact = generate_job_artifact(snapshot, temp_path / "output")

            output = artifact.path.read_text(encoding="utf-8")
            self.assertIn("SNAPSHOT MARKER", output)
            self.assertNotIn("CHANGED AFTER CAPTURE", output)

    def test_identical_artifacts_use_the_same_content_addressed_remote_path(self):
        gui = FakeGui()
        gui.config_dir = str(PROJECT_DIR / "config")
        gui.grid_tab_dict = {1: FakeGrid()}
        gui._current_workspace_mode = lambda: "grid"
        snapshot = capture_generation_snapshot(gui)

        with tempfile.TemporaryDirectory() as temp_dir:
            first = generate_job_artifact(snapshot, temp_dir)
            second = generate_job_artifact(snapshot, temp_dir)

        self.assertEqual(first.sha256, second.sha256)
        self.assertEqual(first.remote_path, second.remote_path)
        self.assertTrue(first.remote_path.endswith(f"{first.sha256}.gcode"))

    def test_runtime_capture_rejects_invalid_numeric_input_instead_of_defaulting(self):
        gui = FakeGui()
        gui.config_dir = str(PROJECT_DIR / "config")
        gui.grid_tab_dict = {1: FakeGrid()}
        gui._current_workspace_mode = lambda: "grid"
        gui.entry[0].value = "not-a-coordinate"

        with self.assertRaisesRegex(ValueError, "Base origin X from TCP"):
            capture_generation_snapshot(gui)

    def test_snapshot_mappings_are_immutable(self):
        gui = FakeGui()
        gui.config_dir = str(PROJECT_DIR / "config")
        gui.grid_tab_dict = {1: FakeGrid()}
        gui._current_workspace_mode = lambda: "grid"
        snapshot = capture_generation_snapshot(gui)

        with self.assertRaises(TypeError):
            snapshot.global_values["probe_x"] = 0
        with self.assertRaises(TypeError):
            snapshot.grids[0].grid["rows"] = 2

    def test_recipe_name_cannot_inject_an_extra_gcode_line(self):
        gui = FakeGui()
        gui.config_dir = str(PROJECT_DIR / "config")
        grid = FakeGrid()
        grid.get_grid_name = lambda: "Sample\nM112"
        gui.grid_tab_dict = {1: grid}
        gui._current_workspace_mode = lambda: "grid"

        with self.assertRaisesRegex(ValueError, "newlines or control characters"):
            capture_generation_snapshot(gui)

    def test_direct_run_rejects_accidental_unbounded_grid_size(self):
        gui = FakeGui()
        gui.config_dir = str(PROJECT_DIR / "config")
        grid = FakeGrid()
        grid.grid_entry[0].value = 500
        grid.grid_entry[1].value = 500
        gui.grid_tab_dict = {1: grid}
        gui._current_workspace_mode = lambda: "grid"

        with self.assertRaisesRegex(ValueError, "direct-run limit"):
            capture_generation_snapshot(gui)

    def test_direct_run_counts_repeated_cleaning_work_before_generation(self):
        gui = FakeGui()
        gui.config_dir = str(PROJECT_DIR / "config")
        grid = FakeGrid()
        grid.grid_entry[0].value = 250
        grid.grid_entry[1].value = 100
        grid.cleaning_entry[0].value = 250
        grid.cleaning_entry[1].value = 100
        grid.cleaning_entry[10].value = 1
        grid.cleaning_enabled.value = True
        gui.grid_tab_dict = {1: grid}
        gui._current_workspace_mode = lambda: "grid"

        with self.assertRaisesRegex(
            ValueError,
            "pattern and maintenance operations",
        ):
            capture_generation_snapshot(gui)


if __name__ == "__main__":
    unittest.main()
