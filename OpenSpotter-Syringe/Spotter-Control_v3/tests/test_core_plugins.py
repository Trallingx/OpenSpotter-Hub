import unittest
from types import SimpleNamespace
from unittest import mock

from app.core.plugins import (
    API_VERSION,
    ENTRY_POINT_GROUP,
    DuplicatePluginError,
    PluginCompatibilityError,
    PluginLoadError,
    PluginManifest,
    PluginManifestError,
    PluginRegistry,
)


class DummyPlugin:
    def __init__(self, plugin_id, api_version=API_VERSION):
        self.manifest = PluginManifest(
            id=plugin_id,
            display_name=plugin_id.title(),
            version="1.0.0",
            api_version=api_version,
        )
        self.name = plugin_id

    def plan(self, context):
        return [{"plugin": self.name, "context": context}]


class ClassEntryPointPlugin(DummyPlugin):
    def __init__(self):
        super().__init__("class-entry-point")


class FakeEntryPoint:
    def __init__(
        self,
        name,
        candidate=None,
        error=None,
        group=ENTRY_POINT_GROUP,
        distribution="test-distribution",
    ):
        self.name = name
        self.value = "tests:{}".format(name)
        self.group = group
        self.dist = SimpleNamespace(name=distribution)
        self.candidate = candidate
        self.error = error
        self.load_count = 0

    def load(self):
        self.load_count += 1
        if self.error is not None:
            raise self.error
        return self.candidate


class PluginRegistryTests(unittest.TestCase):
    def test_registration_validates_manifest_and_implementation(self):
        registry = PluginRegistry()
        plugin = DummyPlugin("alpha")

        self.assertIs(registry.register(plugin, source="test"), plugin)
        self.assertIs(registry.get("alpha"), plugin)
        self.assertEqual(registry.ids(), ("alpha",))
        with self.assertRaises(TypeError):
            registry.plugins["other"] = plugin

        with self.subTest("invalid ID"):
            invalid_id = DummyPlugin("Invalid ID")
            with self.assertRaisesRegex(PluginManifestError, "plugin ID"):
                PluginRegistry().register(invalid_id)

        with self.subTest("incompatible API"):
            incompatible = DummyPlugin("future", api_version=API_VERSION + 1)
            with self.assertRaisesRegex(
                PluginCompatibilityError,
                "targets API version",
            ):
                PluginRegistry().register(incompatible)

        with self.subTest("missing planner"):
            plugin_without_plan = SimpleNamespace(
                manifest=PluginManifest(
                    id="missing-plan",
                    display_name="Missing Plan",
                    version="1.0.0",
                ),
                name="missing-plan",
            )
            with self.assertRaisesRegex(PluginManifestError, "callable plan"):
                PluginRegistry().register(plugin_without_plan)

        with self.subTest("legacy name mismatch"):
            mismatched = DummyPlugin("manifest-name")
            mismatched.name = "different-name"
            with self.assertRaisesRegex(PluginManifestError, "does not match"):
                PluginRegistry().register(mismatched)

    def test_duplicate_plugin_ids_are_rejected_without_replacing_first(self):
        registry = PluginRegistry()
        first = DummyPlugin("duplicate")
        second = DummyPlugin("duplicate")
        registry.register(first, source="first-source")

        with self.assertRaisesRegex(
            DuplicatePluginError,
            "first-source",
        ):
            registry.register(second, source="second-source")

        self.assertIs(registry.require("duplicate"), first)

    def test_builtin_discovery_is_deterministic_and_idempotent(self):
        registry = PluginRegistry()

        first_loaded = registry.discover_builtins("app.plugins")
        first_spiral = registry.require("spiral")
        second_loaded = registry.discover_builtins("app.plugins")

        self.assertIn("spiral", first_loaded)
        self.assertEqual(second_loaded, ())
        self.assertIs(registry.require("spiral"), first_spiral)

    def test_external_entry_points_load_in_name_order_only_once(self):
        registry = PluginRegistry()
        alpha = FakeEntryPoint("alpha", candidate=lambda: DummyPlugin("alpha"))
        beta = FakeEntryPoint("beta", candidate=DummyPlugin("beta"))

        first_loaded = registry.load_entry_points(
            entry_points=[beta, alpha],
        )
        second_loaded = registry.load_entry_points(
            entry_points=[beta, alpha],
        )

        self.assertEqual(first_loaded, ("alpha", "beta"))
        self.assertEqual(second_loaded, ())
        self.assertEqual(alpha.load_count, 1)
        self.assertEqual(beta.load_count, 1)
        self.assertEqual(registry.ids(), ("alpha", "beta"))

    def test_external_loader_supports_python_38_mapping_api(self):
        registry = PluginRegistry()
        external = FakeEntryPoint(
            "external",
            candidate=lambda: DummyPlugin("external"),
        )

        with mock.patch(
            "app.core.plugins.importlib_metadata.entry_points",
            return_value={ENTRY_POINT_GROUP: [external]},
        ):
            loaded = registry.load_entry_points()

        self.assertEqual(loaded, ("external",))
        self.assertIsNotNone(registry.get("external"))

    def test_external_loader_constructs_plugin_classes(self):
        registry = PluginRegistry()
        external = FakeEntryPoint(
            "class-entry-point",
            candidate=ClassEntryPointPlugin,
        )

        loaded = registry.load_entry_points(entry_points=[external])

        self.assertEqual(loaded, ("class-entry-point",))
        self.assertIsInstance(
            registry.require("class-entry-point"),
            ClassEntryPointPlugin,
        )

    def test_external_loader_can_report_failure_and_continue(self):
        registry = PluginRegistry()
        broken = FakeEntryPoint("broken", error=RuntimeError("cannot import"))
        healthy = FakeEntryPoint(
            "healthy",
            candidate=lambda: DummyPlugin("healthy"),
        )
        errors = []

        loaded = registry.load_entry_points(
            entry_points=[healthy, broken],
            on_error=errors.append,
        )

        self.assertEqual(loaded, ("healthy",))
        self.assertEqual(len(errors), 1)
        self.assertIsInstance(errors[0], PluginLoadError)
        self.assertIn("cannot import", str(errors[0]))


if __name__ == "__main__":
    unittest.main()
