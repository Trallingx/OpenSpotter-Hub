import json
import tempfile
import unittest
from pathlib import Path

from app.runtime_logging import (
    configure_logging,
    get_logger,
    log_options,
    serialize_options,
    shutdown_logging,
)


class RuntimeLoggingTests(unittest.TestCase):
    def tearDown(self):
        shutdown_logging()

    def test_runtime_options_are_written_and_sensitive_values_are_redacted(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            log_path = configure_logging(temp_dir, level="DEBUG")
            log_options(
                get_logger("test"),
                "runtime.options",
                mode="grid",
                speed=12.5,
                api_token="do-not-log",
                nested={"password": "also-secret", "enabled": True},
            )
            shutdown_logging()

            text = log_path.read_text(encoding="utf-8")

        self.assertIn("runtime.options", text)
        self.assertIn('"mode":"grid"', text)
        self.assertIn('"speed":12.5', text)
        self.assertIn('"api_token":"<redacted>"', text)
        self.assertIn('"password":"<redacted>"', text)
        self.assertNotIn("do-not-log", text)
        self.assertNotIn("also-secret", text)

    def test_option_serialization_handles_paths_and_nonfinite_numbers(self):
        source_path = Path("config") / "config_global.json"
        payload = json.loads(
            serialize_options(
                {
                    "path": source_path,
                    "values": [float("inf"), float("-inf"), float("nan")],
                }
            )
        )

        self.assertEqual(payload["path"], str(source_path))
        self.assertEqual(payload["values"], ["inf", "-inf", "nan"])


if __name__ == "__main__":
    unittest.main()
