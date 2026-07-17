import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from app.gui_v3 import DropletGui
from app.plugin_runtime import application_plugins


def profile_owner():
    plugins = application_plugins(include_external=False)
    plugin_map = {plugin.manifest.id: plugin for plugin in plugins}
    owner = SimpleNamespace(
        pattern_plugins=plugins,
        pattern_plugins_by_id=plugin_map,
    )
    owner._plugin_for = lambda plugin_id: plugin_map[plugin_id]
    return owner


class PluginProfileTests(unittest.TestCase):
    def _parse(self, payload):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "profile.json"
            path.write_text(
                json.dumps(payload),
                encoding="utf-8",
            )
            return DropletGui._parse_generation_json_file(
                profile_owner(),
                path,
            )

    def test_schema_v3_patterns_are_normalized_by_the_owning_plugin(self):
        parsed = self._parse(
            {
                "schema_version": 3,
                "global_settings": {},
                "patterns": [
                    {
                        "plugin_id": "spiral",
                        "plugin_version": "1.0.0",
                        "recipes": [
                            {
                                "spiral_name": "Example",
                                "spiral_color": "orange",
                                "spiral": {"turns": 2},
                            }
                        ],
                    }
                ],
            }
        )

        recipes = parsed["_pattern_entries"]["spiral"]
        self.assertEqual(recipes[0]["spiral_name"], "Example")
        self.assertEqual(recipes[0]["spiral"], {"turns": 2})

    def test_schema_v2_legacy_arrays_remain_loadable(self):
        parsed = self._parse(
            {
                "schema_version": 2,
                "global_settings": {},
                "grid_settings": [],
                "spiral_settings": [
                    {
                        "spiral_name": "Legacy",
                        "spiral": {},
                    }
                ],
            }
        )

        self.assertEqual(
            parsed["_pattern_entries"]["spiral"][0]["spiral_name"],
            "Legacy",
        )
        self.assertEqual(parsed["_pattern_entries"]["grid"], [])

    def test_unavailable_plugin_has_an_actionable_error(self):
        with self.assertRaisesRegex(
            ValueError,
            "unavailable pattern plugin 'missing'",
        ):
            self._parse(
                {
                    "schema_version": 3,
                    "global_settings": {},
                    "patterns": [
                        {
                            "plugin_id": "missing",
                            "recipes": [],
                        }
                    ],
                }
            )


if __name__ == "__main__":
    unittest.main()
