import json
import tempfile
import tkinter as tk
import unittest
from pathlib import Path

from app.machine.connection_settings import (
    ConnectionSettingsError,
    MoonrakerConnectionSettings,
    load_connection_settings,
    save_connection_settings,
)
from app.moonraker_connection_window import MoonrakerConnectionWindow


class MoonrakerConnectionSettingsTests(unittest.TestCase):
    def test_missing_file_uses_safe_defaults(self):
        with tempfile.TemporaryDirectory() as directory:
            settings = load_connection_settings(
                Path(directory) / "config_moonraker.json"
            )

        self.assertEqual(settings.host, "localhost")
        self.assertEqual(settings.port, 7125)
        self.assertEqual(settings.scheme, "http")
        self.assertEqual(settings.route_prefix, "")
        self.assertIsNone(settings.api_key)

    def test_round_trip_normalizes_values_and_keeps_secrets_out_of_repr(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "nested" / "config_moonraker.json"
            settings = MoonrakerConnectionSettings(
                host=" printer.local ",
                port="7126",
                scheme=" HTTPS ",
                route_prefix="/proxy/moonraker/",
                api_key=" top-secret-key ",
            )

            saved_path = save_connection_settings(settings, path)
            loaded = load_connection_settings(path)
            payload = json.loads(path.read_text(encoding="utf-8"))

        self.assertEqual(saved_path, path)
        self.assertEqual(loaded.host, "printer.local")
        self.assertEqual(loaded.port, 7126)
        self.assertEqual(loaded.scheme, "https")
        self.assertEqual(loaded.route_prefix, "/proxy/moonraker")
        self.assertEqual(loaded.api_key, "top-secret-key")
        self.assertEqual(payload["version"], 1)
        self.assertEqual(payload["api_key"], "top-secret-key")
        self.assertNotIn("top-secret-key", repr(settings))
        self.assertNotIn("top-secret-key", repr(loaded))
        self.assertNotIn(
            "top-secret-key",
            repr(loaded.to_moonraker_config()),
        )

    def test_runtime_config_contains_urls_and_api_header(self):
        settings = MoonrakerConnectionSettings(
            host="printer.local",
            port=443,
            scheme="https",
            route_prefix="moonraker",
            api_key="secret",
        )

        config = settings.to_moonraker_config(request_timeout=3.0)

        self.assertEqual(
            config.base_url,
            "https://printer.local:443/moonraker",
        )
        self.assertEqual(
            config.websocket_url,
            "wss://printer.local:443/moonraker/websocket",
        )
        self.assertEqual(config.request_headers["X-Api-Key"], "secret")
        self.assertEqual(config.request_timeout, 3.0)

    def test_invalid_network_fields_are_rejected_without_echoing_key(self):
        invalid_values = (
            {"host": ""},
            {"host": "http://printer.local"},
            {"host": "printer.local/moonraker"},
            {"host": "printer local"},
            {"host": "printer.local@attacker.example"},
            {"host": "printer.local?x=1"},
            {"host": "printer.local#fragment"},
            {"host": "printer.local:7125"},
            {"host": "[::1"},
            {"host": "printer.local", "port": 0},
            {"host": "printer.local", "port": "not-a-port"},
            {"host": "printer.local", "scheme": "ftp"},
        )
        for values in invalid_values:
            with self.subTest(values=values):
                with self.assertRaises(ConnectionSettingsError) as raised:
                    MoonrakerConnectionSettings(
                        api_key="must-not-appear",
                        **values,
                    )
                self.assertNotIn("must-not-appear", str(raised.exception))

    def test_ipv4_ipv6_and_dns_hosts_are_canonicalized(self):
        self.assertEqual(
            MoonrakerConnectionSettings(host="192.168.1.10").host,
            "192.168.1.10",
        )
        self.assertEqual(
            MoonrakerConnectionSettings(host="[2001:db8::1]").host,
            "[2001:db8::1]",
        )
        self.assertEqual(
            MoonrakerConnectionSettings(host="Printer.LOCAL.").host,
            "printer.local",
        )

    def test_malformed_or_non_object_json_has_generic_error(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config_moonraker.json"
            path.write_text('{"api_key": "secret",', encoding="utf-8")
            with self.assertRaisesRegex(
                ConnectionSettingsError,
                "could not be read",
            ) as raised:
                load_connection_settings(path)
            self.assertNotIn("secret", str(raised.exception))

            path.write_text('["not", "an", "object"]', encoding="utf-8")
            with self.assertRaisesRegex(
                ConnectionSettingsError,
                "must be a JSON object",
            ):
                load_connection_settings(path)


class MoonrakerConnectionWindowTests(unittest.TestCase):
    def test_constructs_masked_persistent_window_and_saves_callback_config(self):
        try:
            root = tk.Tk()
        except tk.TclError as exc:
            self.skipTest(f"Tk is unavailable: {exc}")
        root.withdraw()
        self.addCleanup(root.destroy)

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config_moonraker.json"
            callbacks = []
            window = MoonrakerConnectionWindow(
                root,
                path=path,
                on_saved=callbacks.append,
            )
            self.addCleanup(
                lambda: window.destroy() if window.winfo_exists() else None
            )

            self.assertEqual(window.state(), "withdrawn")
            self.assertEqual(window.api_key_input.cget("show"), "*")
            self.assertFalse(window.overrideredirect())

            window.host_var.set("printer.local")
            window.scheme_var.set("https")
            window.port_var.set("443")
            window.route_prefix_var.set("/moonraker")
            window.api_key_var.set("secret")
            config = window.save()

            self.assertIs(config, callbacks[0])
            self.assertEqual(
                callbacks[0].base_url,
                "https://printer.local:443/moonraker",
            )
            self.assertEqual(window.hide(), "break")
            self.assertEqual(window.state(), "withdrawn")
            self.assertTrue(window.winfo_exists())
            self.assertEqual(
                load_connection_settings(path).api_key,
                "secret",
            )

    def test_saved_callback_failure_is_contained_after_persistence(self):
        try:
            root = tk.Tk()
        except tk.TclError as exc:
            self.skipTest(f"Tk is unavailable: {exc}")
        root.withdraw()
        self.addCleanup(root.destroy)

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config_moonraker.json"

            def fail_callback(_config):
                raise RuntimeError("simulated reconnect failure")

            window = MoonrakerConnectionWindow(
                root,
                path=path,
                on_saved=fail_callback,
            )
            self.addCleanup(
                lambda: window.destroy() if window.winfo_exists() else None
            )
            window.host_var.set("printer.local")

            config = window.save()

            self.assertIsNotNone(config)
            self.assertTrue(path.exists())
            self.assertIn("reconnecting failed", window.status_var.get())


if __name__ == "__main__":
    unittest.main()
