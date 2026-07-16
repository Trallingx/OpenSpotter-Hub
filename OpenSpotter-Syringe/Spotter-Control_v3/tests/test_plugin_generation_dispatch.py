import unittest
from unittest import mock

from app import gcode_generation


class FakePlugin:
    def __init__(self, plugin_id, count):
        self.manifest = mock.Mock(id=plugin_id)
        self._instances = {index: object() for index in range(count)}
        self.generated = []

    def instance_map(self, _gui):
        return self._instances

    def generate(self, gui, filepath=None):
        self.generated.append((gui, filepath))
        return filepath


class PluginGenerationDispatchTests(unittest.TestCase):
    def test_save_file_dispatches_each_nonempty_registered_plugin(self):
        gui = object()
        grid = FakePlugin("grid", 1)
        empty = FakePlugin("empty", 0)
        spiral = FakePlugin("spiral", 2)

        with mock.patch.object(
            gcode_generation,
            "prompt_save_base_path",
            return_value="experiment.gcode",
        ), mock.patch.object(
            gcode_generation,
            "application_plugins",
            return_value=(grid, empty, spiral),
        ):
            result = gcode_generation.save_file(gui)

        self.assertEqual(
            result,
            [
                "experiment_grid.gcode",
                "experiment_spiral.gcode",
            ],
        )
        self.assertEqual(empty.generated, [])

    def test_save_file_returns_none_when_every_plugin_is_empty(self):
        with mock.patch.object(
            gcode_generation,
            "prompt_save_base_path",
            return_value="experiment.gcode",
        ), mock.patch.object(
            gcode_generation,
            "application_plugins",
            return_value=(FakePlugin("grid", 0),),
        ):
            self.assertIsNone(gcode_generation.save_file(object()))


if __name__ == "__main__":
    unittest.main()
