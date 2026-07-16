import json
import tempfile
import unittest
from pathlib import Path

from app.paths import (
    PACKAGED_CONFIG_FILES,
    prepare_runtime_layout,
    resolve_resource_dir,
    resolve_runtime_layout,
)


class RuntimePathTests(unittest.TestCase):
    def _resource_tree(self, root):
        resource_dir = Path(root) / "application"
        config_dir = resource_dir / "config"
        assets_dir = resource_dir / "assets"
        config_dir.mkdir(parents=True)
        assets_dir.mkdir()
        (config_dir / "config_global.json").write_text(
            json.dumps({"source": "packaged"}),
            encoding="utf-8",
        )
        (config_dir / "config_gcode_workflow.json").write_text(
            json.dumps({"schema_version": 1, "blocks": []}),
            encoding="utf-8",
        )
        return resource_dir

    def test_resource_override_is_cwd_independent(self):
        with tempfile.TemporaryDirectory() as temporary_dir:
            resource_dir = self._resource_tree(temporary_dir)
            resolved = resolve_resource_dir(
                {"OPENSPOTTER_RESOURCE_ROOT": str(resource_dir)}
            )
            self.assertEqual(resolved, resource_dir.resolve())

    def test_auto_mode_preserves_source_checkout_layout(self):
        with tempfile.TemporaryDirectory() as temporary_dir:
            resource_dir = self._resource_tree(temporary_dir)
            layout = resolve_runtime_layout(
                {},
                resource_dir=resource_dir,
                source_checkout=True,
            )
            self.assertEqual(layout.mode, "source")
            self.assertEqual(layout.runtime_dir, resource_dir.resolve())
            self.assertEqual(layout.config_dir, resource_dir.resolve() / "config")

    def test_user_mode_uses_platform_data_directory(self):
        with tempfile.TemporaryDirectory() as temporary_dir:
            root = Path(temporary_dir)
            resource_dir = self._resource_tree(root)
            local_data = root / "LocalAppData"
            layout = resolve_runtime_layout(
                {
                    "OPENSPOTTER_MODE": "user",
                    "LOCALAPPDATA": str(local_data),
                },
                resource_dir=resource_dir,
                source_checkout=True,
                platform_name="win32",
                home_dir=root / "home",
            )
            self.assertEqual(layout.mode, "user")
            self.assertEqual(
                layout.runtime_dir,
                (local_data / "OpenSpotter" / "Control").resolve(),
            )

    def test_explicit_home_takes_precedence_over_source_mode(self):
        with tempfile.TemporaryDirectory() as temporary_dir:
            root = Path(temporary_dir)
            resource_dir = self._resource_tree(root)
            explicit_home = root / "portable-data"
            layout = resolve_runtime_layout(
                {
                    "OPENSPOTTER_MODE": "source",
                    "OPENSPOTTER_HOME": str(explicit_home),
                },
                resource_dir=resource_dir,
                source_checkout=True,
            )
            self.assertEqual(layout.mode, "custom")
            self.assertEqual(layout.runtime_dir, explicit_home.resolve())

    def test_first_run_seeds_defaults_without_overwriting_user_config(self):
        with tempfile.TemporaryDirectory() as temporary_dir:
            root = Path(temporary_dir)
            resource_dir = self._resource_tree(root)
            runtime_dir = root / "user-data"
            destination_config = runtime_dir / "config"
            destination_config.mkdir(parents=True)
            existing = destination_config / "config_global.json"
            existing.write_text(
                json.dumps({"source": "operator"}),
                encoding="utf-8",
            )

            layout = resolve_runtime_layout(
                {"OPENSPOTTER_HOME": str(runtime_dir)},
                resource_dir=resource_dir,
                source_checkout=False,
            )
            copied = prepare_runtime_layout(layout)

            self.assertEqual(
                json.loads(existing.read_text(encoding="utf-8")),
                {"source": "operator"},
            )
            self.assertIn(
                destination_config / "config_gcode_workflow.json",
                copied,
            )
            self.assertTrue(layout.gcode_dir.is_dir())
            self.assertTrue(layout.log_dir.is_dir())

    def test_packaged_seed_allowlist_excludes_local_connection_credentials(self):
        self.assertNotIn("config_moonraker.json", PACKAGED_CONFIG_FILES)
        with tempfile.TemporaryDirectory() as temporary_dir:
            root = Path(temporary_dir)
            resource_dir = self._resource_tree(root)
            (resource_dir / "config" / "config_moonraker.json").write_text(
                json.dumps({"api_key": "must-not-seed"}),
                encoding="utf-8",
            )
            runtime_dir = root / "user-data"
            layout = resolve_runtime_layout(
                {"OPENSPOTTER_HOME": str(runtime_dir)},
                resource_dir=resource_dir,
                source_checkout=False,
            )
            prepare_runtime_layout(layout)
            self.assertFalse(
                (layout.config_dir / "config_moonraker.json").exists()
            )

    def test_explicit_migration_precedes_packaged_defaults(self):
        with tempfile.TemporaryDirectory() as temporary_dir:
            root = Path(temporary_dir)
            resource_dir = self._resource_tree(root)
            legacy_config = root / "old-checkout" / "config"
            legacy_config.mkdir(parents=True)
            (legacy_config / "config_global.json").write_text(
                json.dumps({"source": "legacy-operator"}),
                encoding="utf-8",
            )
            (legacy_config / "config_moonraker.json").write_text(
                json.dumps({"host": "printer.local", "api_key": "local-secret"}),
                encoding="utf-8",
            )
            runtime_dir = root / "new-user-data"
            layout = resolve_runtime_layout(
                {
                    "OPENSPOTTER_HOME": str(runtime_dir),
                    "OPENSPOTTER_MIGRATE_FROM": str(legacy_config.parent),
                },
                resource_dir=resource_dir,
                source_checkout=False,
            )

            prepare_runtime_layout(layout)

            migrated_global = json.loads(
                (layout.config_dir / "config_global.json").read_text(
                    encoding="utf-8"
                )
            )
            self.assertEqual(migrated_global, {"source": "legacy-operator"})
            self.assertTrue(
                (layout.config_dir / "config_moonraker.json").is_file()
            )
            self.assertTrue(
                (layout.config_dir / "config_gcode_workflow.json").is_file()
            )

    def test_invalid_mode_has_an_actionable_error(self):
        with tempfile.TemporaryDirectory() as temporary_dir:
            resource_dir = self._resource_tree(temporary_dir)
            with self.assertRaisesRegex(RuntimeError, "OPENSPOTTER_MODE"):
                resolve_runtime_layout(
                    {"OPENSPOTTER_MODE": "roaming"},
                    resource_dir=resource_dir,
                    source_checkout=False,
                )


if __name__ == "__main__":
    unittest.main()
