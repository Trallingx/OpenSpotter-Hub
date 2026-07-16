import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from app.core.storage import read_json_object, write_json_atomic, write_text_atomic


class CoreStorageTests(unittest.TestCase):
    def test_json_round_trip_uses_object_schema_and_trailing_newline(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "nested" / "config.json"

            resolved = write_json_atomic(path, {"enabled": True, "value": 1.5})

            self.assertEqual(resolved, path.resolve())
            self.assertEqual(
                read_json_object(path),
                {"enabled": True, "value": 1.5},
            )
            self.assertTrue(path.read_text(encoding="utf-8").endswith("\n"))

    def test_failed_replace_keeps_existing_destination(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "state.txt"
            path.write_text("before", encoding="utf-8")

            with mock.patch("app.core.storage.os.replace", side_effect=OSError("busy")):
                with self.assertRaisesRegex(OSError, "busy"):
                    write_text_atomic(path, "after")

            self.assertEqual(path.read_text(encoding="utf-8"), "before")
            self.assertEqual(list(path.parent.glob(".*.tmp")), [])

    def test_non_object_json_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            path.write_text(json.dumps(["not", "an", "object"]), encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "object"):
                read_json_object(path)


if __name__ == "__main__":
    unittest.main()
